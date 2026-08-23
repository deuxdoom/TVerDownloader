import os
import subprocess
from typing import List, Dict, Optional, Any
from PyQt6.QtCore import QObject, QDeadlineTimer, pyqtSignal

from src.threads.download_thread import DownloadThread
from src.threads.conversion_thread import ConversionThread
from src.history_store import HistoryStore
from src.metadata_prefetch import MetadataPrefetcher
from src.queue_store import QueueStore
from src.utils import (get_startupinfo, DEFAULT_PARALLEL, resolve_ffprobe_path,
                       item_percent, canonicalize_config_fragments,
                       canonicalize_config_codec, canonicalize_config_encoder)

class DownloadManager(QObject):
    log = pyqtSignal(str)
    heading = pyqtSignal(str, str)
    """구분선을 두른 제목과 그 아래 한 줄. (제목, 본문) 괘선을 그리는 일은 창이 맡는다."""
    item_added = pyqtSignal(str)
    progress_updated = pyqtSignal(str, dict)
    task_finished = pyqtSignal(str, bool, str, dict)
    queue_changed = pyqtSignal(int, int)
    all_tasks_completed = pyqtSignal()

    def __init__(self, config: Dict[str, Any], history_store: HistoryStore,
                 queue_store: Optional[QueueStore] = None, parent=None):
        super().__init__(parent)
        self.config = config; self.history_store = history_store
        self._queue_store = queue_store
        self._held: List[str] = []; self._queue_meta: Dict[str, Dict[str, str]] = {}
        self.ytdlp_path: Optional[str] = None; self.ffmpeg_path: Optional[str] = None
        self._task_queue: List[str] = []; self._active_threads: Dict[str, DownloadThread] = {}
        self._active_conversions: Dict[str, ConversionThread] = {}
        self._active_urls: set[str] = set(); self._logged_start: set[str] = set()
        self._conversion_meta_cache: Dict[str, Dict] = {}
        self._concurrency_logged = False
        self._shutting_down = False
        self._item_percent: Dict[str, int] = {}
        self._prefetch = MetadataPrefetcher(self)
        self._prefetch.set_wanted_check(self.is_queued)
        self._prefetch.set_ignore_ssl_errors(config.get("ignore_ssl_errors", False))
        self._prefetch.loaded.connect(self._on_prefetch_loaded)

    def overall_progress(self) -> Optional[int]:
        """이번 묶음 전체의 진행률(0~100). 아무것도 걸려 있지 않으면 None.

        분모는 진행 중인 것이 아니라 묶음 전체(_active_urls)다 - 진행 중인 것만 세면 90%짜리가
        끝날 때 값이 뒤로 간다. 대기는 0, 변환 중은 100, 되살려 세워 둔 것(_held)은 분모에서 뺀다.
        """
        held = set(self._held)
        tracked = [url for url in self._active_urls if url not in held]
        total = len(tracked)
        if not total:
            return None
        done = 0
        for url in tracked:
            if self.is_queued(url):
                continue
            if self.is_busy(url):
                done += self._item_percent.get(url, 0)
            else:
                done += 100
        return min(100, done // total)

    STOP_WAIT_MS = 3000
    """stop_all()이 스레드들의 뒷정리를 기다리는 전체 시간.

    kill은 부르는 자리에서 끝나지만 쓰다 만 파일을 지우는 일은 스레드가 run()에서
    빠져나오며 한다. 스레드마다 따로 세지 않고 전체에 한 번 건다.
    """

    def is_busy(self, url: str) -> bool:
        """받는 중이거나 변환 중. 밖에서 프로세스가 돌고 있다는 뜻이다.

        변환은 별도 스레드라 _active_threads에 없다. 다운로드만 보면 변환 중인 항목이
        새어 나가, 목록에서 지워도 ffmpeg는 계속 돈다.
        """
        return url in self._active_threads or url in self._active_conversions

    def is_queued(self, url: str) -> bool:
        """차례를 기다리는 중. 아직 아무 프로세스도 뜨지 않았다.

        되살려 세워 둔 것(_held)도 여기 든다 - 가르면 되살린 항목만 목록 조작에서 새어 나간다.
        """
        return url in self._task_queue or url in self._held

    def is_pending(self, url: str) -> bool:
        """아직 끝나지 않았다. 진행 중이거나 기다리는 중."""
        return self.is_busy(url) or self.is_queued(url)

    def pending_count(self) -> int:
        """앱을 껐다 켜면 실제로 끊기는 항목 수(받는 중 + 변환 중 + 대기 중).

        되살려 세워 둔 것(_held)은 빼고 센다 - 껐다 켜도 같은 자리에 다시 서므로, 세면
        되살린 것을 두는 사람에게 '진행 중인 작업이 있다'는 거짓 경고가 뜬다.
        """
        return (len(self._task_queue)
                + len(self._active_threads) + len(self._active_conversions))

    def stop_all(self) -> int:
        """진행 중인 다운로드와 변환을 모두 멈추고, 멈춘 개수를 돌려준다. 대기열을 먼저 비운다.

        완료 신호에 check_queue_and_start가 새 프로세스를 띄우면 거둘 사람이 없어서다.
        비우기 전에 남은 대기열을 적고(뒤에 적으면 빈 목록으로 덮인다), 멈춘 뒤에는 쓰다 만
        파일을 지우는 스레드를 STOP_WAIT_MS만큼 기다린다.
        """
        self._persist_queue()
        self._shutting_down = True
        self._task_queue.clear()
        self._held.clear()
        self._item_percent.clear()
        self._prefetch.stop_all()
        threads = list(self._active_threads.values()) + list(self._active_conversions.values())
        for thread in threads:
            thread.stop()
        deadline = QDeadlineTimer(self.STOP_WAIT_MS)
        for thread in threads:
            if not thread.wait(deadline):
                self.log.emit("[알림] 정리가 끝나기 전에 종료합니다. 받다 만 파일이 남을 수 있습니다.")
                break
        self._update_queue_counter()
        return len(threads)

    def set_paths(self, ytdlp_path: str, ffmpeg_path: str):
        self.ytdlp_path = ytdlp_path; self.ffmpeg_path = ffmpeg_path
        self._prefetch.set_ytdlp_path(ytdlp_path)

    def update_config(self, new_config: Dict[str, Any]):
        self.config = new_config
        self._prefetch.set_ignore_ssl_errors(new_config.get("ignore_ssl_errors", False))
        self.check_queue_and_start()

    def add_task(self, url: str, title: str = "", thumbnail: str = "") -> bool:
        """대기열에 하나 넣는다. 제목·표지 그림을 이미 알면 함께 넘긴다.

        시리즈 선택·즐겨찾기 확인은 그 둘을 손에 들고 있다. 모르는 채로 들어온 것만 미리 묻는다.
        """
        url = (url or "").strip()
        if not url or url in self._active_urls:
            if url in self._active_urls: self.log.emit(f"[알림] 이미 대기열/작업 중인 URL입니다: {url}")
            return False
        self._active_urls.add(url); self._task_queue.append(url)
        self.item_added.emit(url); self.log.emit(f"[대기열] 추가됨: {url}")
        self._emit_preview(url, title, thumbnail)
        self._update_queue_counter(); self.check_queue_and_start()
        if self.is_queued(url) and not title:
            self._prefetch.request(url)
        return True

    def _emit_preview(self, url: str, title: str, thumbnail: str = "", duration=None):
        """카드에 제목·표지 그림·재생 시간만 먼저 얹는다.

        _on_progress를 거치지 않는 것은 그쪽이 첫 줄에서 '다운로드 시작' 구분선을 긋는
        자리라, 아직 받지도 않은 항목이 로그에 시작을 알리게 되기 때문이다.
        """
        self._remember_meta(url, title, thumbnail)
        payload: Dict[str, Any] = {}
        if title:
            payload["title"] = title
        if thumbnail:
            payload["thumbnail"] = thumbnail
        if duration:
            payload["duration"] = duration
        if payload:
            self.progress_updated.emit(url, payload)

    def _on_prefetch_loaded(self, url: str, metadata: Dict[str, Any]):
        """미리 물어본 답이 왔다. 아직 기다리는 중일 때만 카드에 얹는다.

        여기서 한 번 더 저장한다 - 놓치면 앱이 갑자기 죽었을 때 되살린 카드가 제목 없이 뜬다.
        """
        if not self.is_queued(url):
            return
        self._emit_preview(url, metadata.get("title") or "", metadata.get("thumbnail") or "",
                           metadata.get("duration"))
        self._persist_queue()

    def stop_task(self, url: str):
        if url in self._active_threads: self._active_threads[url].stop()
        if url in self._active_conversions: self._active_conversions[url].stop()

    def remove_task_from_queue(self, url: str):
        """대기 중인 것 하나를 뺀다. 되살려 세워 둔 것도 같은 길로 빠진다.

        가르면 `대기열에서 제거`가 되살린 카드에서만 듣지 않아 지울 방법이 없는 카드가 생긴다.
        """
        if url in self._held:
            self._held.remove(url)
        elif url in self._task_queue:
            self._task_queue.remove(url)
        else:
            return False
        self._active_urls.discard(url); self._queue_meta.pop(url, None)
        self._prefetch.cancel(url)
        self._update_queue_counter(); self.log.emit(f"[대기열] 제거됨: {url}")
        return True

    def restore_task(self, url: str, title: str = "", thumbnail: str = "") -> bool:
        """지난 실행에서 남은 항목을 카드만 세워 둔다. 받기 시작하지는 않는다.

        대기열이 아니라 따로 세우는 것(_held)은, 같은 줄에 넣으면 새 주소 하나에
        check_queue_and_start가 앞에 선 것까지 통째로 띄우기 때문이다. 저절로 시작하지 않는
        근거는 지역 제한이다 - `--tray`로 뜨면 앱이 VPN보다 먼저 서서 전부 실패로 끝난다.
        """
        url = (url or "").strip()
        if not url or url in self._active_urls:
            return False
        self._active_urls.add(url); self._held.append(url)
        self.item_added.emit(url)
        self._emit_preview(url, title, thumbnail)
        self._update_queue_counter()
        if not title:
            self._prefetch.request(url)
        return True

    def held_count(self) -> int:
        """시작을 기다리며 세워 둔 항목 수. 0이면 되살린 것이 없다."""
        return len(self._held)

    def start_held_tasks(self) -> int:
        """세워 둔 것들을 대기열에 넣고 받기 시작한다. 넣은 개수를 돌려준다.

        맨 앞에 붙인다 - 지난 실행에서 이미 기다리던 것들이라 그 사이에 넣은 주소보다 앞이다.
        """
        if not self._held:
            return 0
        count = len(self._held)
        self._task_queue[:0] = self._held
        self._held.clear()
        self._update_queue_counter()
        self.check_queue_and_start()
        return count

    def check_queue_and_start(self):
        if self._shutting_down: return
        if not self.ytdlp_path or not self.ffmpeg_path: return
        max_concurrent = self.config.get("max_concurrent_downloads", DEFAULT_PARALLEL)
        if self._task_queue and not self._concurrency_logged:
            self._concurrency_logged = True
            self.log.emit(f"동시 다운로드 최대 {max_concurrent}개로 진행합니다.")
        while len(self._active_threads) < max_concurrent and self._task_queue:
            url = self._task_queue.pop(0); self._start_download(url)
        self._update_queue_counter()

    def _start_download(self, url: str):
        preloaded = self._prefetch.take(url)
        download_folder = self.config.get("download_folder", "")
        if not download_folder: self._on_download_finished(url, False, "", {}); return
        from src.utils import construct_filename_template
        output_template = construct_filename_template(self.config)
        quality_format = self.config.get("quality", "bv*+ba/b")

        download_subs = self.config.get("download_subtitles", True)
        embed_subs = self.config.get("embed_subtitles", False)
        subtitle_format = self.config.get("subtitle_format", "vtt")
        ignore_ssl = self.config.get("ignore_ssl_errors", False)
        embed_thumb = self.config.get("embed_thumbnail", False)
        fragments = canonicalize_config_fragments(self.config)

        thread = DownloadThread(url=url, download_folder=download_folder, ytdlp_exe_path=self.ytdlp_path,
                                ffmpeg_exe_path=self.ffmpeg_path, output_template=output_template,
                                quality_format=quality_format,
                                download_subtitles=download_subs,
                                embed_subtitles=embed_subs,
                                subtitle_format=subtitle_format,
                                ignore_ssl_errors=ignore_ssl,
                                embed_thumbnail=embed_thumb,
                                preloaded_metadata=preloaded,
                                concurrent_fragments=fragments
                                )
        thread.progress.connect(self._on_progress); thread.finished.connect(self._on_download_finished)
        self._active_threads[url] = thread; self._logged_start.discard(url); thread.start()
        self._update_queue_counter()

    def _on_progress(self, url: str, payload: Dict[str, Any]):
        if url not in self._logged_start and 'log' in payload:
            self._logged_start.add(url)
            self.heading.emit("다운로드 시작", url)
        self._remember_meta(url, payload.get("title") or "", payload.get("thumbnail") or "")
        self._item_percent[url] = item_percent(payload.get("percent"),
                                               self._item_percent.get(url, 0))
        self.progress_updated.emit(url, payload)

    def _get_video_codec(self, filepath: str) -> Optional[str]:
        ffprobe_path = resolve_ffprobe_path(self.ffmpeg_path)
        if not ffprobe_path:
            self.log.emit("[오류] ffprobe를 찾지 못해 코덱을 확인할 수 없습니다.")
            return None

        command = [
            ffprobe_path, '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_name',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            filepath
        ]
        try:
            proc = subprocess.run(command, capture_output=True, text=True, startupinfo=get_startupinfo(), timeout=10)
            if proc.returncode == 0:
                return proc.stdout.strip()
            else:
                self.log.emit(f"[오류] ffprobe 코덱 확인 실패: {proc.stderr}")
                return None
        except Exception as e:
            self.log.emit(f"[오류] ffprobe 실행 중 예외 발생: {e}")
            return None

    def _on_download_finished(self, url: str, success: bool, final_filepath: str, metadata: dict):
        thread = self._active_threads.pop(url, None)
        if thread: thread.deleteLater()

        if not success or not final_filepath or not os.path.exists(final_filepath):
            self.log.emit(f"[실패] 다운로드 실패 또는 파일 없음: {url}")
            self.task_finished.emit(url, False, "", metadata)
            self._check_completion(); return

        self.log.emit(f"[성공] 다운로드 완료: {final_filepath}")
        self._conversion_meta_cache[url] = metadata

        preferred_codec_key = canonicalize_config_codec(self.config)

        if preferred_codec_key == "original":
            self.task_finished.emit(url, True, final_filepath, metadata)
            self._check_completion()
            return

        current_codec = self._get_video_codec(final_filepath)

        codec_map = {'avc': 'h264', 'hevc': 'hevc'}
        target_codec = codec_map.get(preferred_codec_key)

        if current_codec and target_codec and current_codec != target_codec:
            self.log.emit(f"변환 시작: {current_codec} -> {target_codec}")
            self._start_conversion(url, final_filepath, target_codec)
        else:
            self.task_finished.emit(url, True, final_filepath, metadata)
            self._check_completion()

    def _start_conversion(self, url: str, input_path: str, target_codec: str):
        """재인코딩만 남았으므로 원본은 늘 지운다 - 같은 영상이 코덱만 다르게 둘 남는다."""
        self.progress_updated.emit(url, {"status": f"{target_codec.upper()} 변환 중..."})

        thread = ConversionThread(url, input_path, self.ffmpeg_path,
                                  target_codec=target_codec,
                                  delete_original=True,
                                  hw_encoder_setting=canonicalize_config_encoder(self.config))
        thread.log.connect(self.log); thread.finished.connect(self._on_conversion_finished)
        self._active_conversions[url] = thread; thread.start()
        self.check_queue_and_start()

    def _on_conversion_finished(self, success: bool, url:str, new_filepath: str):
        thread = self._active_conversions.pop(url, None)
        if thread: thread.deleteLater()
        meta = self._conversion_meta_cache.pop(url, {})
        final_status = "완료" if success else "변환 오류"
        payload = {"status": final_status}
        if success: payload["final_filepath"] = new_filepath
        self.progress_updated.emit(url, payload)
        self.task_finished.emit(url, success, new_filepath if success else "", meta)
        self._check_completion()

    def _check_completion(self):
        if self._shutting_down: return
        self._update_queue_counter()

        self.check_queue_and_start()

        if not self._task_queue and not self._active_threads and not self._active_conversions:
            self._active_urls = set(self._held); self._logged_start.clear()
            self._item_percent.clear()
            self._queue_meta = {url: meta for url, meta in self._queue_meta.items()
                                if url in self._active_urls}
            self._concurrency_logged = False
            self.all_tasks_completed.emit()

    def _remember_meta(self, url: str, title: str = "", thumbnail: str = ""):
        """카드에 얹은 제목·표지 그림을 대기열 저장용으로 적어 둔다.

        비어 있는 값으로 덮지 않는다 - 통째로 갈아 끼우면 이미 알던 것까지 지워진다.
        """
        if not title and not thumbnail:
            return
        entry = self._queue_meta.setdefault(url, {})
        if title:
            entry["title"] = title
        if thumbnail:
            entry["thumbnail"] = thumbnail

    def _snapshot_pending(self) -> List[Dict[str, str]]:
        """파일에 남길 항목을 대기열 차례대로 늘어놓는다.

        받는 중·변환 중인 것도 함께 적는다 - 다음 실행에서 대기로 되살아난다. 차례를 되살린 것,
        변환 중, 받는 중, 기다리는 중 순으로 두면 다음 실행의 위아래가 지금과 같아진다.
        """
        urls = (list(self._held) + list(self._active_conversions)
                + list(self._active_threads) + list(self._task_queue))
        return [{"url": url,
                 "title": self._queue_meta.get(url, {}).get("title", ""),
                 "thumbnail": self._queue_meta.get(url, {}).get("thumbnail", "")}
                for url in urls]

    def _persist_queue(self):
        """지금 남은 대기열을 파일에 적는다.

        멈추는 중이면 쓰지 않는다 - stop_all이 적어 둔 것을 빈 목록으로 덮어쓴다.
        """
        if self._queue_store is None or self._shutting_down:
            return
        self._queue_store.replace(self._snapshot_pending())
        self._queue_store.save()

    def _update_queue_counter(self):
        """대기·진행 개수를 알리고, 남은 대기열을 파일에도 반영한다.

        저장을 여기 한 곳에 붙였다 - 대기열이 바뀌는 길목마다 이미 이것이 불리므로,
        저장할 자리를 따로 세면 언젠가 한 곳을 빠뜨린다.
        """
        queued = len(self._task_queue) + len(self._held)
        active = len(self._active_threads) + len(self._active_conversions)
        self._persist_queue()
        self.queue_changed.emit(queued, active)

    def reset_for_redownload(self, url: str):
        if not url: return
        try:
            if url in self._task_queue: self._task_queue.remove(url)
            if url in self._held: self._held.remove(url)
        except ValueError: pass
        self._active_urls.discard(url)
        self._logged_start.discard(url)
        self._item_percent.pop(url, None)
        self._queue_meta.pop(url, None)
        self._conversion_meta_cache.pop(url, None)
        self._prefetch.cancel(url)
