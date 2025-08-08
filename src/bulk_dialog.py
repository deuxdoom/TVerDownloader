# 파일명: src/bulk_dialog.py
# 다중 URL 입력 다이얼로그: 한 줄(Shift+Enter 포함)당 하나의 URL. 공백/쉼표도 처리.
from __future__ import annotations

import re
from typing import List
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPlainTextEdit, QDialogButtonBox, QPushButton, QWidget
)

URL_RE = re.compile(r"https?://\S+")

def parse_urls(text: str) -> List[str]:
    # 줄/공백/쉼표 섞여도 안전하게 URL만 추출
    return [u.strip() for u in URL_RE.findall(text or "") if u.strip()]

class BulkAddDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("다중 다운로드")
        self.setMinimumSize(520, 360)
        self._urls: List[str] = []

        root = QVBoxLayout(self)

        caption = QLabel("여러 개의 TVer URL을 붙여넣으세요.\n(권장: 한 줄에 하나 · Shift+Enter로 줄바꿈)")
        root.addWidget(caption)

        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText("예)\nhttps://tver.jp/episodes/xxxx\nhttps://tver.jp/series/yyyy\n...")
        root.addWidget(self.edit, 1)

        # 상태줄(개수)
        status_row = QHBoxLayout()
        self.count_label = QLabel("0개 URL")
        status_row.addWidget(self.count_label)
        status_row.addStretch(1)
        root.addLayout(status_row)

        # 버튼
        self.buttons = QDialogButtonBox()
        add_btn = self.buttons.addButton("목록 추가", QDialogButtonBox.ButtonRole.AcceptRole)
        cancel_btn = self.buttons.addButton("취소", QDialogButtonBox.ButtonRole.RejectRole)
        root.addWidget(self.buttons)

        add_btn.clicked.connect(self._on_accept)
        cancel_btn.clicked.connect(self.reject)
        self.edit.textChanged.connect(self._update_count)

        self._update_count()

    def _update_count(self):
        urls = parse_urls(self.edit.toPlainText())
        self.count_label.setText(f"{len(urls)}개 URL")

    def _on_accept(self):
        self._urls = parse_urls(self.edit.toPlainText())
        if not self._urls:
            # 비어있어도 그냥 닫지 말고 개수만 갱신
            self._update_count()
            return
        self.accept()

    def urls(self) -> List[str]:
        return self._urls[:]
