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
    """구분선을 두른 제목과 그 아래 한 줄. (제목, 본문)

    괘선을 몇 개 넣어야 한 줄로 떨어지는지는 로그 패널 폭과 글꼴을 재야 나온다.
    여기서는 알 수 없는 값이라 그리는 일은 창에 맡기고 내용만 보낸다.
    """
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

        분모는 '지금 돌고 있는 것'이 아니라 **묶음 전체**다(_active_urls). 진행
        중인 것만 세면 항목이 끝나 빠질 때마다 진행률이 뒤로 간다 — 90%짜리와
        20%짜리가 있을 때 앞의 것이 끝나면 55%에서 20%로 떨어진다. 다 끝나
        _active_urls가 비워질 때 묶음도 함께 끝난다.

        차례를 기다리는 항목은 0으로 센다. 하나를 받는 동안 열 개가 대기 중이면
        전체로는 이제 시작한 것이 맞다.

        변환 중인 항목은 받기를 마쳤으므로 100으로 남는다. 변환은 진행률을
        내주지 않아 더 잘게 나눌 수가 없다. 그래서 변환만 남은 구간에서는 링이
        가득 찬 채로 멈춰 있고, 몇 개가 남았는지는 툴팁의 '진행' 수가 알려 준다.

        **지난 실행에서 되살려 세워 둔 것(_held)은 분모에서 뺀다.** 사용자가
        시작을 누르기 전까지는 이번 묶음이 아니다. 세어 버리면 새로 넣은 하나를
        받는 동안 고리가 낮은 값에 눌려 있고, 스무 개를 되살린 사람은 그 하나가
        다 끝나도 5%에서 멈춘 것을 본다.
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

    프로세스를 죽이는 것과 쓰다 만 파일을 지우는 것은 다른 곳에서 일어난다.
    kill은 부르는 자리에서 끝나지만, 지우는 일은 스레드가 run()에서 빠져나오며
    한다. 스레드마다 따로 세지 않고 전체에 한 번 거는 값이다 — 종료를 누른 뒤
    창이 몇 초씩 붙잡혀 있으면 멈춘 것으로 보인다.
    """

    def is_busy(self, url: str) -> bool:
        """받는 중이거나 변환 중. 밖에서 프로세스가 돌고 있다는 뜻이다.

        변환은 다운로드가 끝난 뒤 도는 별도 스레드라 _active_threads에 없다.
        진행 여부를 물으면서 다운로드만 보면 변환 중인 항목이 '아무것도 하지 않는
        항목'으로 새어 나가, 목록에서 지워도 ffmpeg는 계속 돈다.
        """
        return url in self._active_threads or url in self._active_conversions

    def is_queued(self, url: str) -> bool:
        """차례를 기다리는 중. 아직 아무 프로세스도 뜨지 않았다.

        지난 실행에서 되살려 세워 둔 것(_held)도 여기 든다. 밖에서 보면 둘 다
        '아직 시작하지 않은 대기 항목'이라, 목록에서 빼거나 개수를 셀 때 갈라
        놓으면 되살린 항목만 규칙에서 새어 나간다.
        """
        return url in self._task_queue or url in self._held

    def is_pending(self, url: str) -> bool:
        """아직 끝나지 않았다. 진행 중이거나 기다리는 중."""
        return self.is_busy(url) or self.is_queued(url)

    def pending_count(self) -> int:
        """앱을 껐다 켜면 실제로 끊기는 항목 수(받는 중 + 변환 중 + 대기 중).

        업데이트처럼 앱을 껐다 켜는 일을 하기 전에 물어보려고 쓴다. 자료구조를
        밖에서 세지 않도록 여기 둔다 — 변환만 남은 항목을 빠뜨리는 실수가
        예전에 아홉 군데에서 났다.

        **되살려 세워 둔 것(_held)은 빼고 센다.** 그것들은 아직 아무것도
        시작하지 않아 끊길 일이 없고, 껐다 켜도 같은 자리에 그대로 다시 선다.
        세어 버리면 되살린 것을 시작하지 않고 두는 사람에게는 업데이트할 때마다
        '진행 중인 작업이 있다'는 창이 뜨는데, 정작 중단되는 것은 하나도 없다.

        그래서 여기만 is_pending과 답이 갈린다. 묻는 것이 달라서다 — 이쪽은
        '지금 껐을 때 잃는 것'이고, is_pending은 '아직 끝나지 않았는가'다.
        """
        return (len(self._task_queue)
                + len(self._active_threads) + len(self._active_conversions))

    def stop_all(self) -> int:
        """진행 중인 다운로드와 변환을 모두 멈추고, 멈춘 개수를 돌려준다.

        대기열을 먼저 비운다. 멈춘 작업이 끝났다고 알려 오는 순간
        check_queue_and_start가 다음 것을 새로 띄우는데, 종료 직전에 뜬
        프로세스는 거둘 사람이 없어 그대로 남는다.

        멈춘 뒤 기다리는 것은 뒷정리가 스레드 쪽에 있기 때문이다. 기다리지 않고
        프로세스를 끝내면 쓰다 만 파일을 지우는 코드에 차례가 오지 않는다.
        기다림은 전체 STOP_WAIT_MS 하나로 묶어, 작업이 많아도 종료가 늘어지지 않게 한다.

        **비우기 전에 남은 대기열을 파일에 적는다.** 받는 중이던 것까지 함께
        적어 두고, 다음 실행에서 대기로 되살린다. 끊긴 자리에서 이어받을 수는
        없지만 목록에서 통째로 사라지는 것보다 낫다. 적는 일이 반드시 이 자리
        앞이어야 하는 것은, 아래에서 대기열을 비운 뒤 세는 코드가 다시 저장을
        불러 방금 적은 것을 빈 목록으로 덮어쓰기 때문이다(_persist_queue가
        _shutting_down을 보고 돌아 나가는 이유이기도 하다).
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

        시리즈 선택 창과 즐겨찾기 확인은 그 둘을 이미 손에 들고 있다. 넘겨받으면
        카드가 그 자리에서 채워져, 미리 묻기에 회선을 쓸 일도 없다. 모르는 채로
        들어온 것(직접 붙여넣기·다중 추가·드롭)만 미리 물어본다.
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

    def _emit_preview(self, url: str, title: str, thumbnail: str = ""):
        """카드에 제목과 표지 그림만 먼저 얹는다.

        progress_updated를 쓰되 _on_progress는 거치지 않는다. 그쪽은 진행률을
        갈무리하고 첫 줄에서 '다운로드 시작' 구분선을 긋는 자리라, 아직 받지도
        않은 항목이 지나가면 로그에 시작을 알리는 줄이 먼저 찍힌다.

        카드에 얹는 김에 저장용으로도 적어 둔다. 카드가 아는 것과 파일에 남는
        것이 갈리면, 되살린 항목만 제목 없이 뜨는 자리가 생긴다.
        """
        self._remember_meta(url, title, thumbnail)
        payload: Dict[str, Any] = {}
        if title:
            payload["title"] = title
        if thumbnail:
            payload["thumbnail"] = thumbnail
        if payload:
            self.progress_updated.emit(url, payload)

    def _on_prefetch_loaded(self, url: str, metadata: Dict[str, Any]):
        """미리 물어본 답이 왔다. 아직 기다리는 중일 때만 카드에 얹는다.

        여기서 한 번 더 저장한다. 대기열 구성이 바뀐 것이 아니라 자동으로 적히는
        자리가 아닌데, 이 답을 놓치면 앱이 갑자기 죽었을 때 되살린 카드가 제목
        없이 뜬다. 항목 하나당 한 번뿐이라 자주 쓰는 것도 아니다.
        """
        if not self.is_queued(url):
            return
        self._emit_preview(url, metadata.get("title") or "", metadata.get("thumbnail") or "")
        self._persist_queue()

    def stop_task(self, url: str):
        if url in self._active_threads: self._active_threads[url].stop()
        if url in self._active_conversions: self._active_conversions[url].stop()

    def remove_task_from_queue(self, url: str):
        """대기 중인 것 하나를 뺀다. 되살려 세워 둔 것도 같은 길로 빠진다.

        둘을 가르지 않는 것은 밖에서 보면 똑같이 '아직 시작하지 않은 대기 항목'
        이기 때문이다. 우클릭 메뉴의 `대기열에서 제거`가 되살린 카드에서만 듣지
        않으면, 지울 방법이 없는 카드가 생긴다.
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

        **대기열(_task_queue)이 아니라 따로 세워 둔다**(_held). 같은 줄에 넣으면
        사용자가 새 주소 하나를 넣는 순간 check_queue_and_start가 앞에 선 것까지
        통째로 띄운다. 하나만 받으려던 사람 앞에서 스무 개가 한꺼번에 뜨는 일은
        없어야 한다.

        **저절로 시작하지 않는 근거는 지역 제한이다.** TVer은 일본 밖에서 막히고,
        시작 프로그램으로 등록해 두면 로그인과 함께 앱이 VPN보다 먼저 선다. 그
        자리에서 받기 시작하면 담아 둔 것이 전부 실패로 끝난다. 클립보드와
        드롭이 주소를 채워만 두고 시작하지 않는 것과 같은 판단이다.

        제목을 모르는 채로 되살아난 항목은 미리 묻기에 맡긴다. 갑자기 죽어
        저장이 늦은 경우인데, 그대로 두면 누르기 전까지 `제목 로딩 중…`으로
        남아 무엇을 걸어 두었는지 여전히 알 수 없다.
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

        **맨 앞에 붙인다.** 지난 실행에서 이미 기다리던 것들이라, 뒤에 붙이면
        그 사이에 넣은 주소보다 더 오래 기다리게 된다.

        개수를 세는 일은 여기서 끝내고, 실제로 몇 개가 동시에 뜰지는 여느 때와
        같이 check_queue_and_start가 정한다.
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

        target_container_format = self.config.get("conversion_format", "none")
        if target_container_format != "none":
            self.log.emit(f"변환 시작: {target_container_format.upper()}")
            self._start_conversion(url, final_filepath, target_format=target_container_format)
            return

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
            self._start_conversion(url, final_filepath, target_codec=target_codec, delete_original=True)
        else:
            self.task_finished.emit(url, True, final_filepath, metadata)
            self._check_completion()

    def _start_conversion(self, url: str, input_path: str, target_format: Optional[str] = None, target_codec: Optional[str] = None, delete_original: Optional[bool] = None):
        status_msg = ""
        if target_format: status_msg = f"{target_format.upper()} 변환 중..."
        elif target_codec: status_msg = f"{target_codec.upper()} 변환 중..."
        self.progress_updated.emit(url, {"status": status_msg})

        delete_on_conv = self.config.get("delete_on_conversion", False)
        if delete_original is not None:
            delete_on_conv = delete_original

        thread = ConversionThread(url, input_path, self.ffmpeg_path,
                                  target_format=target_format,
                                  target_codec=target_codec,
                                  delete_original=delete_on_conv,
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

        **비어 있는 값으로 덮지 않는다.** 미리 묻기가 제목만 가져오고 표지 그림은
        못 가져오는 경우가 있어, 통째로 갈아 끼우면 이미 알던 것까지 지워진다.
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

        **받는 중·변환 중인 것도 함께 적는다.** 다음 실행에서 그것들은 대기로
        되살아난다. 끊긴 자리에서 이어받을 수는 없지만, 목록에서 사라지는 것보다
        '아직 안 받았다'로 남는 편이 낫다.

        차례는 먼저 시작한 것이 앞이다. 되살린 것 → 변환 중 → 받는 중 →
        기다리는 중 순으로 늘어놓으면 다음 실행의 대기열이 이번과 같은 차례로
        선다. 카드는 새로 온 것을 맨 위에 꽂으므로 화면에서도 지금과 같은
        위아래가 된다.
        """
        urls = (list(self._held) + list(self._active_conversions)
                + list(self._active_threads) + list(self._task_queue))
        return [{"url": url,
                 "title": self._queue_meta.get(url, {}).get("title", ""),
                 "thumbnail": self._queue_meta.get(url, {}).get("thumbnail", "")}
                for url in urls]

    def _persist_queue(self):
        """지금 남은 대기열을 파일에 적는다.

        멈추는 중이면 쓰지 않는다. stop_all이 대기열을 비우기 직전에 한 번
        적어 두는데, 비운 뒤 개수를 세는 자리가 다시 여기로 들어와 방금 적은
        것을 빈 목록으로 덮어쓴다.
        """
        if self._queue_store is None or self._shutting_down:
            return
        self._queue_store.replace(self._snapshot_pending())
        self._queue_store.save()

    def _update_queue_counter(self):
        """대기·진행 개수를 알리고, 남은 대기열을 파일에도 반영한다.

        **저장을 여기 한 곳에 붙였다.** 대기열 구성이 바뀌는 길목마다 이미 이것이
        불리므로, 저장할 자리를 따로 세면 언젠가 한 곳을 빠뜨린다 — 창 쪽 아홉
        군데가 자료구조를 각자 세다 조건이 어긋난 적이 있다.
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
