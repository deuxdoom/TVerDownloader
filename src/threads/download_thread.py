import os, re, json, signal, subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any
from PyQt6.QtCore import QThread, pyqtSignal
from src.utils import (get_startupinfo, FILENAME_TITLE_MAX_LENGTH,
                       NO_AUDIO_STATUS, resolve_ffprobe_path,
                       STATUS_DOWNLOADING, STATUS_CANCELING, STATUS_SUBTITLE_CONVERTING,
                       STATUS_MERGING, STATUS_EMBEDDING_SUBS,
                       STATUS_DONE, STATUS_ERROR, STATUS_CANCELED)
from src.i18n import t
from src.threads import ytdlp_run

MAX_PATH_LEN = 250
"""저장 경로 전체에 허용하는 최대 길이.

윈도우 기본 제한은 260자인데, TVer는 음성 쪽 임시 파일명이 본편보다 길어 먼저 걸린다.
"""

MIN_NAME_LEN = 10
"""이름을 줄일 때 남겨 두는 최소 글자 수.

여기까지 줄여도 길면 더 깎지 않는다 - 두 글자짜리 이름은 어느 회차인지 알아볼 수 없다.
"""


def shorten_long_path(full_dir: str, path_without_ext: str, ext: str,
                      max_len: int = MAX_PATH_LEN):
    """경로가 너무 길면 이름을 줄인다. (전체 경로, 줄인 상대 경로)를 돌려준다.

    줄이지 않았으면 둘째 값이 None이다. **회차 이름부터 줄이고 시리즈 폴더는 마지막에
    손댄다** - 폴더를 먼저 깎으면 같은 시리즈가 서로 다른 폴더로 흩어진다. 폴더 구분자는
    그대로 둔다(잃으면 파일이 최상위에 쏟아진다).
    """
    full_path = os.path.join(full_dir, f"{path_without_ext}.{ext}")
    if len(full_path) <= max_len:
        return full_path, None

    sub_dir, sep, base_name = path_without_ext.rpartition('/')

    excess = len(full_path) - max_len
    new_len = max(MIN_NAME_LEN, len(base_name) - excess)
    base_name = base_name[:new_len].strip() or "video"
    path_without_ext = f"{sub_dir}{sep}{base_name}" if sep else base_name
    full_path = os.path.join(full_dir, f"{path_without_ext}.{ext}")

    if len(full_path) > max_len and sep:
        excess = len(full_path) - max_len
        new_dir_len = max(MIN_NAME_LEN, len(sub_dir) - excess)
        sub_dir = sub_dir[:new_dir_len].strip() or "series"
        path_without_ext = f"{sub_dir}{sep}{base_name}"
        full_path = os.path.join(full_dir, f"{path_without_ext}.{ext}")

    return full_path, f"{path_without_ext}.{ext}"


