"""업데이트 진행 창.

**닫기 단추를 없애고 취소 단추만 둔다** - 창만 닫고 스레드는 계속 도는 상태가 생기면
다음에 다시 눌렀을 때 같은 폴더에 두 번 풀게 된다.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QLabel, QProgressBar, QPushButton,
                             QVBoxLayout, QHBoxLayout)

from src.i18n import t
from src.threads.update_thread import UpdateDownloadThread

DIALOG_WIDTH = 420
"""창 폭. 진행 문구가 파일 크기까지 담아도 한 줄에 떨어지는 값."""


class UpdateProgressDialog(QDialog):
    """내려받기·확인·압축 풀기까지의 진행을 보여 준다."""

    def __init__(self, asset_url: str, work_dir: Path, latest_tag: str,
                 parent=None, theme: str = "light"):
        super().__init__(parent)
        self.setWindowTitle(t("update.dialog_title"))
        self.setModal(True)
        self.setFixedWidth(DIALOG_WIDTH)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        self.failure_reason = ""
        """실패 사유. 사용자가 취소했으면 빈 문자열로 남는다."""

        self._work_done = False
        """스레드가 결론을 냈는가. 창을 닫아도 되는지를 이 값으로 가른다."""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        self.title_label = QLabel(t("update.dialog_heading", tag=latest_tag))
        self.title_label.setObjectName("UpdateTitle")
        layout.addWidget(self.title_label)

        self.status_label = QLabel(t("update.preparing"))
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton(t("common.cancel"))
        self.cancel_button.clicked.connect(self._cancel)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

        self.thread = UpdateDownloadThread(asset_url, work_dir, self)
        self.thread.progress.connect(self._on_progress)
        self.thread.finished.connect(self._on_finished)
        self.thread.start()

    def _on_progress(self, percent: int, message: str):
        self.bar.setValue(percent)
        self.status_label.setText(message)

    def _on_finished(self, ok: bool, reason: str):
        self.failure_reason = reason
        self._work_done = True
        self.accept() if ok else self.reject()

    def _cancel(self):
        """받기를 세운다. **창은 여기서 닫지 않는다** - 스레드가 빠져나온 뒤에 닫힌다."""
        self.cancel_button.setEnabled(False)
        self.status_label.setText(t("update.canceling"))
        self.thread.stop()

    def reject(self):
        """Esc·X도 취소 단추와 같은 길로 보낸다. 사유는 비워 둔다(사용자가 고른 것이라서).

        **끝나기를 기다리지 않고 닫으면 안 된다.** 닫는 순간 호출부가 작업 폴더를 지우는데,
        받기는 응답이 끊기면 DOWNLOAD_TIMEOUT(30초)까지 매달려 있어 그 사이에 지우면 쓰는
        중인 파일과 부딪힌다. 예전에는 3초만 기다리고 결과와 무관하게 닫았다. 창이 스레드의
        부모라 도는 채로 파괴될 위험도 함께 없앤다.

        `_work_done`이 필요한 것은 finished 시그널이 도착한 시점에 QThread가 아직
        `isRunning()`으로 보일 수 있어서다 - 그것만 보면 정작 끝났을 때 창이 닫히지 않는다.
        """
        if self._work_done or not self.thread.isRunning():
            super().reject()
            return
        self._cancel()
