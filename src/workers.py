# -*- coding: utf-8 -*-
# 파일명: src/workers.py
# 역할:
#   - SetupThread: yt-dlp / ffmpeg 최신 버전 확인 및 ./bin 설치/업데이트 (기존 동작 유지)
#   - SeriesParseThread: 시리즈 URL에서 에피소드 URL 목록 추출 (기존 동작 유지)
#   - DownloadThread: 다운로드 실행, 실시간 진행 전달, 즉시 중단(프로세스 트리 종료)
#
# 변경 요약:
#   - DownloadThread.run() 종료 처리 보강: 프로세스 루프 후 반드시 wait()로 종료 코드 회수 → 완료인데 오류로 표기되던 문제 해결
#   - 나머지 로직(도구 다운로드/업뎃, 즉시 중단)은 이전 정상 동작 버전 그대로 유지

from __future__ import annotations

import os
import re
import json
import time
import zipfile
import shutil
import signal
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from src.utils import get_startupinfo


# ============================== SetupThread (기존 동작 유지) ==============================
class SetupThread(QThread):
    log = pyqtSignal(str)
    finished = pyqtSignal(bool, str, str)

    BIN_DIR = Path("bin")
    YTDLP_API_URL = "https://api.github.com/repos/yt-dlp/yt-dlp-nightly-builds/releases/latest"
    FFMPEG_API_URL = "https://api.github.com/repos/GyanD/codexffmpeg/releases/latest"
    FFMPEG_ASSET_KEYWORD = "essentials"
    FFMPEG_ASSET_EXTENSION = ".zip"

    def run(self):
        try:
            ytdlp_exe_path = self._update_ytdlp()
            ffmpeg_exe_path = self._update_ffmpeg()
            if ytdlp_exe_path and ffmpeg_exe_path:
                self.finished.emit(True, ytdlp_exe_path, ffmpeg_exe_path)
            else:
                self.finished.emit(False, "", "")
        except Exception as e:
            self.log.emit(f"[치명적 오류] 설정 중 예외 발생: {e}")
            self.finished.emit(False, "", "")

    def _get_api_info(self, url: str) -> Optional[dict]:
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            self.log.emit(f"[오류] GitHub API 호출 실패: {e}")
            return None

    def _download_and_place(self, url: str, target_path: Path) -> bool:
        self.log.emit(f" -> 다운로드 시작: {url}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(target_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return True

    def _download_and_unzip(self, url: str, target_dir: Path, file_name: str) -> bool:
        target_dir.mkdir(parents=True, exist_ok=True)
        zip_path = target_dir / file_name
        self.log.emit(f" -> 다운로드 시작: {url}")
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        self.log.emit(f" -> 압축 해제 중: {zip_path}")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(target_dir)
        try:
            os.remove(zip_path)
        except Exception:
            pass
        return True

    def _update_ytdlp(self) -> Optional[str]:
        self.log.emit("[1] yt-dlp.exe 최신 버전 확인 중...")
        ytdlp_exe_path = self.BIN_DIR / "yt-dlp.exe"
        version_file = self.BIN_DIR / "ytdlp_version.txt"

        info = self._get_api_info(self.YTDLP_API_URL)
        if not info:
            return str(ytdlp_exe_path) if ytdlp_exe_path.exists() else None

        latest = info.get("tag_name")
        current = version_file.read_text().strip() if version_file.exists() else None

        if latest == current and ytdlp_exe_path.exists():
            self.log.emit(f" ... yt-dlp가 이미 최신 버전입니다 ({latest}).")
            return str(ytdlp_exe_path)

        asset = next((a for a in info.get("assets", []) if isinstance(a, dict)
                      and a.get("name", "").endswith(".exe")
                      and "yt-dlp" in a.get("name", "").lower()), None)
        if not asset:
            self.log.emit("[오류] yt-dlp.exe 에셋을 찾을 수 없습니다.")
            return None

        if self._download_and_place(asset["browser_download_url"], ytdlp_exe_path):
            version_file.write_text(latest or "")
            self.log.emit(" ... yt-dlp.exe 업데이트 완료.")
        return str(ytdlp_exe_path)

    def _update_ffmpeg(self) -> Optional[str]:
        self.log.emit("[2] FFmpeg 최신 버전 확인 중...")
        ffmpeg_exe_path = self.BIN_DIR / "ffmpeg.exe"
        version_file = self.BIN_DIR / "ffmpeg_version.txt"

        info = self._get_api_info(self.FFMPEG_API_URL)
        if not info:
            return str(ffmpeg_exe_path) if ffmpeg_exe_path.exists() else None

        latest = info.get("tag_name")
        current = version_file.read_text().strip() if version_file.exists() else None

        if latest == current and ffmpeg_exe_path.exists():
            self.log.emit(f" ... FFmpeg가 이미 최신 버전입니다 ({latest}).")
            return str(ffmpeg_exe_path)

        asset = next(
            (a for a in info.get("assets", []) if isinstance(a, dict)
             and self.FFMPEG_ASSET_KEYWORD in a.get("name", "").lower()
             and a.get("name", "").endswith(self.FFMPEG_ASSET_EXTENSION)),
            None,
        )
        if not asset:
            self.log.emit("[오류] FFmpeg .zip 에셋을 찾을 수 없습니다.")
            return None

        temp_dir = self.BIN_DIR / "ffmpeg_temp"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

        if not self._download_and_unzip(asset["browser_download_url"], temp_dir, asset["name"]):
            return None

        extracted_root = next((p for p in temp_dir.iterdir() if p.is_dir()), None)
        source = None
        if extracted_root and (extracted_root / "bin" / "ffmpeg.exe").exists():
            source = extracted_root / "bin" / "ffmpeg.exe"
        if source:
            ffmpeg_exe_path.parent.mkdir(parents=True, exist_ok=True)
            if ffmpeg_exe_path.exists():
                try:
                    os.remove(ffmpeg_exe_path)
                except Exception:
                    pass
            shutil.move(str(source), str(ffmpeg_exe_path))
            self.log.emit(f" -> {ffmpeg_exe_path}로 이동 완료.")
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
            version_file.write_text(latest or "")
            self.log.emit(" ... FFmpeg 업데이트 완료.")
            return str(ffmpeg_exe_path)

        self.log.emit("[오류] 압축 해제된 파일에서 ffmpeg.exe를 찾을 수 없습니다.")
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass
        return None


# ============================== SeriesParseThread (기존 동작 유지) ==============================
class SeriesParseThread(QThread):
    log = pyqtSignal(str)
    finished = pyqtSignal(list)  # List[str]

    def __init__(self, series_url: str, ytdlp_exe_path: str):
        super().__init__()
        self.series_url = series_url
        self.ytdlp_exe_path = ytdlp_exe_path

    def run(self):
        try:
            self.log.emit(f"[시리즈] 분석 중: {self.series_url}")
            command = [
                self.ytdlp_exe_path,
                "--flat-playlist",
                "--print", "%(url)s\t%(title)s",
                "--skip-download",
                "--no-warnings",
                self.series_url,
            ]
            startupinfo = get_startupinfo()
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
            out, err = proc.communicate()
            if proc.returncode != 0:
                self.log.emit(f"[오류] 시리즈 분석 실패:\n{(err or '').strip()}")
                self.finished.emit([])
                return

            lines = [l for l in (out or "").splitlines() if "\t" in l]
            pairs = [l.split("\t", 1) for l in lines]
            final_urls: List[str] = []
            self.log.emit(f"시리즈에서 {len(pairs)}개의 항목을 찾았습니다. 예고편 제외 처리 중...")
            for url, title in pairs:
                if "予告" in (title or ""):
                    self.log.emit(f" -> 예고편 제외: {title}")
                    continue
                final_urls.append(url.strip())
            self.log.emit(f"최종 {len(final_urls)}개 에피소드 URL 추출 완료.")
            self.finished.emit(final_urls)
        except Exception as e:
            self.log.emit(f"[오류] 시리즈 분석 중 예외: {e}")
            self.finished.emit([])


# ============================== DownloadThread (즉시 중단 + 종료코드 보강) ==============================
class DownloadThread(QThread):
    progress = pyqtSignal(str, dict)   # (url, payload)
    finished = pyqtSignal(str, bool)   # (url, success)

    def __init__(self, url: str, download_folder: str, ytdlp_exe_path: str,
                 ffmpeg_exe_path: str, filename_format: str, quality_format: str):
        super().__init__()
        self.url = url
        self.download_folder = download_folder
        self.ytdlp_exe_path = ytdlp_exe_path
        self.ffmpeg_exe_path = ffmpeg_exe_path
        self.filename_format = filename_format
        self.quality_format = quality_format

        self.process: Optional[subprocess.Popen] = None
        self._stop_flag = False

    # ----- 즉시 중단 -----
    def stop(self):
        self._stop_flag = True
        try:
            self.progress.emit(self.url, {"status": "취소", "log": "사용자 중단 요청"})
        except Exception:
            pass
        self._kill_process_tree()

    def _kill_process_tree(self):
        p = self.process
        if not p:
            return
        try:
            if os.name == "nt":
                try:
                    p.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                except Exception:
                    pass
                for _ in range(20):
                    if p.poll() is not None:
                        break
                    time.sleep(0.05)
                if p.poll() is None:
                    try:
                        p.terminate()
                    except Exception:
                        pass
                for _ in range(20):
                    if p.poll() is not None:
                        break
                    time.sleep(0.05)
                if p.poll() is None:
                    try:
                        subprocess.run(
                            ["taskkill", "/PID", str(p.pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                        )
                    except Exception:
                        pass
            else:
                try:
                    os.killpg(p.pid, signal.SIGTERM)
                except Exception:
                    pass
                for _ in range(20):
                    if p.poll() is not None:
                        break
                    time.sleep(0.05)
                if p.poll() is None:
                    try:
                        os.killpg(p.pid, signal.SIGKILL)
                    except Exception:
                        pass
        finally:
            self.process = None

    # ----- 실행 -----
    def run(self):
        success = False
        try:
            # 1) 빠른 메타 전달
            self._emit_quick_metadata()

            # 2) yt-dlp 실행
            output_template = os.path.join(self.download_folder, "%(series)s", self.filename_format)
            command: List[str] = [
                self.ytdlp_exe_path, self.url,
                "--ffmpeg-location", os.path.dirname(self.ffmpeg_exe_path),
                "-o", output_template,
                "--retries", "10", "--fragment-retries", "10",
                "--buffer-size", "16K", "--force-overwrites",
                "--no-keep-fragments", "--no-check-certificate", "--no-mtime",
                "--windows-filenames", "--no-cache-dir", "--abort-on-error", "--no-continue",
                "--add-header", "Accept-Language:ja-JP",
                "--console-title", "--progress", "--encoding", "utf-8", "--newline",
                "--write-subs", "--sub-format", "vtt", "--embed-subs",
            ]
            if self.quality_format == "audio_only":
                command += ["-f", "bestaudio", "-x", "--audio-format", "mp3"]
            else:
                command += ["-f", self.quality_format, "--merge-output-format", "mp4"]

            startupinfo = get_startupinfo()

            creationflags = 0
            popen_kwargs = {}
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["start_new_session"] = True

            self.progress.emit(self.url, {"status": "다운로드 중 (비디오/오디오)", "log": "yt-dlp 시작"})
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                startupinfo=startupinfo,
                text=True,
                encoding="utf-8",
                errors="ignore",
                creationflags=creationflags,
                **popen_kwargs,
            )

            current_component = "비디오"
            assert self.process.stdout is not None
            for line in iter(self.process.stdout.readline, ""):
                if self._stop_flag:
                    self._kill_process_tree()
                    break
                line = (line or "").strip()
                if not line:
                    continue

                if "[download] Destination:" in line:
                    lc = line.lower()
                    current_component = "오디오" if ("audio" in lc or ".m4a" in lc) else "비디오"

                m = re.search(r"\[download\]\s+([0-9.]+)% of.*?at (.*?/s)\s+ETA\s+(.*)", line)
                if m:
                    try:
                        percent = float(m.group(1))
                        speed = m.group(2)
                        eta = m.group(3)
                        self.progress.emit(self.url, {
                            "status": f"다운로드 중 ({current_component})",
                            "percent": percent,
                            "speed": speed,
                            "eta": eta,
                            "log": line,
                        })
                    except Exception:
                        pass
                elif "Merging formats" in line or "merging formats" in line.lower() \
                        or "postprocessing" in line.lower() or "Embedding subtitles" in line:
                    self.progress.emit(self.url, {"status": "후처리 중...", "log": line})
                elif "Writing subtitle file" in line:
                    self.progress.emit(self.url, {"status": "자막 처리 중...", "log": line})
                else:
                    self.progress.emit(self.url, {"log": line})

            # 3) 종료 코드 확정 (중요)
            rc = 1
            if self.process:
                try:
                    rc = self.process.wait(timeout=5)  # 종료 코드 반드시 회수
                except Exception:
                    # 타임아웃 등 예외 시 현재 returncode라도 사용
                    rc = self.process.returncode if self.process.returncode is not None else 1

            if self._stop_flag:
                success = False
                self.progress.emit(self.url, {"status": "취소"})
            else:
                success = (rc == 0)
                self.progress.emit(self.url, {"status": "완료" if success else "오류"})
                if success:
                    self.progress.emit(self.url, {"progress": 100})

        except Exception as e:
            success = False
            self.progress.emit(self.url, {"status": "오류", "log": f"다운로드 중 예외: {e}"})
        finally:
            try:
                self.finished.emit(self.url, success)
            except Exception:
                pass

    def _emit_quick_metadata(self):
        try:
            cmd = [self.ytdlp_exe_path, "-J", self.url]
            p = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="ignore",
                startupinfo=get_startupinfo(),
                timeout=20,
            )
            if p.returncode != 0:
                return
            data = json.loads(p.stdout)
            payload = {}
            title = data.get("title")
            if title:
                payload["title"] = title
            thumb_single = data.get("thumbnail")
            thumbs = data.get("thumbnails")
            if thumb_single:
                payload["thumbnail"] = thumb_single
            if thumbs:
                payload["thumbnails"] = thumbs
            if payload:
                self.progress.emit(self.url, payload)
        except Exception:
            pass
