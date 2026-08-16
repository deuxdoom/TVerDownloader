"""업데이트 진행 창.

받는 동안 무엇을 하는 중인지 보여 주고, 그만둘 길을 남긴다. 35MB를 받는 동안
아무 표시 없이 굳어 있으면 앱이 죽은 것으로 보인다.

**닫기 단추를 없애고 취소 단추만 둔다.** 창만 닫고 스레드는 계속 도는 상태가
생기면, 다음에 다시 눌렀을 때 같은 폴더에 두 번 풀게 된다. 나가는 길을 하나로
모아 그 자리에서 스레드를 세운다.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QLabel, QProgressBar, QPushButton,
                             QVBoxLayout, QHBoxLayout)

from src.threads.update_thread import UpdateDownloadThread

DIALOG_WIDTH = 420
"""창 폭. 진행 문구가 파일 크기까지 담아도 한 줄에 떨어지는 값."""


class UpdateProgressDialog(QDialog):
    """내려받기·확인·압축 풀기까지의 진행을 보여 준다."""

    def __init__(self, asset_url: str, work_dir: Path, latest_tag: str,
                 parent=None, theme: str = "light"):
        super().__init__(parent)
        self.setWindowTitle("업데이트")
        self.setModal(True)
        self.setFixedWidth(DIALOG_WIDTH)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        self.failure_reason = ""
        """실패 사유. 사용자가 취소했으면 빈 문자열로 남는다."""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        self.title_label = QLabel(f"새 버전 {latest_tag}")
        self.title_label.setObjectName("UpdateTitle")
        layout.addWidget(self.title_label)

        self.status_label = QLabel("준비하는 중...")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("취소")
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
        self.accept() if ok else self.reject()

    def _cancel(self):
        """받기를 세우고 창을 닫는다. 사유는 비워 둔다(사용자가 고른 것이라서)."""
        self.cancel_button.setEnabled(False)
        self.status_label.setText("취소하는 중...")
        self.thread.stop()

    def reject(self):
        """Esc로도 여기를 지나가므로 스레드를 세우는 자리를 여기로 모은다."""
        if self.thread.isRunning():
            self.thread.stop()
            self.thread.wait(3000)
        super().reject()
