import os, re, json, signal, subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any
from PyQt6.QtCore import QThread, pyqtSignal
from src.utils import (get_startupinfo, FILENAME_TITLE_MAX_LENGTH,
                       NO_AUDIO_STATUS, resolve_ffprobe_path)
from src.threads import ytdlp_run

class DownloadThread(QThread):
    progress = pyqtSignal(str, dict)
    finished = pyqtSignal(str, bool, str, dict)

    THUMBNAIL_EMBED_ERROR_HINTS = ("thumbnail embedding", "embedthumbnail",
                                   "embed the thumbnail")
    """썸네일 임베드 실패를 알리는 yt-dlp 출력 조각.

    이 후처리가 실패하면 yt-dlp는 종료 코드 1로 끝난다. 영상 파일은 이미 병합까지
    끝나 멀쩡한데도 그렇다. 표지 그림 하나 때문에 정상 다운로드를 실패로 만들지
    않으려고, 이 경우만 따로 알아본다.
    """

    THUMBNAIL_SIDECAR_SUFFIXES = (".webp", ".png", ".jpg", ".jpeg")

    def __init__(self, url: str, download_folder: str, ytdlp_exe_path: str, ffmpeg_exe_path: str,
                 output_template: str, quality_format: str,
                 download_subtitles: bool, embed_subtitles: bool, subtitle_format: str,
                 ignore_ssl_errors: bool = False, embed_thumbnail: bool = False,
                 parent=None):
        super().__init__(parent)
        self.url = url; self.download_folder = download_folder
        self.ytdlp_exe_path = ytdlp_exe_path

        self.ffmpeg_path_dir = os.path.dirname(ffmpeg_exe_path)
        self.ffmpeg_full_exe_path = ffmpeg_exe_path

        self.output_template = output_template; self.quality_format = quality_format

        self.download_subtitles = download_subtitles
        self.embed_subtitles = embed_subtitles
        self.subtitle_format = subtitle_format
        self.ignore_ssl_errors = ignore_ssl_errors
        self.embed_thumbnail = embed_thumbnail

        self.process: Optional[subprocess.Popen] = None
        self._stop_flag = False; self._current_component: str = "비디오"; self._final_filepath: str = ""
        self._thumbnail_embed_failed = False
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

    def _convert_vtt_to_srt(self, vtt_filepath: Path):
        """FFmpeg를 사용하여 VTT 파일을 SRT 파일로 변환하고 원본 VTT를 삭제합니다."""
        if not vtt_filepath.exists():
            self.progress.emit(self.url, {"log": f"[오류] SRT 변환 대상 VTT 파일을 찾지 못함: {vtt_filepath}"})
            return

        srt_filepath = vtt_filepath.with_suffix('.srt')

        if srt_filepath.exists():
            self.progress.emit(self.url, {"log": "SRT 파일이 이미 존재합니다."})
            return

        command = [
            self.ffmpeg_full_exe_path,
            '-y',
            '-i', str(vtt_filepath),
            str(srt_filepath)
        ]

        try:
            proc = subprocess.run(command, capture_output=True, text=True, startupinfo=get_startupinfo(), timeout=15)
            if proc.returncode == 0:
                self.progress.emit(self.url, {"log": "자막을 SRT로 변환했습니다."})
                try:
                    vtt_filepath.unlink()
                except OSError as e:
                    self.progress.emit(self.url, {"log": f"[오류] 원본 VTT 파일 삭제 실패: {e}"})
            else:
                self.progress.emit(self.url, {"log": f"[오류] SRT 변환 실패: {proc.stderr}"})
        except Exception as e:
            self.progress.emit(self.url, {"log": f"[오류] SRT 변환 중 예외 발생: {e}"})

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

        if not os.path.exists(self._final_filepath):
             self.progress.emit(self.url, {"log": f"[오류] 최종 파일이 지정된 경로에 없습니다: {self._final_filepath}"})

        success = (rc == 0) and os.path.exists(self._final_filepath)

        if (not success and self._thumbnail_embed_failed
                and rc != 0 and os.path.exists(self._final_filepath)):
            self.progress.emit(self.url, {"log": (
                "[알림] 썸네일을 영상에 넣지 못했지만 영상 자체는 정상입니다. "
                "완료로 처리합니다.")})
            self._cleanup_thumbnail_sidecars()
            success = True

        if success and self.download_subtitles and not self.embed_subtitles and self.subtitle_format == 'srt':
            self.progress.emit(self.url, {"status": "자막 변환 중 (SRT)..."})
            vtt_path = Path(self._final_filepath).with_suffix('.ja.vtt')
            self._convert_vtt_to_srt(vtt_path)

        final_status = "완료" if success else "오류"
        if success and self._has_audio_stream(self._final_filepath) is False:
            final_status = NO_AUDIO_STATUS
            self._warn_missing_audio()

        self.progress.emit(self.url, {"status": final_status, "percent": 100, "final_filepath": self._final_filepath})
        return success

    def _cleanup_thumbnail_sidecars(self):
        """임베드가 실패해 남은 표지 이미지를 지운다.

        완료로 처리하는 이상 영상 옆에 쓰지도 않을 그림 파일을 남기지 않는다.
        """
        target = Path(self._final_filepath)
        removed = []
        for suffix in self.THUMBNAIL_SIDECAR_SUFFIXES:
            candidate = target.with_suffix(suffix)
            if not candidate.exists():
                continue
            try:
                candidate.unlink()
                removed.append(candidate.name)
            except OSError:
                pass
        if removed:
            self.progress.emit(self.url, {"log": f"남은 표지 이미지를 정리했습니다: {', '.join(removed)}"})

    def _has_audio_stream(self, filepath: str) -> Optional[bool]:
        """음성 트랙이 들어 있는지 본다. True/False, 확인 불가면 None.

        None은 '없다'가 아니라 '모른다'는 뜻이다. ffprobe가 없거나 실행이 실패했다고
        멀쩡한 다운로드를 실패로 만들면 안 되므로, 호출부는 None을 통과로 다룬다.
        """
        ffprobe_path = resolve_ffprobe_path(self.ffmpeg_full_exe_path)
        if not ffprobe_path:
            self.progress.emit(self.url, {"log": "[알림] ffprobe를 찾지 못해 음성 확인을 건너뜁니다."})
            return None

        command = [
            ffprobe_path, '-v', 'error', '-select_streams', 'a',
            '-show_entries', 'stream=codec_type',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            filepath
        ]
        try:
            proc = subprocess.run(command, capture_output=True, text=True,
                                  encoding="utf-8", errors="ignore",
                                  startupinfo=get_startupinfo(), timeout=20)
        except Exception as e:
            self.progress.emit(self.url, {"log": f"[알림] 음성 확인을 건너뜁니다(ffprobe 실행 실패: {e})."})
            return None

        if proc.returncode != 0:
            self.progress.emit(self.url, {"log": f"[알림] 음성 확인을 건너뜁니다(ffprobe 오류: {(proc.stderr or '').strip()})."})
            return None

        return bool(proc.stdout.strip())

    def _warn_missing_audio(self):
        """음성이 빠진 이유를 짐작해 로그에 남긴다.

        TVer는 2025년 3월 사양 변경 이후 영상과 음성을 따로 내려받아 합치는데,
        음성 쪽 임시 파일명이 더 길어서 Windows 경로 길이 제한에 먼저 걸린다.
        그러면 yt-dlp는 0으로 끝나고 영상만 남아 겉보기에는 성공처럼 보인다.
        """
        length = len(self._final_filepath)
        self.progress.emit(self.url, {"log": (
            f"[오류] 음성 트랙이 없습니다: {self._final_filepath}\n"
            f"저장 경로가 {length}자입니다. TVer는 영상과 음성을 따로 받아 합치는데 "
            f"음성 쪽 임시 파일명이 더 길어, 경로가 길면 음성만 저장에 실패하고 "
            f"영상만 남을 수 있습니다.\n"
            f"저장 폴더를 더 짧은 경로로 옮기거나 설정 > 파일명에서 구성 요소를 줄인 뒤 "
            f"재다운로드해 주세요.")})

    METADATA_TIMEOUT = 60
    """제목·썸네일을 물어보는 데 주는 제한 시간.

    예전에는 20초에 한 번 물어보고 끝이라, 시리즈 분석이 도는 중에 주소를 넣으면
    회선을 나눠 쓰다가 여기서 떨어지고 '메타데이터를 가져올 수 없습니다'로 끝났다.
    실제로 받기도 전에 실패하는 것이라 조회 쪽은 넉넉히 기다린다.
    """

    def _get_metadata(self) -> Optional[Dict[str, Any]]:
        """받기 전에 제목·썸네일을 미리 물어본다.

        통신이 밀리는 순간에 걸리면 다시 건다(ytdlp_run). 여기서 한 번에 포기하면
        다운로드가 시작조차 못 하고 오류 카드로 남는다.
        """
        cmd = [self.ytdlp_exe_path, "-J", "--skip-download", *ytdlp_run.network_options()]
        if self.ignore_ssl_errors:
            cmd.append("--no-check-certificate")
        cmd.append(self.url)
        ok, out, err = ytdlp_run.run(cmd, self.METADATA_TIMEOUT, "영상 정보 확인",
                                     lambda msg: self.progress.emit(self.url, {"log": msg}))
        if not ok:
            self.progress.emit(self.url, {"log": f"[오류] 영상 정보 확인 실패: {(err or '').strip()}"})
            return None
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return None

    def _build_final_filepath(self, metadata: Dict[str, Any]) -> str:
        template, ext = self.output_template.rsplit('.', 1)

        series_title = (metadata.get('series') or metadata.get('playlist_title') or '').strip()
        episode_title = metadata.get('title', 'NA').strip()

        if series_title:
            if episode_title.startswith(series_title):
                episode_title = episode_title[len(series_title):]
            else:
                try:
                    safe_series = re.escape(series_title)
                    match = re.match(r'^' + safe_series, episode_title, re.IGNORECASE)
                    if match:
                         episode_title = episode_title[match.end():]
                except Exception:
                    pass

            episode_title = re.sub(r'^[:\-\s\u3000]+', '', episode_title).strip()

        def replacer(match):
            key = match.group(1)
            if key == 'title':
                return episode_title[:FILENAME_TITLE_MAX_LENGTH]
            elif key == 'series,playlist_title': return series_title
            elif key == 'upload_date>%Y-%m-%d': return (metadata.get('upload_date') or '')[:8]
            else: return str(metadata.get(key, ''))

        path_without_ext = re.sub(r'%\((.*?)\)s', replacer, template)
        path_without_ext = re.sub(r'\s+', ' ', path_without_ext).strip()

        full_dir = os.path.abspath(self.download_folder)
        final_ext = metadata.get('ext', ext)
        full_path = os.path.join(full_dir, f"{path_without_ext}.{final_ext}")

        MAX_PATH_LEN = 250

        if len(full_path) > MAX_PATH_LEN:
            sub_dir, sep, base_name = path_without_ext.rpartition('/')

            excess = len(full_path) - MAX_PATH_LEN
            new_len = max(10, len(base_name) - excess)
            base_name = base_name[:new_len].strip() or "video"
            path_without_ext = f"{sub_dir}{sep}{base_name}" if sep else base_name
            full_path = os.path.join(full_dir, f"{path_without_ext}.{final_ext}")

            if len(full_path) > MAX_PATH_LEN and sep:
                excess = len(full_path) - MAX_PATH_LEN
                new_dir_len = max(10, len(sub_dir) - excess)
                sub_dir = sub_dir[:new_dir_len].strip() or "series"
                path_without_ext = f"{sub_dir}{sep}{base_name}"
                full_path = os.path.join(full_dir, f"{path_without_ext}.{final_ext}")

            self.progress.emit(self.url, {"log": f"[알림] 경로가 너무 길어 이름을 축소했습니다: {path_without_ext}.{final_ext}"})

        return full_path

    def _build_command(self, final_filepath: str) -> List[str]:
        """yt-dlp 명령을 조립한다.

        자막 옵션은 임베드와 별도 저장이 서로 배타적이다. --embed-subs만 주면
        yt-dlp가 자막을 받아 영상에 넣은 뒤 자막 파일을 지우지만, --write-subs를
        함께 주면 "이미 파일이 있다"고 판단해 남겨 둔다. 그래서 임베드를 골랐는데도
        영상 옆에 .ja.vtt가 따라붙던 것이다. 둘을 같이 붙이지 말 것.

        --embed-thumbnail도 같은 규칙을 따른다. 단독으로 주면 썸네일을 받아 넣고
        파일은 지우므로, --write-thumbnail을 함께 붙이지 않는다.
        """
        command: List[str] = [
            self.ytdlp_exe_path, self.url,
            "--ffmpeg-location", self.ffmpeg_path_dir,
            "-o", final_filepath,
            "--retries", "10", "--fragment-retries", "10", "--force-overwrites", "--no-keep-fragments",
            "--windows-filenames", "--no-cache-dir", "--abort-on-error",
            "--add-header", "Accept-Language:ja-JP", "--progress", "--encoding", "utf-8", "--newline",
            "-f", self.quality_format,
            "--merge-output-format", "mp4",
        ]

        if self.ignore_ssl_errors:
            command.append("--no-check-certificate")

        if self.embed_thumbnail:
            command.append("--embed-thumbnail")

        if self.download_subtitles:
            command.append("--sub-langs")
            command.append("ja")

            if self.embed_subtitles:
                command.append("--embed-subs")
            else:
                command.append("--write-subs")
                command.append("--sub-format")
                command.append("vtt")
        else:
            command.append("--no-write-subs")

        return command

    def _parse_line(self, line: str):
        line = (line or "").strip()
        if not line: return
        payload: Dict[str, Any] = {}
        log_keywords = ["Merging formats into", "Embedding subtitles", "[error]", "ERROR:"]
        if any(keyword in line for keyword in log_keywords): payload["log"] = line

        lowered = line.lower()
        if any(hint in lowered for hint in self.THUMBNAIL_EMBED_ERROR_HINTS):
            if "error" in lowered or "unable" in lowered or "not support" in lowered:
                self._thumbnail_embed_failed = True

        m_merger = re.search(r"\[Merger\] Merging formats into \"(.+)\"", line)
        if m_merger:
            self._final_filepath = m_merger.group(1)

        if "[download] Destination:" in line:
            if not self._final_filepath:
                self._final_filepath = line.split("Destination:", 1)[1].strip()

            destination_path = line.split("Destination:", 1)[1].lower()
            if ".m4a" in destination_path or "audio" in destination_path: self._current_component = "오디오"
            else: self._current_component = "비디오"

        m_progress = re.search(r"\[download\]\s+([0-9.]+)% of.*?at (.*?/s)\s+ETA\s+(.*)", line)
        if m_progress:
            eta = m_progress.group(3).split("(")[0].strip()
            payload.update({"status": "다운로드 중", "percent": float(m_progress.group(1)), "speed": m_progress.group(2),
                            "eta": eta, "component": self._current_component})

        if "Merging formats" in line: payload["status"] = "후처리 중 (병합)"
        elif "Embedding subtitles" in line: payload["status"] = "후처리 중 (자막)"

        if payload: self.progress.emit(self.url, payload)
