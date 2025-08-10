# src/threads/download_thread.py
# 수정: _kill_process_tree 내 taskkill 호출 시 CREATE_NO_WINDOW 플래그 추가

import os
import re
import json
import time
import signal
import subprocess
from typing import List, Optional, Dict, Any

from PyQt6.QtCore import QThread, pyqtSignal

from src.utils import get_startupinfo

class DownloadThread(QThread):
    """yt-dlp를 사용하여 단일 URL을 다운로드하고 진행률을 보고하는 스레드."""
    progress = pyqtSignal(str, dict)
    finished = pyqtSignal(str, bool)

    def __init__(self, url: str, download_folder: str, ytdlp_exe_path: str,
                 ffmpeg_exe_path: str, output_template: str, quality_format: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.download_folder = download_folder
        self.ytdlp_exe_path = ytdlp_exe_path
        self.ffmpeg_exe_path = os.path.dirname(ffmpeg_exe_path)
        self.output_template = output_template
        self.quality_format = quality_format

        self.process: Optional[subprocess.Popen] = None
        self._stop_flag = False

    def stop(self):
        if self._stop_flag: return
        self._stop_flag = True
        try:
            self.progress.emit(self.url, {"status": "취소 중...", "log": "사용자 중단 요청"})
        except RuntimeError: pass
        self._kill_process_tree()

    def _kill_process_tree(self):
        p = self.process
        if not p or p.poll() is not None: return
        try:
            if os.name == "nt":
                p.send_signal(signal.CTRL_BREAK_EVENT)
                p.wait(timeout=2)
            else:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
                p.wait(timeout=2)
        except (ProcessLookupError, subprocess.TimeoutExpired, OSError): pass

        # 프로세스가 여전히 살아있으면 강제 종료
        if p.poll() is None:
            try:
                if os.name == "nt":
                    # taskkill 실행 시 콘솔 창이 뜨지 않도록 creationflags 추가
                    flags = subprocess.CREATE_NO_WINDOW
                    subprocess.run(
                        ["taskkill", "/PID", str(p.pid), "/T", "/F"],
                        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=flags
                    )
                else:
                    os.killpg(os.getpgid(p.pid), signal.SIGKILL)
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

        self.finished.emit(self.url, is_successful)

    def _execute_download(self) -> bool:
        self._emit_quick_metadata()
        command = self._build_command()
        
        popen_kwargs: Dict[str, Any] = {}
        if os.name == 'nt':
            popen_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs['start_new_session'] = True
        
        self.progress.emit(self.url, {"status": "다운로드 중", "log": "yt-dlp 프로세스 시작..."})
        self.process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="ignore", **popen_kwargs
        )

        if self.process and self.process.stdout:
            for line in iter(self.process.stdout.readline, ""):
                if self._stop_flag:
                    self.progress.emit(self.url, {"status": "취소됨"})
                    return False
                self._parse_line(line)

        if self._stop_flag:
            return False

        rc = self.process.wait(timeout=5) if self.process else 1
        success = (rc == 0)
        final_status = "완료" if success else "오류"
        self.progress.emit(self.url, {"status": final_status, "percent": 100})
        return success

    def _build_command(self) -> List[str]:
        output_path_template = os.path.join(self.download_folder, self.output_template)
        command: List[str] = [
            self.ytdlp_exe_path, self.url,
            "--ffmpeg-location", self.ffmpeg_exe_path,
            "-o", output_path_template,
            "--retries", "10", "--fragment-retries", "10",
            "--force-overwrites", "--no-keep-fragments", "--no-check-certificate",
            "--windows-filenames", "--no-cache-dir", "--abort-on-error",
            "--add-header", "Accept-Language:ja-JP",
            "--progress", "--encoding", "utf-8", "--newline",
            "--write-subs", "--sub-format", "vtt", "--embed-subs",
        ]
        if self.quality_format == "audio_only":
            command += ["-f", "bestaudio", "-x", "--audio-format", "mp3"]
        else:
            command += ["-f", self.quality_format, "--merge-output-format", "mp4"]
        return command

    def _parse_line(self, line: str):
        line = (line or "").strip()
        if not line: return
        payload: Dict[str, Any] = {"log": line}
        m = re.search(r"\[download\]\s+([0-9.]+)% of.*?at (.*?/s)\s+ETA\s+(.*)", line)
        if m:
            payload.update({"status": "다운로드 중", "percent": float(m.group(1)), "speed": m.group(2), "eta": m.group(3)})
        elif "Merging formats" in line:
            payload["status"] = "후처리 중 (병합)"
        elif "Embedding subtitles" in line:
            payload["status"] = "후처리 중 (자막)"
        
        if "[download] Destination:" in line:
            payload["final_filepath"] = line.split("Destination:", 1)[1].strip()
        elif "Merging formats into" in line:
            m_path = re.search(r'Merging formats into "(.*?)"', line)
            if m_path: payload["final_filepath"] = m_path.group(1).strip()
                
        self.progress.emit(self.url, payload)

    def _emit_quick_metadata(self):
        try:
            cmd = [self.ytdlp_exe_path, "-J", "--no-warnings", self.url]
            startupinfo = get_startupinfo()
            p = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8",
                errors="ignore", startupinfo=startupinfo, timeout=20,
            )
            if p.returncode == 0:
                data = json.loads(p.stdout)
                payload = {"title": data.get("title"), "thumbnail": data.get("thumbnail") or (data.get("thumbnails")[0] if data.get("thumbnails") else None)}
                if any(v for v in payload.values()):
                    self.progress.emit(self.url, payload)
        except Exception:
            pass