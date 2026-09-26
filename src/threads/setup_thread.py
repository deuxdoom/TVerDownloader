import os
import hashlib
import shutil
import zipfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from PyQt6.QtCore import QThread, pyqtSignal

from src.i18n import t
from src.utils import (expected_sha256, github_api_headers, is_rate_limited,
                       rate_limit_message)


def describe_network_error(error: BaseException, host: str) -> str:
    """통신 예외를 사람이 읽을 한 줄로 줄인다. 예외 원문은 로그에 싣지 않는다.

    requests는 `HTTPSConnectionPool(host=..., port=443): Max retries exceeded ...
    (Caused by NameResolutionError(...))`처럼 두 줄 가까운 원문을 내놓아, 인터넷이 끊겼다는
    한마디가 그 안에 묻혔다(사용자 지적, 2026-09-22). 종류만 가르고 원문은 버린다.
    """
    import requests

    text = str(error)
    if isinstance(error, requests.exceptions.SSLError):
        return t("setup.net_ssl", host=host)
    if isinstance(error, requests.exceptions.Timeout):
        return t("setup.net_timeout", host=host)
    if ("NameResolutionError" in text or "getaddrinfo failed" in text
            or "Name or service not known" in text or "11001" in text):
        return t("setup.net_dns", host=host)
    if isinstance(error, requests.exceptions.ConnectionError):
        return t("setup.net_connect", host=host)
    return t("setup.net_other", host=host, name=type(error).__name__)


def is_unreachable(error: BaseException) -> bool:
    """서버 쪽 문제가 아니라 이쪽 회선이 닿지 않는 실패인가. 그렇다면 다음 확인도 실패한다."""
    import requests

    return isinstance(error, (requests.exceptions.ConnectionError, requests.exceptions.Timeout))


