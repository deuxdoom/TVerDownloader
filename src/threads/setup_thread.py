import os
import shutil
import zipfile
from pathlib import Path
from typing import Optional

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from src.utils import github_api_headers, is_rate_limited, rate_limit_message

class SetupThread(QThread):
    """yt-dlp와 ffmpeg 실행 파일 경로를 찾아 준비 상태를 알리는 스레드."""
    log = pyqtSignal(str)
    finished = pyqtSignal(bool, str, str)

    BIN_DIR = Path("bin")
    YTDLP_API_URL = "https://api.github.com/repos/yt-dlp/yt-dlp-nightly-builds/releases/latest"
    FFMPEG_API_URL = "https://api.github.com/repos/GyanD/codexffmpeg/releases/latest"
    FFMPEG_ASSET_KEYWORD = "essentials"
    FFMPEG_ASSET_EXTENSION = ".zip"

    API_USER_AGENT = "TVerDownloader-Setup"
    API_MAX_ATTEMPTS = 3
    API_RETRY_BASE_DELAY = 3

    def run(self):
        try:
            ytdlp_exe_path = self._update_ytdlp()
            ffmpeg_exe_path = self._update_ffmpeg()
            if ytdlp_exe_path and ffmpeg_exe_path:
                self.finished.emit(True, str(ytdlp_exe_path), str(ffmpeg_exe_path))
            else:
                self.finished.emit(False, "", "")
        except Exception as e:
            self.log.emit(f"[치명적 오류] 설정 중 예외 발생: {e}")
            self.finished.emit(False, "", "")

    def _get_api_info(self, url: str) -> Optional[dict]:
        """GitHub 릴리스 정보를 받아 온다. 실패하면 None.

        raise_for_status()로 묶어 RequestException 하나로 잡으면 한도 초과가
        네트워크 오류와 구분되지 않아, 풀리지도 않을 상태를 붙잡고 재시도하게
        된다. 그래서 상태 코드를 먼저 갈라 보고 예외는 그다음에 다룬다.
        """
        headers = github_api_headers(self.API_USER_AGENT)

        for attempt in range(1, self.API_MAX_ATTEMPTS + 1):
            try:
                response = requests.get(url, headers=headers, timeout=10)
            except requests.exceptions.RequestException as e:
                if not self._retry_pause(attempt, f"호출 실패: {e}"):
                    self.log.emit(f"[오류] GitHub API 호출 실패: {e}")
                    return None
                continue

            if is_rate_limited(response):
                self.log.emit(f"[오류] {rate_limit_message(response)}")
                return None

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as e:
                    self.log.emit(f"[오류] GitHub API 응답을 해석하지 못했습니다: {e}")
                    return None

            if response.status_code < 500:
                self.log.emit(f"[오류] GitHub API가 {response.status_code}로 응답했습니다.")
                return None

            if not self._retry_pause(attempt, f"서버 오류 {response.status_code}"):
                self.log.emit(f"[오류] GitHub API가 {response.status_code}로 응답했습니다.")
                return None

        return None

    def _retry_pause(self, attempt: int, reason: str) -> bool:
        """재시도 여지가 남았으면 지수 백오프만큼 쉬고 True를 돌려준다.

        마지막 시도였다면 쉬지 않고 False. 호출부가 실패를 기록하고 끝낸다.
        """
        if attempt >= self.API_MAX_ATTEMPTS:
            return False
        delay = self.API_RETRY_BASE_DELAY * (2 ** (attempt - 1))
        self.log.emit(f" ... GitHub API {reason}. {delay}초 후 재시도합니다"
                      f" ({attempt + 1}/{self.API_MAX_ATTEMPTS}).")
        self.msleep(delay * 1000)
        return True

    def _download_headers(self) -> dict:
        """에셋 내려받기용 헤더.

        API가 아니라 파일을 받는 요청이라 JSON Accept는 붙이지 않는다.
        User-Agent는 GitHub이 모든 요청에 권장한다.
        """
        return {"User-Agent": self.API_USER_AGENT}

    def _download_and_place(self, url: str, target_path: Path) -> bool:
        self.log.emit(f" -> 다운로드 시작: {url}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, headers=self._download_headers(), stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(target_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return True

    def _download_and_unzip(self, url: str, target_dir: Path, file_name: str) -> bool:
        target_dir.mkdir(parents=True, exist_ok=True)
        zip_path = target_dir / file_name
        self.log.emit(f" -> 다운로드 시작: {url}")
        with requests.get(url, headers=self._download_headers(), stream=True, timeout=60) as r:
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

    def _update_ytdlp(self) -> Optional[Path]:
        self.log.emit("[1] yt-dlp.exe 최신 버전 확인 중...")
        ytdlp_exe_path = self.BIN_DIR / "yt-dlp.exe"
        version_file = self.BIN_DIR / "ytdlp_version.txt"

        info = self._get_api_info(self.YTDLP_API_URL)
        if not info:
            return ytdlp_exe_path if ytdlp_exe_path.exists() else None

        latest = info.get("tag_name")
        current = version_file.read_text().strip() if version_file.exists() else None

        if latest == current and ytdlp_exe_path.exists():
            self.log.emit(f" ... yt-dlp가 이미 최신 버전입니다 ({latest}).")
            return ytdlp_exe_path

        asset = next((a for a in info.get("assets", []) if isinstance(a, dict)
                      and a.get("name", "").endswith(".exe")
                      and "yt-dlp" in a.get("name", "").lower()), None)
        if not asset:
            self.log.emit("[오류] yt-dlp.exe 에셋을 찾을 수 없습니다.")
            return ytdlp_exe_path if ytdlp_exe_path.exists() else None

        if self._download_and_place(asset["browser_download_url"], ytdlp_exe_path):
            version_file.write_text(latest or "")
            self.log.emit(" ... yt-dlp.exe 업데이트 완료.")
        return ytdlp_exe_path

    def _update_ffmpeg(self) -> Optional[Path]:
        self.log.emit("[2] FFmpeg 최신 버전 확인 중...")
        ffmpeg_exe_path = self.BIN_DIR / "ffmpeg.exe"
        ffprobe_exe_path = self.BIN_DIR / "ffprobe.exe"
        version_file = self.BIN_DIR / "ffmpeg_version.txt"

        info = self._get_api_info(self.FFMPEG_API_URL)
        if not info:
            return ffmpeg_exe_path if ffmpeg_exe_path.exists() and ffprobe_exe_path.exists() else None

        latest = info.get("tag_name")
        current = version_file.read_text().strip() if version_file.exists() else None

        if latest == current and ffmpeg_exe_path.exists() and ffprobe_exe_path.exists():
            self.log.emit(f" ... FFmpeg가 이미 최신 버전입니다 ({latest}).")
            return ffmpeg_exe_path

        asset = next(
            (a for a in info.get("assets", []) if isinstance(a, dict)
             and self.FFMPEG_ASSET_KEYWORD in a.get("name", "").lower()
             and a.get("name", "").endswith(self.FFMPEG_ASSET_EXTENSION)),
            None,
        )
        if not asset:
            self.log.emit("[오류] FFmpeg .zip 에셋을 찾을 수 없습니다.")
            return ffmpeg_exe_path if ffmpeg_exe_path.exists() else None

        temp_dir = self.BIN_DIR / "ffmpeg_temp"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

        if not self._download_and_unzip(asset["browser_download_url"], temp_dir, asset["name"]):
            return ffmpeg_exe_path if ffmpeg_exe_path.exists() else None

        extracted_root = next((p for p in temp_dir.iterdir() if p.is_dir()), None)
        if not extracted_root:
            self.log.emit("[오류] FFmpeg 압축 해제 후 폴더를 찾을 수 없습니다.")
            return ffmpeg_exe_path if ffmpeg_exe_path.exists() else None

        source_ffmpeg = extracted_root / "bin" / "ffmpeg.exe"
        source_ffprobe = extracted_root / "bin" / "ffprobe.exe"

        if source_ffmpeg.exists() and source_ffprobe.exists():
            self.BIN_DIR.mkdir(parents=True, exist_ok=True)
            if ffmpeg_exe_path.exists(): ffmpeg_exe_path.unlink()
            if ffprobe_exe_path.exists(): ffprobe_exe_path.unlink()
            shutil.move(str(source_ffmpeg), str(ffmpeg_exe_path))
            shutil.move(str(source_ffprobe), str(ffprobe_exe_path))

            self.log.emit(f" -> {ffmpeg_exe_path.name} 및 {ffprobe_exe_path.name} 이동 완료.")
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
            version_file.write_text(latest or "")
            self.log.emit(" ... FFmpeg 업데이트 완료.")
            return ffmpeg_exe_path
        else:
            self.log.emit("[오류] 압축 해제된 파일에서 ffmpeg.exe 또는 ffprobe.exe를 찾을 수 없습니다.")
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
            return ffmpeg_exe_path if ffmpeg_exe_path.exists() else None
