import os
import subprocess
from typing import List, Dict, Optional, Any
from PyQt6.QtCore import QObject, QDeadlineTimer, pyqtSignal

from src.threads.download_thread import DownloadThread
from src.threads.conversion_thread import ConversionThread
from src.history_store import HistoryStore
from src.utils import get_startupinfo, DEFAULT_PARALLEL, resolve_ffprobe_path, item_percent

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

    def __init__(self, config: Dict[str, Any], history_store: HistoryStore, parent=None):
        super().__init__(parent)
        self.config = config; self.history_store = history_store
        self.ytdlp_path: Optional[str] = None; self.ffmpeg_path: Optional[str] = None
        self._task_queue: List[str] = []; self._active_threads: Dict[str, DownloadThread] = {}
        self._active_conversions: Dict[str, ConversionThread] = {}
        self._active_urls: set[str] = set(); self._logged_start: set[str] = set()
        self._conversion_meta_cache: Dict[str, Dict] = {}
        self._concurrency_logged = False
        self._shutting_down = False
        self._item_percent: Dict[str, int] = {}

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
        """
        total = len(self._active_urls)
        if not total:
            return None
        done = 0
        for url in self._active_urls:
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
        """차례를 기다리는 중. 아직 아무 프로세스도 뜨지 않았다."""
        return url in self._task_queue

    def is_pending(self, url: str) -> bool:
        """아직 끝나지 않았다. 진행 중이거나 기다리는 중."""
        return self.is_busy(url) or self.is_queued(url)

    def pending_count(self) -> int:
        """아직 끝나지 않은 항목 수(받는 중 + 변환 중 + 대기 중).

        업데이트처럼 앱을 껐다 켜는 일을 하기 전에 물어보려고 쓴다. 자료구조를
        밖에서 세지 않도록 여기 둔다 — 변환만 남은 항목을 빠뜨리는 실수가
        예전에 아홉 군데에서 났다.
        """
        return len(self._task_queue) + len(self._active_threads) + len(self._active_conversions)

    def stop_all(self) -> int:
        """진행 중인 다운로드와 변환을 모두 멈추고, 멈춘 개수를 돌려준다.

        대기열을 먼저 비운다. 멈춘 작업이 끝났다고 알려 오는 순간
        check_queue_and_start가 다음 것을 새로 띄우는데, 종료 직전에 뜬
        프로세스는 거둘 사람이 없어 그대로 남는다.

        멈춘 뒤 기다리는 것은 뒷정리가 스레드 쪽에 있기 때문이다. 기다리지 않고
        프로세스를 끝내면 쓰다 만 파일을 지우는 코드에 차례가 오지 않는다.
        기다림은 전체 STOP_WAIT_MS 하나로 묶어, 작업이 많아도 종료가 늘어지지 않게 한다.
        """
        self._shutting_down = True
        self._task_queue.clear()
        self._item_percent.clear()
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

    def update_config(self, new_config: Dict[str, Any]):
        self.config = new_config; self.check_queue_and_start()

    def add_task(self, url: str) -> bool:
        url = (url or "").strip()
        if not url or url in self._active_urls:
            if url in self._active_urls: self.log.emit(f"[알림] 이미 대기열/작업 중인 URL입니다: {url}")
            return False
        self._active_urls.add(url); self._task_queue.append(url)
        self.item_added.emit(url); self.log.emit(f"[대기열] 추가됨: {url}")
        self._update_queue_counter(); self.check_queue_and_start()
        return True

    def stop_task(self, url: str):
        if url in self._active_threads: self._active_threads[url].stop()
        if url in self._active_conversions: self._active_conversions[url].stop()

    def remove_task_from_queue(self, url: str):
        if url in self._task_queue:
            self._task_queue.remove(url); self._active_urls.remove(url)
            self._update_queue_counter(); self.log.emit(f"[대기열] 제거됨: {url}")
            return True
        return False

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

        thread = DownloadThread(url=url, download_folder=download_folder, ytdlp_exe_path=self.ytdlp_path,
                                ffmpeg_exe_path=self.ffmpeg_path, output_template=output_template,
                                quality_format=quality_format,
                                download_subtitles=download_subs,
                                embed_subtitles=embed_subs,
                                subtitle_format=subtitle_format,
                                ignore_ssl_errors=ignore_ssl,
                                embed_thumbnail=embed_thumb
                                )
        thread.progress.connect(self._on_progress); thread.finished.connect(self._on_download_finished)
        self._active_threads[url] = thread; self._logged_start.discard(url); thread.start()
        self._update_queue_counter()

    def _on_progress(self, url: str, payload: Dict[str, Any]):
        if url not in self._logged_start and 'log' in payload:
            self._logged_start.add(url)
            self.heading.emit("다운로드 시작", url)
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
                codec = proc.stdout.strip()
                self.log.emit(f"파일 코덱 확인: '{codec}' ({filepath})")
                return codec
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
            self._start_conversion(url, final_filepath, target_format=target_container_format)
            return

        preferred_codec_key = self.config.get("preferred_codec", "original")

        if preferred_codec_key == "original":
            self.log.emit("선호 코덱이 '원본 유지'입니다. 재인코딩을 건너뜁니다.")
            self.task_finished.emit(url, True, final_filepath, metadata)
            self._check_completion()
            return

        current_codec = self._get_video_codec(final_filepath)

        codec_map = {'avc': 'h264', 'hevc': 'hevc', 'vp9': 'vp9', 'av1': 'av1'}
        target_codec = codec_map.get(preferred_codec_key)

        if current_codec and target_codec and current_codec != target_codec:
            self.log.emit(f"코덱 불일치. 변환 시작: (원본) '{current_codec}' -> (목표) '{target_codec}'")
            self._start_conversion(url, final_filepath, target_codec=target_codec, delete_original=True)
        else:
            if current_codec: self.log.emit(f"코덱 일치 ('{current_codec}'). 변환이 불필요합니다.")
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

        hw_encoder_setting = self.config.get("hardware_encoder", "cpu")

        quality_cfg = {
            "cpu_h264_crf": self.config.get("quality_cpu_h264_crf", 26),
            "cpu_h265_crf": self.config.get("quality_cpu_h265_crf", 31),
            "cpu_vp9_crf": self.config.get("quality_cpu_vp9_crf", 36),
            "cpu_av1_crf": self.config.get("quality_cpu_av1_crf", 41),
            "gpu_cq": self.config.get("quality_gpu_cq", 30),
        }

        thread = ConversionThread(url, input_path, self.ffmpeg_path,
                                  target_format=target_format,
                                  target_codec=target_codec,
                                  delete_original=delete_on_conv,
                                  hw_encoder_setting=hw_encoder_setting,
                                  quality_cfg=quality_cfg)
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
            self._active_urls.clear(); self._logged_start.clear()
            self._item_percent.clear()
            self._concurrency_logged = False
            self.all_tasks_completed.emit()

    def _update_queue_counter(self):
        queued = len(self._task_queue)
        active = len(self._active_threads) + len(self._active_conversions)
        self.queue_changed.emit(queued, active)

    def reset_for_redownload(self, url: str):
        if not url: return
        try:
            if url in self._task_queue: self._task_queue.remove(url)
        except ValueError: pass
        self._active_urls.discard(url)
        self._logged_start.discard(url)
        self._item_percent.pop(url, None)
        self._conversion_meta_cache.pop(url, None)
