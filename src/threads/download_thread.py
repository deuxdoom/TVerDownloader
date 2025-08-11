# src/threads/download_thread.py
# 수정:
# - finished 시그널: 메타데이터(dict)를 함께 전달하도록 인자 추가
# - run 메서드: 작업 완료 후 finished 시그널을 보낼 때, 초기에 획득했던 메타데이터를 함께 전달

import os
import re
import json
import time
import signal
import subprocess
from typing import List, Optional, Dict, Any

from PyQt6.QtCore import QThread, pyqtSignal

from src.utils import get_startupinfo, FILENAME_TITLE_MAX_LENGTH

class DownloadThread(QThread):
    progress = pyqtSignal(str, dict)
    finished = pyqtSignal(str, bool, str, dict) # (url, success, final_filepath, metadata)

    def __init__(self, url: str, download_folder: str, ytdlp_exe_path: str, ffmpeg_exe_path: str, 
                 output_template: str, quality_format: str, bandwidth_limit: str, parent=None):
        super().__init__(parent)
        self.url = url; self.download_folder = download_folder
        self.ytdlp_exe_path = ytdlp_exe_path; self.ffmpeg_exe_path = os.path.dirname(ffmpeg_exe_path)
        self.output_template = output_template; self.quality_format = quality_format
        self.bandwidth_limit = bandwidth_limit
        self.process: Optional[subprocess.Popen] = None
        self._stop_flag = False
        self._current_component: str = "비디오"
        self._final_filepath: str = ""
        self._metadata: Dict = {} # 메타데이터를 저장할 인스턴스 변수

    def stop(self):
        if self._stop_flag: return
        self._stop_flag = True
        try: self.progress.emit(self.url, {"status": "취소 중...", "log": "사용자 중단 요청"})
        except RuntimeError: pass
        self._kill_process_tree()

    def _kill_process_tree(self):
        p = self.process
        if not p or p.poll() is not None: return
        try:
            if os.name == "nt": p.send_signal(signal.CTRL_BREAK_EVENT); p.wait(timeout=2)
            else: os.killpg(os.getpgid(p.pid), signal.SIGTERM); p.wait(timeout=2)
        except (ProcessLookupError, subprocess.TimeoutExpired, OSError): pass
        if p.poll() is None:
            try:
                if os.name == "nt":
                    flags = subprocess.CREATE_NO_WINDOW
                    subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
                else: os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError, AttributeError): pass
            finally: self.process = None

    def run(self):
        is_successful = False
        try:
            is_successful = self._execute_download()
        except Exception as e:
            is_successful = False
            log_msg = f"다운로드 스레드 예외 발생: {e}"
            self.progress.emit(self.url, {"status": "오류", "log": log_msg})
        # 작업 완료 시 저장해둔 메타데이터를 함께 전달
        self.finished.emit(self.url, is_successful, self._final_filepath if is_successful else "", self._metadata)

    def _execute_download(self) -> bool:
        self._metadata = self._get_metadata() or {}
        if not self._metadata:
            self.progress.emit(self.url, {"status": "오류", "log": "메타데이터를 가져올 수 없습니다."})
            return False
        
        # UI에 빠른 피드백을 위해 초기 정보만 먼저 보냄
        self.progress.emit(self.url, {"title": self._metadata.get("title", "제목 없음"), "thumbnail": self._metadata.get("thumbnail")})
        
        self._final_filepath = self._build_final_filepath(self._metadata)
        command = self._build_command(self._final_filepath)
        popen_kwargs: Dict[str, Any] = {}
        if os.name == 'nt': popen_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        else: popen_kwargs['start_new_session'] = True
        
        self.progress.emit(self.url, {"status": "다운로드 중", "log": "yt-dlp 프로세스 시작..."})
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="ignore", **popen_kwargs)

        if self.process and self.process.stdout:
            for line in iter(self.process.stdout.readline, ""):
                if self._stop_flag: self.progress.emit(self.url, {"status": "취소됨"}); return False
                self._parse_line(line, self._final_filepath)
        if self._stop_flag: return False
        rc = self.process.wait(timeout=5) if self.process else 1
        success = (rc == 0)
        final_status = "완료" if success else "오류"
        self.progress.emit(self.url, {"status": final_status, "percent": 100, "final_filepath": self._final_filepath})
        return success

    def _get_metadata(self) -> Optional[Dict[str, Any]]:
        try:
            cmd = [self.ytdlp_exe_path, "-J", "--no-warnings", self.url]
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", startupinfo=get_startupinfo(), timeout=20)
            return json.loads(p.stdout) if p.returncode == 0 else None
        except Exception: return None
    
    def _build_final_filepath(self, metadata: Dict[str, Any]) -> str:
        template, ext = self.output_template.rsplit('.', 1)
        def replacer(match):
            key = match.group(1)
            if key == 'title':
                title = metadata.get('title', 'NA')
                return title[:FILENAME_TITLE_MAX_LENGTH]
            elif key == 'series,playlist_title': return metadata.get('series') or metadata.get('playlist_title') or ''
            elif key == 'upload_date>%Y-%m-%d': return (metadata.get('upload_date') or '')[:8]
            else: return str(metadata.get(key, ''))
        path_without_ext = re.sub(r'%\((.*?)\)s', replacer, template)
        path_without_ext = re.sub(r'\s+', ' ', path_without_ext).strip()
        final_filename = f"{path_without_ext}.{metadata.get('ext', ext)}"
        return os.path.join(self.download_folder, final_filename)

    def _build_command(self, final_filepath: str) -> List[str]:
        command: List[str] = [
            self.ytdlp_exe_path, self.url,
            "--ffmpeg-location", self.ffmpeg_exe_path,
            "-o", final_filepath,
            "--retries", "10", "--fragment-retries", "10", "--force-overwrites", "--no-keep-fragments",
            "--no-check-certificate", "--windows-filenames", "--no-cache-dir", "--abort-on-error",
            "--add-header", "Accept-Language:ja-JP", "--progress", "--encoding", "utf-8", "--newline",
            "--write-subs", "--sub-format", "vtt", "--embed-subs",
        ]
        if self.quality_format != 'audio_only': command.extend(["-f", self.quality_format, "--merge-output-format", "mp4"])
        if self.bandwidth_limit and self.bandwidth_limit != "0": command.extend(["-r", self.bandwidth_limit])
        return command

    def _parse_line(self, line: str, final_filepath: str):
        line = (line or "").strip()
        if not line: return
        payload: Dict[str, Any] = {}
        log_keywords = ["Merging formats into", "Embedding subtitles", "[error]", "ERROR:"]
        if any(keyword in line for keyword in log_keywords): payload["log"] = line
        if "[download] Destination:" in line:
            destination_path = line.split("Destination:", 1)[1].lower()
            if ".m4a" in destination_path or "audio" in destination_path: self._current_component = "오디오"
            else: self._current_component = "비디오"
        m_progress = re.search(r"\[download\]\s+([0-9.]+)% of.*?at (.*?/s)\s+ETA\s+(.*)", line)
        if m_progress:
            payload.update({"status": "다운로드 중", "percent": float(m_progress.group(1)), "speed": m_progress.group(2),
                            "eta": m_progress.group(3), "component": self._current_component})
        if "Merging formats" in line:
            payload["status"] = "후처리 중 (병합)"; payload["final_filepath"] = final_filepath
        elif "Embedding subtitles" in line:
            payload["status"] = "후처리 중 (자막)"
        if payload: self.progress.emit(self.url, payload)