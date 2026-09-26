"""업데이트 진행 창.

**닫는 길과 취소가 같은 길이다** - 제목 줄의 X도 `reject()`로 가고, 그것이 받기를 세운 뒤
스레드가 빠져나오기를 기다린다. 창만 닫히고 스레드는 도는 상태가 생기면 다음에 다시
눌렀을 때 같은 폴더에 두 번 풀게 된다.
"""
from __future__ import annotations

import webbrowser
from pathlib import Path

from PyQt6.QtWidgets import QDialog, QVBoxLayout

from src.appicon import get_app_icon
from src.i18n import t
from src import self_update
from src.threads.update_thread import UpdateDownloadThread
from src.ui.update_flow import (UpdateFlowView, fit_window_height, parse_release_highlights,
                                refit_after_show)
from src.window_frame import apply_dialog_frame
from versioninfo import APP_VERSION

DIALOG_WIDTH = 420
"""창 폭. 진행 문구가 파일 크기까지 담아도 한 줄에 떨어지는 값."""


class UpdateProgressDialog(QDialog):
    """확인에서 받기까지 같은 창에 두어 선택 뒤 화면 위치가 바뀌지 않게 한다."""

    def __init__(self, asset_url: str, work_dir: Path | None, latest_tag: str,
                 parent=None, theme: str = "light", expected_digest: str | None = None,
                 *, release: dict | None = None, asset: dict | None = None,
                 pending_count: int = 0, single_button: bool = False,
                 html_url: str = "", log=print):
        super().__init__(parent)
        self.setWindowTitle(t("update.check_title"))
        self.setModal(True)
        self.setFixedWidth(DIALOG_WIDTH)
        self.failure_reason = ""
        self._work_done = False
        self._cancel_requested = False
        self.started_download = False
        self.thread = None
        self.work_dir = Path(work_dir) if work_dir is not None else None
        self.asset_url = asset_url
        self.expected_digest = expected_digest
        self.html_url = html_url
        self.log = log
        release = release or {}
        asset = asset or {}
        self._data = {
            "from_version": APP_VERSION, "to_version": latest_tag.lstrip("vV"),
            "size": asset.get("size", 0),
            "published": str(release.get("published_at", ""))[:10],
            "highlights": parse_release_highlights(str(release.get("body") or "")),
            "pending_count": pending_count, "single_button": single_button,
            "has_digest": bool(expected_digest), "progress": 0,
            "task": "download",
        }
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.view = UpdateFlowView(theme)
        self.view.action.connect(self._action)
        layout.addWidget(self.view)
        apply_dialog_frame(self, theme, resizable=False,
                           icon_name="download")
        getattr(self, "title_bar").setFixedHeight(40)
        getattr(self, "title_bar").icon_label.setPixmap(get_app_icon().pixmap(16, 16))
        if work_dir is None:
            self._set_stage("check")
        else:
            self._begin_download()

    def showEvent(self, event):
        super().showEvent(event)
        refit_after_show(self, recenter=True)

    def _set_stage(self, stage: str):
        position = self.pos()
        self.view.set_state(stage, self._data)
        fit_window_height(self)
        if self.isVisible():
            self.move(position)

    def _begin_download(self):
        self.started_download = True
        self.failure_reason = ""
        self._cancel_requested = False
        self._work_done = False
        self._data.update(progress=0, received=0, total=self._data.get("size", 0),
                          speed_bps=0, eta_s=None, task="download", error="")
        if self.work_dir is None:
            self.work_dir = self_update.prepare_workspace()
            if self.work_dir is None:
                self.failure_reason = (t("update.previous_window_open")
                                       if self_update.previous_window_open()
                                       else t("update.cannot_body"))
                self._data["error"] = self.failure_reason
                self._set_stage("download_failed")
                return
        self._set_stage("downloading")
        self.log(t("log.update_start", tag=self._data["to_version"]))
        self.thread = UpdateDownloadThread(self.asset_url, self.work_dir, self,
                                           expected_digest=self.expected_digest)
        self.thread.progress.connect(self._on_progress)
        self.thread.detail.connect(self._on_detail)
        self.thread.finished.connect(self._on_finished)
        self.thread.start()

    def _action(self, action: str):
        if action == "btn_changelog":
            self.log(t("log.update_open_release", url=self.html_url))
            try:
                webbrowser.open(self.html_url)
            except Exception:
                pass
        elif action == "btn_update_now" and self.view.state == "check":
            self._begin_download()
        elif action == "btn_retry" and self.view.state == "download_failed":
            if self.thread is not None:
                self.thread.wait()
            self_update.cleanup_workspace()
            self.work_dir = None
            self._begin_download()
        elif action == "btn_cancel":
            self._cancel()
        elif action in {"btn_later", "btn_close"}:
            self.reject()

    def _on_progress(self, percent: int, message: str):
        self._data["progress"] = percent

    def _on_detail(self, detail: dict):
        self._data.update(detail)
        self._set_stage("downloading")

    def _on_finished(self, ok: bool, reason: str):
        self.failure_reason = reason
        self._work_done = True
        if self._cancel_requested:
            self.failure_reason = ""
            super().reject()
        elif ok and self.work_dir is not None and self_update.staged_payload_ok(self.work_dir):
            self.accept()
        else:
            if ok:
                reason = t("update.err_incomplete")
                self.failure_reason = reason
            self._data["error"] = reason
            self._set_stage("download_failed")

    def _cancel(self):
        """스레드가 끝나기 전에 창을 없애면 작업 폴더 정리와 압축 풀이 겹친다."""
        if self.thread is None or self._cancel_requested:
            return
        self._cancel_requested = True
        self.view.secondary_button.setEnabled(False)
        self.thread.stop()

    def reject(self):
        if self.view.state != "downloading" or self._work_done:
            if self.thread is not None:
                self.thread.wait()
            super().reject()
            return
        self._cancel()
