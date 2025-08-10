# src/download_manager.py
# 목적: 다운로드 작업의 생명주기를 관리하는 백엔드 컨트롤러

from typing import List, Dict, Optional, Any
from PyQt6.QtCore import QObject, pyqtSignal

from src.threads.download_thread import DownloadThread
from src.utils import construct_filename_template
from src.history_store import HistoryStore
from src.widgets import DownloadItemWidget

class DownloadManager(QObject):
    """
    다운로드 큐, 활성 스레드, 상태를 관리하고 UI와 상호작용하기 위한 시그널을 보냅니다.
    """
    # 시그널
    log = pyqtSignal(str)
    item_added = pyqtSignal(str) # (url)
    progress_updated = pyqtSignal(str, dict) # (url, payload)
    task_finished = pyqtSignal(str, bool) # (url, success)
    queue_changed = pyqtSignal(int, int) # (queued_count, active_count)
    all_tasks_completed = pyqtSignal() # 모든 작업 완료 시

    def __init__(self, config: Dict[str, Any], history_store: HistoryStore, parent=None):
        super().__init__(parent)
        self.config = config
        self.history_store = history_store
        
        self.ytdlp_path: Optional[str] = None
        self.ffmpeg_path: Optional[str] = None

        self._task_queue: List[str] = []
        self._active_threads: Dict[str, DownloadThread] = {}
        self._active_urls: set[str] = set()
        self._logged_start: set[str] = set()

    def set_paths(self, ytdlp_path: str, ffmpeg_path: str):
        """SetupThread 완료 후 실행 경로 설정."""
        self.ytdlp_path = ytdlp_path
        self.ffmpeg_path = ffmpeg_path

    def update_config(self, new_config: Dict[str, Any]):
        """설정 변경 시 호출."""
        self.config = new_config
        self.check_queue_and_start() # 동시 다운로드 수 변경 대응

    def add_task(self, url: str) -> bool:
        """새로운 다운로드 작업을 큐에 추가합니다."""
        url = (url or "").strip()
        if not url or url in self._active_urls:
            if url in self._active_urls:
                self.log.emit(f"[알림] 이미 대기열/다운로드 중인 URL입니다: {url}")
            return False
        
        self._active_urls.add(url)
        self._task_queue.append(url)
        
        self.item_added.emit(url) # UI에 아이템 위젯 생성을 요청
        self.log.emit(f"[대기열] 추가됨: {url}")
        self._update_queue_counter()
        
        self.check_queue_and_start()
        return True

    def stop_task(self, url: str):
        """실행 중인 특정 다운로드 작업을 중지합니다."""
        if url in self._active_threads:
            thread = self._active_threads[url]
            thread.stop() # 스레드에 중지 신호 전송

    def remove_task_from_queue(self, url: str):
        """대기열에 있는 작업을 제거합니다."""
        if url in self._task_queue:
            self._task_queue.remove(url)
            self._active_urls.remove(url)
            self._update_queue_counter()
            self.log.emit(f"[대기열] 제거됨: {url}")
            return True
        return False

    def check_queue_and_start(self):
        """큐를 확인하여 가능한 만큼 새 다운로드를 시작합니다."""
        if not self.ytdlp_path or not self.ffmpeg_path:
            return # 아직 준비 안 됨

        max_concurrent = self.config.get("max_concurrent_downloads", 3)
        
        while len(self._active_threads) < max_concurrent and self._task_queue:
            url = self._task_queue.pop(0)
            self._start_download(url)
        
        self._update_queue_counter()

    def _start_download(self, url: str):
        """실제 DownloadThread를 생성하고 시작합니다."""
        download_folder = self.config.get("download_folder", "")
        if not download_folder:
            self.log.emit("[오류] 다운로드 폴더가 설정되지 않았습니다.")
            self._active_urls.remove(url) # 실패 처리
            self._update_queue_counter()
            return
            
        output_template = construct_filename_template(self.config)
        quality_format = self.config.get("quality", "bv*+ba/b")

        thread = DownloadThread(
            url=url,
            download_folder=download_folder,
            ytdlp_exe_path=self.ytdlp_path,
            ffmpeg_exe_path=self.ffmpeg_path,
            output_template=output_template,
            quality_format=quality_format
        )
        thread.progress.connect(self._on_progress)
        thread.finished.connect(self._on_finished)
        
        self._active_threads[url] = thread
        self._logged_start.discard(url)
        thread.start()
        self._update_queue_counter()
    
    def _on_progress(self, url: str, payload: Dict[str, Any]):
        """스레드로부터 진행 상황을 받아 UI에 전달합니다."""
        if url not in self._logged_start:
            self._logged_start.add(url)
            self.log.emit(f"{'='*44}\n다운로드 시작: {url}\n{'='*44}")
        
        if "log" in payload:
            self.log.emit(payload["log"])
            
        self.progress_updated.emit(url, payload)

    def _on_finished(self, url: str, success: bool):
        """스레드 완료 시 후처리를 담당합니다."""
        thread = self._active_threads.pop(url, None)
        if thread:
            thread.deleteLater()

        if success:
            self.log.emit(f"[성공] 다운로드 완료: {url}")
        else:
            self.log.emit(f"[실패] 다운로드 실패 또는 취소: {url}")

        if url in self._active_urls:
            self._active_urls.remove(url)
        self._logged_start.discard(url)
        
        self.task_finished.emit(url, success)
        self._update_queue_counter()
        
        self.check_queue_and_start()

        # 모든 작업이 끝났는지 확인
        if not self._task_queue and not self._active_threads:
            self.all_tasks_completed.emit()

    def _update_queue_counter(self):
        """큐 카운터 시그널을 보냅니다."""
        queued = len(self._task_queue)
        active = len(self._active_threads)
        self.queue_changed.emit(queued, active)