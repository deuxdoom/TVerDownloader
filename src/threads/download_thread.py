# src/threads/download_thread.py
# 수정:
# - _execute_download:
#   1. yt-dlp로 메타데이터(-J 옵션)를 먼저 가져옴
#   2. 가져온 메타데이터와 파일명 설정값을 조합하여 Python 코드 내에서 직접 최종 파일 경로를 생성 (제목 길이 제한 포함)
#   3. 생성된 최종 파일 경로를 -o 옵션으로 yt-dlp 다운로드 명령어에 전달

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
    finished = pyqtSignal(str, bool)

    def __init__(self, url: str, download_folder: str, ytdlp_exe_path: str,
                 ffmpeg_exe_path: str, output_template: str, quality_format: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.download_folder = download_folder
        self.ytdlp_exe_path = ytdlp_exe_path
        self.ffmpeg_exe_path = os.path.dirname(ffmpeg_exe_path)
        # output_template은 이제 메타데이터와 조합하기 위한 '형식'으로만 사용됨
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
                p.send_signal(signal.CTRL_BREAK_EVENT); p.wait(timeout=2)
            else:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM); p.wait(timeout=2)
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
        # 1. 메타데이터 먼저 가져오기
        metadata = self._get_metadata()
        if not metadata:
            self.progress.emit(self.url, {"status": "오류", "log": "메타데이터를 가져올 수 없습니다."})
            return False
        
        # UI에 제목/썸네일 즉시 표시
        self.progress.emit(self.url, {
            "title": metadata.get("title", "제목 없음"),
            "thumbnail": metadata.get("thumbnail")
        })

        # 2. Python에서 최종 파일 경로 생성 (제목 길이 제한 포함)
        final_filepath = self._build_final_filepath(metadata)

        # 3. 생성된 경로로 다운로드 명령어 재구성
        command = self._build_command(final_filepath)
        
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
                self._parse_line(line, final_filepath)

        if self._stop_flag: return False
        rc = self.process.wait(timeout=5) if self.process else 1
        success = (rc == 0)
        final_status = "완료" if success else "오류"
        self.progress.emit(self.url, {"status": final_status, "percent": 100, "final_filepath": final_filepath})
        return success

    def _get_metadata(self) -> Optional[Dict[str, Any]]:
        """-J 옵션으로 JSON 메타데이터를 가져옵니다."""
        try:
            cmd = [self.ytdlp_exe_path, "-J", "--no-warnings", self.url]
            startupinfo = get_startupinfo()
            p = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8",
                errors="ignore", startupinfo=startupinfo, timeout=20,
            )
            return json.loads(p.stdout) if p.returncode == 0 else None
        except Exception:
            return None
    
    def _build_final_filepath(self, metadata: Dict[str, Any]) -> str:
        """메타데이터와 템플릿을 조합하여 최종 파일 경로를 생성합니다."""
        # 템플릿에서 확장자(.%(ext)s) 부분은 제외하고 처리
        template = self.output_template.rsplit('.', 1)[0]
        
        # 제목(title)에 길이 제한 적용
        title = metadata.get('title', 'NA')
        if len(title) > FILENAME_TITLE_MAX_LENGTH:
            title = title[:FILENAME_TITLE_MAX_LENGTH]

        # 템플릿의 각 부분을 실제 메타데이터로 교체
        path = template.replace("%(series,playlist_title)s", metadata.get('series') or metadata.get('playlist_title') or '')\
                       .replace("%(series)s", metadata.get('series') or '')\
                       .replace("%(upload_date>%Y-%m-%d)s", metadata.get('upload_date', '')[:8])\
                       .replace("%(episode_number)s", str(metadata.get('episode_number', '')))\
                       .replace("%(title)s", title)\
                       .replace("%(id)s", metadata.get('id', ''))
        
        # 확장자 추가
        ext = metadata.get('ext', 'mp4')
        
        # 최종 경로 조합
        return os.path.join(self.download_folder, f"{path}.{ext}")

    def _build_command(self, final_filepath: str) -> List[str]:
        """yt-dlp 실행 명령어를 생성합니다."""
        # -o 옵션에 템플릿 대신 완성된 파일 경로를 전달
        command: List[str] = [
            self.ytdlp_exe_path, self.url,
            "--ffmpeg-location", self.ffmpeg_exe_path,
            "-o", final_filepath,
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

    def _parse_line(self, line: str, final_filepath: str):
        line = (line or "").strip()
        if not line: return

        payload: Dict[str, Any] = {}
        log_keywords = ["Merging formats into", "Embedding subtitles", "[error]", "ERROR:"]
        
        # Destination 로그는 이제 사용하지 않으므로, 완료 로그는 Merging/Embedding으로 판단
        if any(keyword in line for keyword in log_keywords):
            payload["log"] = line

        if "[download] Destination:" in line:
            destination_path = line.split("Destination:", 1)[1].lower()
            if ".m4a" in destination_path or "audio" in destination_path:
                self._current_component = "오디오"
            else:
                self._current_component = "비디오"

        m_progress = re.search(r"\[download\]\s+([0-9.]+)% of.*?at (.*?/s)\s+ETA\s+(.*)", line)
        if m_progress:
            payload.update({
                "status": "다운로드 중",
                "percent": float(m_progress.group(1)), "speed": m_progress.group(2),
                "eta": m_progress.group(3), "component": self._current_component
            })
        
        if "Merging formats" in line:
            payload["status"] = "후처리 중 (병합)"
            # 병합 시 최종 파일 경로는 이미 알고 있으므로, payload에 담아 확실히 전달
            payload["final_filepath"] = final_filepath
        elif "Embedding subtitles" in line:
            payload["status"] = "후처리 중 (자막)"
                
        if payload:
            self.progress.emit(self.url, payload)