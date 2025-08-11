# src/download_manager.py
# 수정:
# - 메타데이터 캐시(_metadata_cache) 및 관련 로직 전체 제거
# - _on_download_finished: DownloadThread로부터 받은 metadata를 그대로 상위로 전달

from typing import List, Dict, Optional, Any
from PyQt6.QtCore import QObject, pyqtSignal

from src.threads.download_thread import DownloadThread
from src.threads.conversion_thread import ConversionThread
from src.history_store import HistoryStore

class DownloadManager(QObject):
    log = pyqtSignal(str)
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
        self._conversion_meta_cache: Dict[str, Dict] = {} # 변환 중인 항목의 메타데이터만 임시 저장

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
        if url in self._active_conversions: self._active_conversions[url].terminate()

    def remove_task_from_queue(self, url: str):
        if url in self._task_queue:
            self._task_queue.remove(url); self._active_urls.remove(url)
            self._update_queue_counter(); self.log.emit(f"[대기열] 제거됨: {url}")
            return True
        return False

    def check_queue_and_start(self):
        if not self.ytdlp_path or not self.ffmpeg_path: return
        max_concurrent = self.config.get("max_concurrent_downloads", 3)
        while len(self._active_threads) < max_concurrent and self._task_queue:
            url = self._task_queue.pop(0); self._start_download(url)
        self._update_queue_counter()

    def _start_download(self, url: str):
        download_folder = self.config.get("download_folder", "")
        if not download_folder: self.log.emit(f"[오류] 다운로드 폴더가 설정되지 않아 '{url}' 다운로드를 시작할 수 없습니다."); self._on_download_finished(url, False, "", {}); return
        from src.utils import construct_filename_template
        output_template = construct_filename_template(self.config)
        quality_format = self.config.get("quality", "bv*+ba/b")
        bandwidth_limit = self.config.get("bandwidth_limit", "0")
        thread = DownloadThread(url=url, download_folder=download_folder, ytdlp_exe_path=self.ytdlp_path, ffmpeg_exe_path=self.ffmpeg_path, output_template=output_template, quality_format=quality_format, bandwidth_limit=bandwidth_limit)
        thread.progress.connect(self.progress_updated); thread.finished.connect(self._on_download_finished)
        self._active_threads[url] = thread; self._logged_start.discard(url); thread.start()
        self._update_queue_counter()
    
    def _on_progress(self, url: str, payload: Dict[str, Any]):
        if url not in self._logged_start and 'log' in payload:
            self._logged_start.add(url)
            self.log.emit(f"{'='*44}\n다운로드 시작: {url}\n{'='*44}")
        self.progress_updated.emit(url, payload)

    def _on_download_finished(self, url: str, success: bool, final_filepath: str, metadata: dict):
        thread = self._active_threads.pop(url, None)
        if thread: thread.deleteLater()
        
        if not success:
            self.log.emit(f"[실패] 다운로드 실패 또는 취소: {url}")
            self.task_finished.emit(url, False, "", metadata)
            self._check_completion(); return
        
        self.log.emit(f"[성공] 다운로드 완료: {final_filepath}")
        target_format = self.config.get("conversion_format", "none")
        if target_format != "none":
            self._conversion_meta_cache[url] = metadata # 변환 전 메타데이터 임시 저장
            self._start_conversion(url, final_filepath, target_format)
        else:
            self.task_finished.emit(url, True, final_filepath, metadata)
            self._check_completion()
            
    def _start_conversion(self, url: str, input_path: str, target_format: str):
        self.progress_updated.emit(url, {"status": f"{target_format.upper()} 변환 중..."})
        delete_original = self.config.get("delete_on_conversion", False)
        thread = ConversionThread(url, input_path, target_format, self.ffmpeg_path, delete_original)
        thread.log.connect(self.log); thread.finished.connect(self._on_conversion_finished)
        self._active_conversions[url] = thread; thread.start()
        
    def _on_conversion_finished(self, success: bool, url: str, new_filepath: str):
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
        self._update_queue_counter()
        if len(self._active_threads) + len(self._active_conversions) == 0:
            self.check_queue_and_start()
        if not self._task_queue and not self._active_threads and not self._active_conversions:
            self._active_urls.clear(); self._logged_start.clear(); self.all_tasks_completed.emit()

    def _update_queue_counter(self):
        queued = len(self._task_queue)
        active = len(self._active_threads) + len(self._active_conversions)
        self.queue_changed.emit(queued, active)