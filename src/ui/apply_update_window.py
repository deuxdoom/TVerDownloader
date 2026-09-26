"""교체 중 본체가 없어도 진행과 실패 원인을 보여 주는 독립 창."""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRect
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QDialog, QVBoxLayout

from src.appicon import get_app_icon
from src.apply_update import (ApplyOptions, apply_update, make_result,
                              validate_arguments, write_result)
from src.i18n import t
from src.self_update import BACKUP_DIR_NAME
from src.ui.update_dialog import DIALOG_WIDTH
from src.ui.update_flow import UpdateFlowView, fit_window_height, refit_after_show
from src.updater import RELEASE_PAGE_URL
from src.window_frame import apply_dialog_frame
from versioninfo import APP_VERSION


def button_state(stage: str) -> tuple[str, bool]:
    if stage in {"waiting", "backing_up", "installing", "rolling_back"}:
        return "none", False
    return "close", True


class ApplyUpdateThread(QThread):
    progress = pyqtSignal(int, str, object)
    outcome = pyqtSignal(object)

    def __init__(self, options: ApplyOptions, parent=None):
        super().__init__(parent)
        self.options = options

    def run(self):
        try:
            result = apply_update(
                self.options,
                lambda percent, stage, detail: self.progress.emit(percent, stage, detail))
        except Exception as error:
            result = make_result(self.options, "failed", str(error))
            try:
                if validate_arguments(self.options, Path(sys.executable)):
                    write_result(self.options, result)
            except Exception:
                pass
            self.progress.emit(0, "failed", {"error": str(error)})
        self.outcome.emit(result)


class ApplyUpdateWindow(QDialog):
    """끝난 뒤에도 남아 있어 결과를 읽고 사용자가 직접 닫을 수 있다."""

    def __init__(self, options: ApplyOptions | None, theme: str = "light"):
        super().__init__()
        self.options = options
        self.stage = "waiting"
        self.worker = None
        self._anchored = False
        self._data = {
            "from_version": options.from_version if options is not None else "",
            "to_version": APP_VERSION, "queued_count": options.queued if options else 0,
            "progress": 0, "apply_stage": "waiting", "installed_count": 0,
        }
        self.setWindowTitle(t("apply_update.window_title"))
        self.setFixedWidth(DIALOG_WIDTH)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.view = UpdateFlowView(theme)
        self.view.action.connect(self._action)
        layout.addWidget(self.view)
        self.view.set_state("applying", self._data)
        apply_dialog_frame(self, theme, resizable=False, icon_name="download")
        getattr(self, "title_bar").setFixedHeight(40)
        getattr(self, "title_bar").icon_label.setPixmap(get_app_icon().pixmap(16, 16))
        getattr(self, "title_bar").close_button.setEnabled(False)
        fit_window_height(self)
        self._place_window(options.pos if options is not None else None)

        if options is None:
            self._show_stage(0, "bad_arguments", {})
        else:
            self.worker = ApplyUpdateThread(options, self)
            self.worker.progress.connect(self._show_stage)
            self.worker.outcome.connect(self._on_outcome)
            self.worker.start()

    def _place_window(self, pos: tuple[int, int] | None):
        if pos is None:
            return
        bounds = QRect(pos[0], pos[1], self.width(), self.height())
        if any(screen.availableGeometry().contains(bounds)
               for screen in QGuiApplication.screens()):
            self.removeEventFilter(getattr(self, "dialog_placer"))
            self.move(*pos)
            self._anchored = True

    def showEvent(self, event):
        super().showEvent(event)
        refit_after_show(self, recenter=not self._anchored)

    def _show_stage(self, percent: int, stage: str, detail: dict):
        previous = self.stage
        self.stage = stage
        self._data["progress"] = percent
        self._data["apply_stage"] = stage
        if stage in {"backing_up", "installing"}:
            done, total = detail.get("done", 0), detail.get("total", 0)
            self._data["task_detail"] = f"{done} / {total}" if total else ""
            if stage == "installing":
                self._data["installed_count"] = total
                self._data["last_done"] = done
                self._data["last_total"] = total
        elif stage in {"rolling_back", "rolled_back", "failed"}:
            if self._data.get("last_total"):
                self._data["task_detail"] = t("update_flow.stopped_at",
                                               done=self._data.get("last_done", 0),
                                               total=self._data["last_total"])
        if stage == "rolling_back":
            self._data["failed_task_index"] = {
                "waiting": 0, "backing_up": 1, "installing": 2,
            }.get(previous, 2)
        elif stage in {"wait_timeout", "bad_arguments", "failed"}:
            self._data.setdefault("failed_task_index", {
                "waiting": 0, "backing_up": 1, "installing": 2,
            }.get(previous, 0))
        if stage == "done":
            self._data["progress"] = 100
            self._data["from_version"] = detail.get("from_version",
                                                     self._data["from_version"])
            self._data["to_version"] = detail.get("to_version", APP_VERSION)
            flow_stage = "done"
        elif stage in {"rolled_back", "wait_timeout", "bad_arguments", "failed"}:
            self._data["rolled_back"] = stage == "rolled_back"
            self._data["rollback_failed"] = stage == "failed" and previous == "rolling_back"
            cause = str(detail.get("error", "")).splitlines()
            self._data["error"] = (t(f"apply_update.stage_{stage}")
                                   if stage in {"wait_timeout", "bad_arguments"}
                                   else cause[0] if cause else
                                   t(f"apply_update.stage_{stage}"))
            if self._data["rollback_failed"]:
                backup = (self.options.work_dir / BACKUP_DIR_NAME if self.options
                          else Path(BACKUP_DIR_NAME))
                self._data["manual"] = t("apply_update.detail_failed_manual",
                                         path=backup)
            flow_stage = "apply_failed"
        else:
            flow_stage = "applying"
        position = self.pos()
        self.view.set_state(flow_stage, self._data)
        getattr(self, "title_bar").close_button.setEnabled(flow_stage != "applying")
        fit_window_height(self)
        if self.isVisible():
            self.move(position)

    def _on_outcome(self, result: dict | None):
        if result is None:
            self._show_stage(0, "failed", {"error": t("apply_update.stage_failed")})
            return
        stage = result["stage"]
        self._show_stage(100 if stage == "done" else self._data["progress"],
                         stage, result)

    def _action(self, action: str):
        if action == "btn_release_page":
            try:
                webbrowser.open(RELEASE_PAGE_URL)
            except Exception:
                pass
        elif action == "btn_close":
            self.reject()

    def reject(self):
        if not button_state(self.stage)[1]:
            return
        if self.worker is not None:
            self.worker.wait()
        super().reject()

    def closeEvent(self, event):
        if not button_state(self.stage)[1]:
            event.ignore()
            return
        if self.worker is not None:
            self.worker.wait()
        event.accept()
