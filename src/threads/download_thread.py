# src/threads/download_thread.py
# 수정:
# - import pathlib.Path 추가
# - __init__: 자막 관련 인자 3개 추가, ffmpeg 실행 파일 경로/디렉토리 경로 분리 저장
# - _build_command: 하드코딩된 자막 옵션 제거, 설정에 따른 분기 로직 추가
# - _convert_vtt_to_srt: VTT->SRT 변환 및 원본 VTT 삭제 메서드 신규 추가
# - _execute_download: 다운로드 완료 후, 설정에 따라 _convert_vtt_to_srt 호출 로직 추가

import os, re, json, time, signal, subprocess
from pathlib import Path # --- [추가] ---
from typing import List, Optional, Dict, Any
from PyQt6.QtCore import QThread, pyqtSignal
from src.utils import get_startupinfo, FILENAME_TITLE_MAX_LENGTH

class DownloadThread(QThread):
    progress = pyqtSignal(str, dict)
    finished = pyqtSignal(str, bool, str, dict)

    def __init__(self, url: str, download_folder: str, ytdlp_exe_path: str, ffmpeg_exe_path: str,
                 output_template: str, quality_format: str, bandwidth_limit: str, 
                 # --- [추가된 부분 시작] ---
                 download_subtitles: bool, embed_subtitles: bool, subtitle_format: str,
                 # --- [추가된 부분 끝] ---
                 parent=None):
        super().__init__(parent)
        self.url = url; self.download_folder = download_folder
        self.ytdlp_exe_path = ytdlp_exe_path
        
        # --- [수정된 부분 시작] ---
        # yt-dlp는 디렉토리 경로가 필요하고, SRT 변환은 실행 파일 경로가 필요
        self.ffmpeg_path_dir = os.path.dirname(ffmpeg_exe_path)
        self.ffmpeg_full_exe_path = ffmpeg_exe_path 
        # --- [수정된 부분 끝] ---

        self.output_template = output_template; self.quality_format = quality_format
        self.bandwidth_limit = bandwidth_limit
        
        # --- [추가된 부분 시작] ---
        self.download_subtitles = download_subtitles
        self.embed_subtitles = embed_subtitles
        self.subtitle_format = subtitle_format
        # --- [추가된 부분 끝] ---
        
        self.process: Optional[subprocess.Popen] = None
        self._stop_flag = False; self._current_component: str = "비디오"; self._final_filepath: str = ""
        self._metadata: Dict = {}

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
        try: is_successful = self._execute_download()
        except Exception as e:
            is_successful = False
            log_msg = f"다운로드 스레드 예외 발생: {e}"
            self.progress.emit(self.url, {"status": "오류", "log": log_msg})
        self.finished.emit(self.url, is_successful, self._final_filepath if is_successful else "", self._metadata)

    # --- [신규 메서드 시작] ---
    def _convert_vtt_to_srt(self, vtt_filepath: Path):
        """FFmpeg를 사용하여 VTT 파일을 SRT 파일로 변환하고 원본 VTT를 삭제합니다."""
        if not vtt_filepath.exists():
            self.progress.emit(self.url, {"log": f"[오류] SRT 변환 대상 VTT 파일을 찾지 못함: {vtt_filepath}"})
            return

        srt_filepath = vtt_filepath.with_suffix('.srt')
        
        # 이미 SRT 파일이 존재하면 변환을 건너뜁니다.
        if srt_filepath.exists():
            self.progress.emit(self.url, {"log": "SRT 파일이 이미 존재합니다."})
            return

        command = [
            self.ffmpeg_full_exe_path,
            '-y',       # 덮어쓰기
            '-i', str(vtt_filepath),
            str(srt_filepath)
        ]
        
        try:
            proc = subprocess.run(command, capture_output=True, text=True, startupinfo=get_startupinfo(), timeout=15)
            if proc.returncode == 0:
                self.progress.emit(self.url, {"log": "자막을 SRT로 변환했습니다."})
                try:
                    vtt_filepath.unlink() # 원본 VTT 파일 삭제
                except OSError as e:
                    self.progress.emit(self.url, {"log": f"[오류] 원본 VTT 파일 삭제 실패: {e}"})
            else:
                self.progress.emit(self.url, {"log": f"[오류] SRT 변환 실패: {proc.stderr}"})
        except Exception as e:
            self.progress.emit(self.url, {"log": f"[오류] SRT 변환 중 예외 발생: {e}"})
    # --- [신규 메서드 끝] ---

    def _execute_download(self) -> bool:
        self._metadata = self._get_metadata() or {}
        if not self._metadata:
            self.progress.emit(self.url, {"status": "오류", "log": "메타데이터를 가져올 수 없습니다."}); return False

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
                self._parse_line(line)
        if self._stop_flag: return False
        rc = self.process.wait(timeout=5) if self.process else 1
        
        # 최종 파일 경로가 존재하는지 다시 한번 확인
        if not os.path.exists(self._final_filepath):
             # self.log.emit(f"[오류] 최종 파일이 지정된 경로에 없습니다: {self._final_filepath}")
             # self.log가 없으므로 progress.emit 사용
             self.progress.emit(self.url, {"log": f"[오류] 최종 파일이 지정된 경로에 없습니다: {self._final_filepath}"})


        success = (rc == 0) and os.path.exists(self._final_filepath)
        
        # --- [추가된 부분 시작] ---
        # SRT 변환 로직 (다운로드 성공 시)
        if success and self.download_subtitles and not self.embed_subtitles and self.subtitle_format == 'srt':
            self.progress.emit(self.url, {"status": "자막 변환 중 (SRT)..."})
            # yt-dlp는 일본어 자막을 .ja.vtt로 저장합니다.
            vtt_path = Path(self._final_filepath).with_suffix('.ja.vtt')
            self._convert_vtt_to_srt(vtt_path)
        # --- [추가된 부분 끝] ---

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
            "--ffmpeg-location", self.ffmpeg_path_dir, # --- [수정] ---
            "-o", final_filepath,
            "--retries", "10", "--fragment-retries", "10", "--force-overwrites", "--no-keep-fragments",
            "--no-check-certificate", "--windows-filenames", "--no-cache-dir", "--abort-on-error",
            "--add-header", "Accept-Language:ja-JP", "--progress", "--encoding", "utf-8", "--newline",
            
            # --- [수정된 부분 시작] ---
            # 하드코딩된 자막 옵션 삭제
            # "--write-subs", "--sub-format", "vtt", "--embed-subs", 
            # --- [수정된 부분 끝] ---
            
            "-f", self.quality_format,
            "--merge-output-format", "mp4",
        ]
        
        # --- [추가된 부분 시작] ---
        # 설정에 따른 자막 옵션 추가
        if self.download_subtitles:
            command.append("--write-subs")
            command.append("--sub-langs")
            command.append("ja") # 일본어 자막으로 고정
            
            if self.embed_subtitles:
                # 1. 병합(Embed) 옵션이 켜진 경우
                command.append("--embed-subs")
            else:
                # 2. 별도 파일 저장 (SRT 변환을 위해 VTT로 고정)
                command.append("--sub-format")
                command.append("vtt")
        else:
            # 3. 자막 다운로드 OFF
            command.append("--no-write-subs")
        # --- [추가된 부분 끝] ---

        if self.bandwidth_limit and self.bandwidth_limit != "0": command.extend(["-r", self.bandwidth_limit])
        return command

    def _parse_line(self, line: str):
        line = (line or "").strip()
        if not line: return
        payload: Dict[str, Any] = {}
        log_keywords = ["Merging formats into", "Embedding subtitles", "[error]", "ERROR:"]
        if any(keyword in line for keyword in log_keywords): payload["log"] = line
        
        # yt-dlp가 최종 파일 경로를 알리는 로그 파싱
        # 예: [Merger] Merging formats into "C:\...\video.mp4"
        m_merger = re.search(r"\[Merger\] Merging formats into \"(.+)\"", line)
        if m_merger:
            self._final_filepath = m_merger.group(1)

        if "[download] Destination:" in line:
            # 최종 파일 경로가 아직 설정되지 않았을 경우, 임시로 설정
            if not self._final_filepath:
                self._final_filepath = line.split("Destination:", 1)[1].strip()
            
            destination_path = line.split("Destination:", 1)[1].lower()
            if ".m4a" in destination_path or "audio" in destination_path: self._current_component = "오디오"
            else: self._current_component = "비디오"
        
        m_progress = re.search(r"\[download\]\s+([0-9.]+)% of.*?at (.*?/s)\s+ETA\s+(.*)", line)
        if m_progress:
            payload.update({"status": "다운로드 중", "percent": float(m_progress.group(1)), "speed": m_progress.group(2),
                            "eta": m_progress.group(3), "component": self._current_component})
        
        if "Merging formats" in line: payload["status"] = "후처리 중 (병합)"
        elif "Embedding subtitles" in line: payload["status"] = "후처리 중 (자막)"
        
        if payload: self.progress.emit(self.url, payload)