class DownloadThread(QThread):
    progress = pyqtSignal(str, dict)
    finished = pyqtSignal(str, bool, str, dict)

    THUMBNAIL_EMBED_ERROR_HINTS = ("thumbnail embedding", "embedthumbnail",
                                   "embed the thumbnail")
    """썸네일 임베드 실패를 알리는 yt-dlp 출력 조각.

    이 후처리가 실패하면 영상은 병합까지 끝나 멀쩡한데도 yt-dlp가 종료 코드 1로 끝난다.
    """

    THUMBNAIL_SIDECAR_SUFFIXES = (".webp", ".png", ".jpg", ".jpeg")

    FORMAT_COUNT_RE = re.compile(r"Downloading\s+\d+\s+format\(s\):\s*(\S+)")
    """yt-dlp가 무엇을 받을지 알리는 줄. 받기 전에 한 번 나온다.

    `401+251`이면 영상과 소리를 따로 받아 합치고 `18`이면 소리까지 든 하나를 받는다.
    몇 조각을 받는지는 이 줄 말고 미리 알 방법이 없다.
    """

    DEFAULT_PARTS = 2
    """위 줄을 못 봤을 때 가정하는 조각 수.

    TVer는 늘 둘로 준다. 1로 두면 영상만으로 100%가 찼다가 소리를 받으며 0으로 떨어진다.
    """

    COMPONENT_KEYS = ("download.component_video", "download.component_audio")
    """조각을 둘로 나눠 받을 때 화면에 보일 이름의 번역 키. 하나로 받으면 붙이지 않는다.

    문구가 아니라 키를 담는 것은 클래스 상수라 값이 모듈 로드 시점에 굳기 때문이다.
    """

    SIDECAR_WRITE_RE = re.compile(r"^\[info\]\s+Writing\s+.+?\s+to:\s*(.+)$")
    """본편이 아닌 파일을 만들기 직전에 yt-dlp가 내는 줄. 그 경로를 잡아낸다.

    자막도 Destination과 0->100% 진행률을 본편과 똑같이 내면서 본편보다 먼저 온다. 줄 수만
    세면 34KB짜리 자막이 첫 조각 자리를 차지해 진행바가 순식간에 50%까지 찬다. 확장자로
    가리면 사이트마다 규칙이 달라 믿을 수 없어(유튜브는 소리를 .webm으로 준다) 이 줄을 쓴다.
    """

    def __init__(self, url: str, download_folder: str, ytdlp_exe_path: str, ffmpeg_exe_path: str,
                 output_template: str, quality_format: str,
                 download_subtitles: bool, embed_subtitles: bool, subtitle_format: str,
                 ignore_ssl_errors: bool = False, embed_thumbnail: bool = False,
                 preloaded_metadata: Optional[Dict[str, Any]] = None,
                 concurrent_fragments: int = 1,
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
        self.concurrent_fragments = concurrent_fragments

        self.process: Optional[subprocess.Popen] = None
        self._stop_flag = False; self._current_component: str = ""; self._final_filepath: str = ""
        self._parts = self.DEFAULT_PARTS; self._part_index = -1; self._aside = False
        self._sidecar_paths: set = set()
        self._thumbnail_embed_failed = False
        self._metadata: Dict = {}
        self._preloaded_metadata: Dict = preloaded_metadata or {}
        """대기열에서 기다리는 동안 미리 받아 둔 영상 정보.

        있으면 다시 묻지 않는다 - 같은 질의를 같은 조건으로 던져 얻은 것이라 다를 이유가 없다.
        """

    def stop(self):
        if self._stop_flag: return
        self._stop_flag = True
        try: self.progress.emit(self.url, {"status": STATUS_CANCELING, "log": t("download.stop_requested")})
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
            self.progress.emit(self.url, {"status": STATUS_ERROR,
                                          "log": t("download.thread_error", error=e)})
        self.finished.emit(self.url, is_successful, self._final_filepath if is_successful else "", self._metadata)

    def _convert_vtt_to_srt(self, vtt_filepath: Path):
        """VTT를 SRT로 바꾸고 원본 VTT를 지운다.

        **출력 인코딩을 반드시 지정한다** - ffmpeg는 입력 경로를 UTF-8로 stderr에
        내놓는데, TVer 제목은 일본어라 cp949로 읽으면 리더 스레드가 죽고 stderr가
        통째로 None이 된다. 그러면 실패했을 때 이유 대신 `None`이 로그에 찍힌다.
        """
        if not vtt_filepath.exists():
            self.progress.emit(self.url, {"log": t("download.srt_no_vtt", path=vtt_filepath)})
            return

        srt_filepath = vtt_filepath.with_suffix('.srt')

        if srt_filepath.exists():
            self.progress.emit(self.url, {"log": t("download.srt_exists")})
            return

        command = [
            self.ffmpeg_full_exe_path,
            '-y',
            '-i', str(vtt_filepath),
            str(srt_filepath)
        ]

        try:
            proc = subprocess.run(command, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  startupinfo=get_startupinfo(), timeout=15)
            if proc.returncode == 0:
                self.progress.emit(self.url, {"log": t("download.srt_done")})
                try:
                    vtt_filepath.unlink()
                except OSError as e:
                    self.progress.emit(self.url, {"log": t("download.srt_vtt_delete_failed", error=e)})
            else:
                self.progress.emit(self.url, {"log": t("download.srt_failed", error=proc.stderr)})
        except Exception as e:
            self.progress.emit(self.url, {"log": t("download.srt_exception", error=e)})

    def _execute_download(self) -> bool:
        self._metadata = self._preloaded_metadata or self._get_metadata() or {}
        if not self._metadata:
            self.progress.emit(self.url, {"status": STATUS_ERROR, "log": t("download.metadata_failed")}); return False

        self.progress.emit(self.url, {"title": self._metadata.get("title") or t("download.title_unknown"),
                                      "thumbnail": self._metadata.get("thumbnail"),
                                      "duration": self._metadata.get("duration")})
        self._final_filepath = self._build_final_filepath(self._metadata)
        command = self._build_command(self._final_filepath)
        popen_kwargs: Dict[str, Any] = {}
        if os.name == 'nt': popen_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        else: popen_kwargs['start_new_session'] = True

        self.progress.emit(self.url, {"status": STATUS_DOWNLOADING, "log": t("download.ytdlp_start")})
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="ignore", **popen_kwargs)

        if self.process and self.process.stdout:
            for line in iter(self.process.stdout.readline, ""):
                if self._stop_flag: self.progress.emit(self.url, {"status": STATUS_CANCELED}); return False
                self._parse_line(line)
        if self._stop_flag: return False
        rc = self.process.wait(timeout=5) if self.process else 1

        if not os.path.exists(self._final_filepath):
             self.progress.emit(self.url, {"log": t("download.final_missing", path=self._final_filepath)})

        success = (rc == 0) and os.path.exists(self._final_filepath)

        if (not success and self._thumbnail_embed_failed
                and rc != 0 and os.path.exists(self._final_filepath)):
            self.progress.emit(self.url, {"log": t("download.thumbnail_embed_failed")})
            self._cleanup_thumbnail_sidecars()
            success = True

        if success and self.download_subtitles and not self.embed_subtitles and self.subtitle_format == 'srt':
            self.progress.emit(self.url, {"status": STATUS_SUBTITLE_CONVERTING})
            vtt_path = Path(self._final_filepath).with_suffix('.ja.vtt')
            self._convert_vtt_to_srt(vtt_path)

        final_status = STATUS_DONE if success else STATUS_ERROR
        if success and self._has_audio_stream(self._final_filepath) is False:
            final_status = NO_AUDIO_STATUS
            self._warn_missing_audio()

        self.progress.emit(self.url, {"status": final_status, "percent": 100, "final_filepath": self._final_filepath})
        return success

    def _begin_destination(self, path: str):
        """Destination 한 줄을 받아, 지금부터 받는 것이 몇 번째 조각인지 정한다.

        파일 이름이 아니라 순서로 센다 - 유튜브는 소리를 `.f251.webm`으로 내놓아 이름
        규칙으로는 영상으로 잘못 잡힌다. 본편이 아닌 것(자막은 앞, 표지 그림은 뒤)은
        `_aside`를 세워 진행률 보고를 멈춘다.
        """
        if path in self._sidecar_paths or self._part_index >= self._parts - 1:
            self._aside = True
            return
        self._aside = False
        self._part_index += 1
        self._current_component = (t(self.COMPONENT_KEYS[self._part_index])
                                   if self._parts > 1 and self._part_index < len(self.COMPONENT_KEYS)
                                   else "")

    def _overall_percent(self, raw: float) -> Optional[float]:
        """조각 하나의 진행률을 항목 전체 기준(0~100)으로 옮긴다.

        yt-dlp는 조각마다 0->100을 새로 센다. 조각 수를 아는 곳이 여기뿐이라 환산도 여기서
        한다. 본편이 아니거나 첫 조각 전이면 None을 주어 화면이 마지막 값을 지키게 한다.
        """
        if self._aside or self._part_index < 0:
            return None
        span = 100.0 / self._parts
        start = max(0, self._part_index) * span
        return max(0.0, min(100.0, start + span * max(0.0, min(100.0, raw)) / 100.0))

    def _cleanup_thumbnail_sidecars(self):
        """임베드가 실패해 남은 표지 이미지를 지운다. 완료로 처리하는 이상 남길 이유가 없다."""
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
            self.progress.emit(self.url, {"log": t("download.cover_cleaned", names=", ".join(removed))})

    def _has_audio_stream(self, filepath: str) -> Optional[bool]:
        """음성 트랙이 들어 있는지 본다. True/False, 확인 불가면 None.

        None은 '없다'가 아니라 '모른다'는 뜻이다 - 호출부는 통과로 다룬다.
        """
        ffprobe_path = resolve_ffprobe_path(self.ffmpeg_full_exe_path)
        if not ffprobe_path:
            self.progress.emit(self.url, {"log": t("download.no_ffprobe")})
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
            self.progress.emit(self.url, {"log": t("download.ffprobe_run_failed", error=e)})
            return None

        if proc.returncode != 0:
            self.progress.emit(self.url, {"log": t("download.ffprobe_error",
                                                   error=(proc.stderr or "").strip())})
            return None

        return bool(proc.stdout.strip())

    def _warn_missing_audio(self):
        """음성이 빠진 이유를 짐작해 로그에 남긴다.

        TVer는 2025년 3월 사양 변경 이후 영상과 음성을 따로 받아 합치는데, 음성 쪽 임시
        파일명이 길어 경로 제한에 먼저 걸린다. 그러면 yt-dlp는 0으로 끝나고 영상만 남는다.
        """
        length = len(self._final_filepath)
        self.progress.emit(self.url, {"log": (
            t("download.no_audio", path=self._final_filepath) + "\n"
            + t("download.no_audio_hint", length=length))})

    METADATA_TIMEOUT = 60
    """제목·썸네일을 물어보는 데 주는 제한 시간.

    20초일 때는 시리즈 분석과 회선을 나눠 쓰다 여기서 떨어져, 받기도 전에 실패로 끝났다.
    """

    def _get_metadata(self) -> Optional[Dict[str, Any]]:
        """받기 전에 제목·썸네일을 미리 물어본다. 통신이 밀리면 ytdlp_run이 다시 건다."""
        cmd = [self.ytdlp_exe_path, "-J", "--skip-download", *ytdlp_run.network_options()]
        if self.ignore_ssl_errors:
            cmd.append("--no-check-certificate")
        cmd.append(self.url)
        ok, out, err = ytdlp_run.run(cmd, self.METADATA_TIMEOUT, t("download.metadata_label"),
                                     lambda msg: self.progress.emit(self.url, {"log": msg}))
        if not ok:
            self.progress.emit(self.url, {"log": t("download.metadata_error",
                                                   error=(err or "").strip())})
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
        full_path, shortened = shorten_long_path(full_dir, path_without_ext, final_ext)
        if shortened:
            self.progress.emit(self.url, {"log": t("download.path_shortened", name=shortened)})

        return full_path

    def _build_command(self, final_filepath: str) -> List[str]:
        """yt-dlp 명령을 조립한다.

        자막은 임베드와 별도 저장이 배타적이다. --embed-subs 단독이면 자막을 넣고 사이드카를
        지우는데, --write-subs를 함께 주면 남는다. --embed-thumbnail도 같은 규칙이다.
        -N은 1보다 클 때만 붙인다 - 1은 기본값이라 명령줄에만 남아 로그에서 헷갈린다.
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

        if self.concurrent_fragments > 1:
            command += ["-N", str(self.concurrent_fragments)]

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

        m_sidecar = self.SIDECAR_WRITE_RE.match(line)
        if m_sidecar:
            self._sidecar_paths.add(m_sidecar.group(1).strip())

        m_formats = self.FORMAT_COUNT_RE.search(line)
        if m_formats:
            self._parts = max(1, len(m_formats.group(1).split("+")))
            self._part_index = -1; self._aside = False

        if "[download] Destination:" in line:
            destination = line.split("Destination:", 1)[1].strip()
            if not self._final_filepath and destination not in self._sidecar_paths:
                self._final_filepath = destination
            self._begin_destination(destination)

        m_progress = re.search(r"\[download\]\s+([0-9.]+)% of.*?at (.*?/s)\s+ETA\s+(.*)", line)
        if m_progress:
            eta = m_progress.group(3).split("(")[0].strip()
            payload.update({"status": STATUS_DOWNLOADING, "speed": m_progress.group(2),
                            "eta": eta, "component": self._current_component})
            overall = self._overall_percent(float(m_progress.group(1)))
            if overall is not None:
                payload["percent"] = overall

        if "Merging formats" in line: payload["status"] = STATUS_MERGING
        elif "Embedding subtitles" in line: payload["status"] = STATUS_EMBEDDING_SUBS

        if payload: self.progress.emit(self.url, payload)
