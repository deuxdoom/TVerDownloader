"""새 버전 파일을 내려받고 확인하고 펴는 스레드.

35MB쯤 되는 파일이라 창에서 그냥 받으면 그동안 앱이 굳는다. 받는 중에 그만둘
수 있어야 하는 것도 이유다 — 회선이 느린 날 몇 분씩 붙잡혀 있으면 앱이 죽은
것으로 보인다.

**여기서는 아무것도 갈아 끼우지 않는다.** 받고, 깨지지 않았는지 보고, 앱 폴더
안 작업 폴더에 펴 두는 데까지다. 실제 교체는 본체가 닫힌 뒤 배치가 한다
(src/self_update.py). 나눠 둔 덕분에 이 단계에서 무엇이 실패해도 지금 쓰는
버전은 그대로다.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from src import self_update
from src.utils import github_api_headers, is_rate_limited, rate_limit_message

CHUNK_SIZE = 256 * 1024
"""한 번에 읽어 들이는 크기. 진행률을 부드럽게 하면서 호출 횟수는 줄이는 선."""

DOWNLOAD_TIMEOUT = 30
"""응답이 끊긴 것으로 볼 때까지의 시간(초).

받는 도중 회선이 죽으면 여기서 끊고 알린다. 조회와 달리 다시 걸지 않는다 —
사용자가 보고 있는 작업이라 조용히 몇 분을 더 쓰는 것보다 알리는 편이 낫다.
"""


class UpdateDownloadThread(QThread):
    """zip 하나를 받아 확인하고 작업 폴더에 펴 놓는다."""

    progress = pyqtSignal(int, str)
    """(0~100, 지금 하는 일). 100이어도 끝난 것은 아니고 finished가 결론이다."""

    finished = pyqtSignal(bool, str)
    """(성공 여부, 실패 사유). 성공이면 사유는 빈 문자열."""

    DOWNLOAD_SHARE = 85
    """진행률에서 내려받기가 차지하는 몫.

    나머지는 확인과 압축 풀기다. 받는 데 걸리는 시간이 압도적이라 그만큼 준다.
    """

    def __init__(self, asset_url: str, work_dir: Path, parent=None):
        super().__init__(parent)
        self.asset_url = asset_url
        self.work_dir = Path(work_dir)
        self._stop_flag = False

    def stop(self):
        """받기를 그만둔다. 다음 덩이를 읽을 때 빠져나온다."""
        self._stop_flag = True

    def run(self):
        try:
            ok, reason = self._execute()
        except Exception as error:
            ok, reason = False, f"예상치 못한 오류: {error}"
        self.finished.emit(ok, reason)

    def _execute(self) -> tuple[bool, str]:
        try:
            import requests
        except ImportError:
            return False, "requests 모듈이 없어 내려받을 수 없습니다."

        zip_path = self.work_dir / "package.zip"
        self.progress.emit(0, "새 버전을 내려받는 중...")

        try:
            response = requests.get(
                self.asset_url, headers=github_api_headers("TVerDownloader-SelfUpdate"),
                stream=True, timeout=DOWNLOAD_TIMEOUT)
        except Exception as error:
            return False, f"내려받기를 시작하지 못했습니다: {error}"

        with response:
            if is_rate_limited(response):
                return False, rate_limit_message(response)
            if response.status_code != 200:
                return False, f"내려받기에 실패했습니다(HTTP {response.status_code})."

            total = int(response.headers.get("Content-Length") or 0)
            received = 0
            try:
                with open(zip_path, "wb") as out:
                    for chunk in response.iter_content(CHUNK_SIZE):
                        if self._stop_flag:
                            return False, ""
                        if not chunk:
                            continue
                        out.write(chunk)
                        received += len(chunk)
                        if total:
                            percent = int(received * self.DOWNLOAD_SHARE / total)
                            self.progress.emit(
                                percent,
                                f"새 버전을 내려받는 중... "
                                f"{received // (1024 * 1024)}MB / {total // (1024 * 1024)}MB")
            except Exception as error:
                return False, f"내려받는 중 문제가 생겼습니다: {error}"

        if self._stop_flag:
            return False, ""

        self.progress.emit(self.DOWNLOAD_SHARE, "받은 파일을 확인하는 중...")
        ok, root, message = self_update.verify_package(zip_path)
        if not ok:
            return False, message

        self.progress.emit(self.DOWNLOAD_SHARE + 3, "새 버전을 준비하는 중...")
        span = 100 - self.DOWNLOAD_SHARE - 3

        def on_extract(index: int, count: int):
            self.progress.emit(self.DOWNLOAD_SHARE + 3 + int(index * span / count),
                               "새 버전을 준비하는 중...")

        try:
            self_update.extract_payload(
                zip_path, root, self.work_dir / self_update.NEW_DIR_NAME, on_extract)
        except Exception as error:
            return False, f"압축을 푸는 중 문제가 생겼습니다: {error}"

        if self._stop_flag:
            return False, ""

        if not self_update.staged_payload_ok(self.work_dir):
            return False, "준비된 파일이 온전하지 않아 교체를 시작하지 않았습니다."

        try:
            zip_path.unlink()
        except OSError:
            pass

        self.progress.emit(100, "준비를 마쳤습니다.")
        return True, ""