class SetupThread(QThread):
    """yt-dlp와 ffmpeg 실행 파일 경로를 찾아 준비 상태를 알리는 스레드.

    **받아 둔 것이 있으면 새 버전 확인은 덤이다.** 켤 때 인터넷이 없으면 예전에는 도구마다
    3초·6초를 쉬며 다시 걸어, 그동안 입력이 잠긴 채 로그에 예외 원문이 쌓였다. 지금은 한 번
    물어보고 안 되면 쓰던 것으로 곧장 넘어간다. 다시 거는 것은 파일이 없을 때와 사용자가
    직접 업데이트를 누른 때뿐이다(`manual`).
    """
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
    API_TIMEOUT = (5, 10)
    """(연결, 읽기) 제한 시간. 연결을 짧게 두는 것은 응답 없는 회선에서 준비가 오래 묶이지 않게 하려는 것이다."""

    def __init__(self, parent=None, manual: bool = False):
        super().__init__(parent)
        self.manual = manual
        self._unreachable = False

    def run(self):
        try:
            ytdlp_exe_path = self._update_ytdlp()
            ffmpeg_exe_path = self._update_ffmpeg()
            if ytdlp_exe_path and ffmpeg_exe_path:
                self.finished.emit(True, str(ytdlp_exe_path), str(ffmpeg_exe_path))
            else:
                self.finished.emit(False, "", "")
        except Exception as e:
            self.log.emit(t("setup.fatal", error=e))
            self.finished.emit(False, "", "")

    def _get_api_info(self, url: str, required: bool = True) -> Optional[dict]:
        """GitHub 릴리스 정보를 받아 온다. 실패하면 None.

        raise_for_status()로 묶으면 한도 초과가 네트워크 오류와 구분되지 않아, 풀리지도
        않을 상태를 붙잡고 재시도하게 된다. 그래서 상태 코드를 먼저 갈라 본다.
        `required`는 받아 둔 파일이 없어 이 답이 꼭 있어야 한다는 뜻이다.
        """
        import requests

        if self._unreachable and not required:
            self.log.emit(t("setup.skip_unreachable"))
            return None
        host = urlparse(url).hostname or url
        attempts = self.API_MAX_ATTEMPTS if (required or self.manual) else 1
        headers = github_api_headers(self.API_USER_AGENT)

        for attempt in range(1, attempts + 1):
            try:
                response = requests.get(url, headers=headers, timeout=self.API_TIMEOUT)
            except requests.exceptions.RequestException as e:
                reason = describe_network_error(e, host)
                if attempt < attempts:
                    self._retry_pause(attempt, attempts, reason)
                    continue
                self._unreachable = is_unreachable(e)
                self.log.emit(t("setup.api_failed", error=reason))
                return None

            if is_rate_limited(response):
                self.log.emit(t("setup.api_error_prefix", message=rate_limit_message(response)))
                return None

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as e:
                    self.log.emit(t("setup.api_parse_failed", error=e))
                    return None

            if response.status_code < 500 or attempt >= attempts:
                self.log.emit(t("setup.api_status", status=response.status_code))
                return None

            self._retry_pause(attempt, attempts,
                              t("setup.server_error", status=response.status_code))

        return None

    def _retry_pause(self, attempt: int, attempts: int, reason: str):
        """지수 백오프만큼 쉰다. 마지막 시도 뒤에는 부르지 않는다."""
        delay = self.API_RETRY_BASE_DELAY * (2 ** (attempt - 1))
        self.log.emit(t("setup.retry_in", reason=reason, seconds=delay,
                        attempt=attempt + 1, total=attempts))
        self.msleep(delay * 1000)

    def _download_headers(self) -> dict:
        """에셋 내려받기용 헤더. 파일을 받는 요청이라 JSON Accept는 붙이지 않는다."""
        return {"User-Agent": self.API_USER_AGENT}

    PARTIAL_SUFFIX = ".part"
    """다 받기 전까지 쓰는 이름. 옮기고 나면 남지 않는다."""

    def _download_and_place(self, url: str, target_path: Path,
                            expected_digest: Optional[str] = None) -> bool:
        """받아서 제자리에 놓는다. **다 받은 뒤에 옮긴다.**

        목적지에 바로 쓰면 중간에 끊겼을 때 잘린 exe가 그 이름으로 남는다. 다음 실행에서
        GitHub API까지 실패하면 파일이 있는지만 보고 그것을 정상으로 넘겨, 받는 것마다
        알 수 없는 이유로 실패한다. 저장소의 다른 쓰기(queue_store·favorites_store·
        history_store)가 모두 임시 파일에 쓰고 os.replace로 바꾸는 것과 같은 이유다.

        ffmpeg 쪽(_download_and_unzip)은 이렇게 하지 않아도 된다 - 임시 폴더에 받고
        다음 실행에서 그 폴더를 통째로 지우므로 잘린 zip이 남지 않는다.
        """
        import requests

        self.log.emit(t("setup.download_start", url=url))
        target_path.parent.mkdir(parents=True, exist_ok=True)
        partial = target_path.with_name(target_path.name + self.PARTIAL_SUFFIX)
        digest = hashlib.sha256()
        try:
            with requests.get(url, headers=self._download_headers(),
                              stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(partial, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                        digest.update(chunk)
            if expected_digest and digest.hexdigest() != expected_digest:
                raise ValueError(t("setup.digest_mismatch"))
            os.replace(partial, target_path)
        except BaseException:
            try:
                partial.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return True

    def _download_and_unzip(self, url: str, target_dir: Path, file_name: str,
                            expected_digest: Optional[str] = None) -> bool:
        import requests

        target_dir.mkdir(parents=True, exist_ok=True)
        zip_path = target_dir / file_name
        digest = hashlib.sha256()
        self.log.emit(t("setup.download_start", url=url))
        with requests.get(url, headers=self._download_headers(), stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    digest.update(chunk)
        if expected_digest and digest.hexdigest() != expected_digest:
            zip_path.unlink(missing_ok=True)
            raise ValueError(t("setup.digest_mismatch"))
        self.log.emit(t("setup.extracting", path=zip_path))
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(target_dir)
        try:
            os.remove(zip_path)
        except Exception:
            pass
        return True

    def _keep_installed(self, path: Path, name: str) -> Optional[Path]:
        """새 버전을 못 받았을 때 쓰던 것으로 넘어간다. 없으면 None."""
        if path.exists():
            self.log.emit(t("setup.keep_installed", name=name))
            return path
        return None

    def _update_ytdlp(self) -> Optional[Path]:
        self.log.emit(t("setup.ytdlp_check"))
        ytdlp_exe_path = self.BIN_DIR / "yt-dlp.exe"
        version_file = self.BIN_DIR / "ytdlp_version.txt"

        info = self._get_api_info(self.YTDLP_API_URL, required=not ytdlp_exe_path.exists())
        if not info:
            return self._keep_installed(ytdlp_exe_path, "yt-dlp")

        latest = info.get("tag_name")
        current = version_file.read_text().strip() if version_file.exists() else None

        if latest == current and ytdlp_exe_path.exists():
            self.log.emit(t("setup.ytdlp_up_to_date", version=latest))
            return ytdlp_exe_path

        asset = next((a for a in info.get("assets", []) if isinstance(a, dict)
                      and a.get("name", "").endswith(".exe")
                      and "yt-dlp" in a.get("name", "").lower()), None)
        if not asset:
            self.log.emit(t("setup.ytdlp_no_asset"))
            return ytdlp_exe_path if ytdlp_exe_path.exists() else None

        try:
            digest = expected_sha256(asset)
            if digest:
                self._download_and_place(asset["browser_download_url"], ytdlp_exe_path, digest)
            else:
                self._download_and_place(asset["browser_download_url"], ytdlp_exe_path)
        except Exception as error:
            if not ytdlp_exe_path.exists():
                raise
            self.log.emit(t("setup.ytdlp_replace_failed", error=error))
            return ytdlp_exe_path
        version_file.write_text(latest or "")
        self.log.emit(t("setup.ytdlp_done"))
        return ytdlp_exe_path

    def _update_ffmpeg(self) -> Optional[Path]:
        """FFmpeg를 최신으로 갈아 끼운다. 실패하면 쓰던 것을 그대로 돌려준다.

        **갈아 끼우기는 지우고 옮기는 것이 아니라 os.replace다.** 먼저 지우면 그 다음
        이동이 막혔을 때(백신이 갓 푼 exe를 잡고 있으면 실제로 난다) 쓰던 도구까지
        잃는다. 자동 업데이트가 exe를 바꿀 때 백업으로 옮겨 두는 것과 같은 판단이다.
        """
        self.log.emit(t("setup.ffmpeg_check"))
        ffmpeg_exe_path = self.BIN_DIR / "ffmpeg.exe"
        ffprobe_exe_path = self.BIN_DIR / "ffprobe.exe"
        version_file = self.BIN_DIR / "ffmpeg_version.txt"
        installed = ffmpeg_exe_path.exists() and ffprobe_exe_path.exists()

        info = self._get_api_info(self.FFMPEG_API_URL, required=not installed)
        if not info:
            return self._keep_installed(ffmpeg_exe_path, "FFmpeg") if installed else None

        latest = info.get("tag_name")
        current = version_file.read_text().strip() if version_file.exists() else None

        if latest == current and installed:
            self.log.emit(t("setup.ffmpeg_up_to_date", version=latest))
            return ffmpeg_exe_path

        asset = next(
            (a for a in info.get("assets", []) if isinstance(a, dict)
             and self.FFMPEG_ASSET_KEYWORD in a.get("name", "").lower()
             and a.get("name", "").endswith(self.FFMPEG_ASSET_EXTENSION)),
            None,
        )
        if not asset:
            self.log.emit(t("setup.ffmpeg_no_asset"))
            return ffmpeg_exe_path if ffmpeg_exe_path.exists() else None

        temp_dir = self.BIN_DIR / "ffmpeg_temp"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

        try:
            digest = expected_sha256(asset)
            if digest:
                self._download_and_unzip(asset["browser_download_url"], temp_dir,
                                         asset["name"], digest)
            else:
                self._download_and_unzip(asset["browser_download_url"], temp_dir, asset["name"])
        except Exception as error:
            if not installed:
                raise
            self.log.emit(t("setup.ffmpeg_replace_failed", error=error))
            return ffmpeg_exe_path

        extracted_root = next((p for p in temp_dir.iterdir() if p.is_dir()), None)
        if not extracted_root:
            self.log.emit(t("setup.ffmpeg_no_folder"))
            return ffmpeg_exe_path if ffmpeg_exe_path.exists() else None

        source_ffmpeg = extracted_root / "bin" / "ffmpeg.exe"
        source_ffprobe = extracted_root / "bin" / "ffprobe.exe"

        if source_ffmpeg.exists() and source_ffprobe.exists():
            self.BIN_DIR.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(str(source_ffmpeg), str(ffmpeg_exe_path))
                os.replace(str(source_ffprobe), str(ffprobe_exe_path))
            except OSError as error:
                self.log.emit(t("setup.ffmpeg_replace_failed", error=error))
                return ffmpeg_exe_path if ffmpeg_exe_path.exists() else None

            self.log.emit(t("setup.ffmpeg_moved",
                            names=f"{ffmpeg_exe_path.name} / {ffprobe_exe_path.name}"))
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
            version_file.write_text(latest or "")
            self.log.emit(t("setup.ffmpeg_done"))
            return ffmpeg_exe_path
        else:
            self.log.emit(t("setup.ffmpeg_missing"))
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
            return ffmpeg_exe_path if ffmpeg_exe_path.exists() else None
