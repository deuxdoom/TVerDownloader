# src/threads/download_thread.py
# 수정:
# - _parse_line: 로그 필터링 기능 추가. 'Destination', 'Merging', 'Embedding', 'ERROR' 등
#                핵심 키워드가 포함된 로그만 UI에 표시하여 불필요한 frag 로그를 제거.

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
        self._current_component: str = "비디오"

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

        if p.poll() is None:
            try:
                if os.name == "nt":
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

        # payload를 미리 만들지 않고, 필요한 정보가 있을 때만 생성
        payload: Dict[str, Any] = {}

        # --- 로그 필터링 로직 ---
        # 로그로 표시할 키워드 목록
        log_keywords = [
            "[download] Destination:", # 각 컴포넌트(비디오/오디오) 다운로드 완료
            "Merging formats into",   # 포맷 병합 시작
            "Embedding subtitles",    # 자막 병합 시작
            "[error]",                # 오류 메시지
            "ERROR:",                 # 오류 메시지
        ]
        # 키워드 중 하나라도 포함된 경우에만 로그를 payload에 추가
        if any(keyword in line for keyword in log_keywords):
            payload["log"] = line

        if "[download] Destination:" in line:
            destination_path = line.split("Destination:", 1)[1].lower()
            if ".m4a" in destination_path or "audio" in destination_path:
                self._current_component = "오디오"
            else:
                self._current_component = "비디오"
            # 파일 경로 추출 로직도 여기에 포함
            payload["final_filepath"] = line.split("Destination:", 1)[1].strip()

        # 진행률 표시줄(%)이 포함된 라인은 항상 처리
        m_progress = re.search(r"\[download\]\s+([0-9.]+)% of.*?at (.*?/s)\s+ETA\s+(.*)", line)
        if m_progress:
            payload.update({
                "status": "다운로드 중",
                "percent": float(m_progress.group(1)),
                "speed": m_progress.group(2),
                "eta": m_progress.group(3),
                "component": self._current_component
            })
        
        # 후처리 상태 업데이트
        if "Merging formats" in line:
            payload["status"] = "후처리 중 (병합)"
            # 병합 시 최종 파일 경로 갱신
            m_path = re.search(r'Merging formats into "(.*?)"', line)
            if m_path: payload["final_filepath"] = m_path.group(1).strip()
        elif "Embedding subtitles" in line:
            payload["status"] = "후처리 중 (자막)"
                
        # 처리할 내용이 payload에 담긴 경우에만 시그널을 보냄
        if payload:
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