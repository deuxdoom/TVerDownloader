"""새 버전 파일을 내려받고 확인하고 펴는 스레드.

35MB쯤 되는 파일이라 창에서 받으면 그동안 앱이 굳고, 받는 중에 그만둘 수도 없다.

**여기서는 아무것도 갈아 끼우지 않는다.** 받고, 깨지지 않았는지 보고, 작업 폴더에 펴 두는
데까지다. 교체는 본체가 닫힌 뒤 별도 적용 창이 맡으므로 이 단계에서 실패해도 지금
쓰는 버전은 그대로다.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from src import self_update
from src.i18n import t
from src.ui.update_flow import SpeedMeter
from src.utils import github_api_headers, is_rate_limited, rate_limit_message

CHUNK_SIZE = 256 * 1024
"""한 번에 읽어 들이는 크기. 진행률을 부드럽게 하면서 호출 횟수는 줄이는 선."""

DOWNLOAD_TIMEOUT = 30
"""응답이 끊긴 것으로 볼 때까지의 시간(초).

조회와 달리 다시 걸지 않는다 - 사용자가 보고 있는 작업이라 알리는 편이 낫다.
"""


class UpdateDownloadThread(QThread):
    """zip 하나를 받아 확인하고 작업 폴더에 펴 놓는다."""

    progress = pyqtSignal(int, str)
    """(0~100, 지금 하는 일). 100이어도 끝난 것은 아니고 finished가 결론이다."""

    finished = pyqtSignal(bool, str)
    """(성공 여부, 실패 사유). 성공이면 사유는 빈 문자열."""
    detail = pyqtSignal(dict)
    """속도와 작업 단계 등 새 업데이트 창에 필요한 값."""

    DOWNLOAD_SHARE = 85
    """받기가 확인과 압축 풀기보다 오래 걸리므로 진행률 대부분을 배정한다."""
    SIGNAL_INTERVAL = 0.1
    """진행 신호가 너무 잦으면 창의 배치·그리기가 다운로드를 따라잡지 못한다."""

    def __init__(self, asset_url: str, work_dir: Path, parent=None,
                 expected_digest: Optional[str] = None):
        super().__init__(parent)
        self.asset_url = asset_url
        self.work_dir = Path(work_dir)
        self.expected_digest = expected_digest
        self._stop_flag = False
        self._last_signal = 0.0
        self._meter = SpeedMeter()

    def _report(self, percent: int, message: str, task: str, *,
                received: int = 0, total: int = 0, force: bool = False):
        now = time.monotonic()
        speed = self._meter.add(received, now) if task == "download" else 0.0
        if not force and now - self._last_signal < self.SIGNAL_INTERVAL:
            return
        self._last_signal = now
        self.progress.emit(percent, message)
        self.detail.emit({"received": received, "total": total,
                          "speed_bps": speed,
                          "eta_s": (total - received) / speed if total and speed else None,
                          "task": task, "task_state": "active"})

    def stop(self):
        """받기를 그만둔다. 다음 덩이를 읽을 때 빠져나온다."""
        self._stop_flag = True

    def run(self):
        try:
            ok, reason = self._execute()
        except Exception as error:
            ok, reason = False, t("update.err_unexpected", error=error)
        self.finished.emit(ok, reason)

    def _execute(self) -> tuple[bool, str]:
        try:
            import requests
        except ImportError:
            return False, t("update.err_no_requests")

        zip_path = self.work_dir / "package.zip"
        self._report(0, t("update.downloading"), "download", force=True)

        try:
            response = requests.get(
                self.asset_url, headers=github_api_headers("TVerDownloader-SelfUpdate"),
                stream=True, timeout=DOWNLOAD_TIMEOUT)
        except Exception as error:
            return False, t("update.err_start", error=error)

        with response:
            if is_rate_limited(response):
                return False, rate_limit_message(response)
            if response.status_code != 200:
                return False, t("update.err_http", status=response.status_code)

            total = int(response.headers.get("Content-Length") or 0)
            received = 0
            digest = hashlib.sha256()
            try:
                with open(zip_path, "wb") as out:
                    for chunk in response.iter_content(CHUNK_SIZE):
                        if self._stop_flag:
                            return False, ""
                        if not chunk:
                            continue
                        out.write(chunk)
                        digest.update(chunk)
                        received += len(chunk)
                        if total:
                            percent = int(received * self.DOWNLOAD_SHARE / total)
                            self._report(percent,
                                         t("update.downloading_progress",
                                           done=f"{received // (1024 * 1024)}MB",
                                           total=f"{total // (1024 * 1024)}MB"),
                                         "download", received=received, total=total,
                                         force=received >= total)
            except Exception as error:
                return False, t("update.err_download", error=error)

        if self._stop_flag:
            return False, ""

        self._report(self.DOWNLOAD_SHARE, t("update.verifying"), "verify",
                     received=received, total=total, force=True)
        if self.expected_digest and digest.hexdigest() != self.expected_digest:
            zip_path.unlink(missing_ok=True)
            return False, t("update.err_digest")
        ok, root, message = self_update.verify_package(zip_path)
        if not ok:
            return False, message

        self._report(self.DOWNLOAD_SHARE + 3, t("update.extracting"), "extract",
                     received=received, total=total, force=True)
        span = 100 - self.DOWNLOAD_SHARE - 3

        def on_extract(index: int, count: int):
            self._report(self.DOWNLOAD_SHARE + 3 + int(index * span / count),
                         t("update.extracting"), "extract",
                         received=received, total=total,
                         force=index == count)

        try:
            self_update.extract_payload(
                zip_path, root, self.work_dir / self_update.NEW_DIR_NAME, on_extract)
        except Exception as error:
            return False, t("update.err_extract", error=error)

        if self._stop_flag:
            return False, ""

        if not self_update.staged_payload_ok(self.work_dir):
            return False, t("update.err_incomplete")

        try:
            zip_path.unlink()
        except OSError:
            pass

        self._report(100, t("update.ready"), "extract", received=received,
                     total=total, force=True)
        return True, ""
