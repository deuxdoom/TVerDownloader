# src/download_manager.py
# (변경 없음, 이전 답변과 동일)
# 수정: _start_download에서 자막 관련 설정 3개를 읽어 DownloadThread로 전달

import os
import subprocess
from typing import List, Dict, Optional, Any
from PyQt6.QtCore import QObject, pyqtSignal

from src.threads.download_thread import DownloadThread
from src.threads.conversion_thread import ConversionThread
from src.history_store import HistoryStore
from src.utils import get_startupinfo

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
        self._conversion_meta_cache: Dict[str, Dict] = {}

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
        if not download_folder: self._on_download_finished(url, False, "", {}); return
        from src.utils import construct_filename_template
        output_template = construct_filename_template(self.config)
        quality_format = self.config.get("quality", "bv*+ba/b")
        bandwidth_limit = self.config.get("bandwidth_limit", "0")

        # --- [추가된 부분 시작] ---
        # 자막 설정 읽기
        download_subs = self.config.get("download_subtitles", True)
        embed_subs = self.config.get("embed_subtitles", True)
        subtitle_format = self.config.get("subtitle_format", "vtt")
        # --- [추가된 부분 끝] ---

        thread = DownloadThread(url=url, download_folder=download_folder, ytdlp_exe_path=self.ytdlp_path,
                                ffmpeg_exe_path=self.ffmpeg_path, output_template=output_template,
                                quality_format=quality_format, bandwidth_limit=bandwidth_limit,
                                # --- [추가된 부분 시작] ---
                                download_subtitles=download_subs,
                                embed_subtitles=embed_subs,
                                subtitle_format=subtitle_format
                                # --- [추가된 부분 끝] ---
                                )
        thread.progress.connect(self._on_progress); thread.finished.connect(self._on_download_finished)
        self._active_threads[url] = thread; self._logged_start.discard(url); thread.start()
        self._update_queue_counter()
    
    def _on_progress(self, url: str, payload: Dict[str, Any]):
        if url not in self._logged_start and 'log' in payload:
            self._logged_start.add(url)
            self.log.emit(f"{'='*44}\n다운로드 시작: {url}\n{'='*44}")
        self.progress_updated.emit(url, payload)
        
    def _get_video_codec(self, filepath: str) -> Optional[str]:
        if not self.ffmpeg_path: return None
        ffprobe_path = self.ffmpeg_path.replace('ffmpeg.exe', 'ffprobe.exe')
        if not os.path.exists(ffprobe_path):
             ffprobe_path = self.ffmpeg_path.replace('ffmpeg', 'ffprobe')
        
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

        preferred_codec_key = self.config.get("preferred_codec", "avc")
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
        self._update_queue_counter()
        
        self.check_queue_and_start()

        if not self._task_queue and not self._active_threads and not self._active_conversions:
            self._active_urls.clear(); self._logged_start.clear(); self.all_tasks_completed.emit()

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
        self._conversion_meta_cache.pop(url, None)