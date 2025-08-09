# -*- coding: utf-8 -*-
# 파일명: src/bulk_dialog.py
# 목적: 여러 개의 URL을 한 번에 입력받아 반환
# 특징:
#  - get_urls(): 줄 단위로 URL을 파싱하여 리스트로 반환
#  - 공백/중복 제거
#  - 시리즈/일반 URL 구분은 호출측(TVerDownloader.open_bulk_add)에서 처리

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton
)
from PyQt6.QtCore import Qt


class BulkAddDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("다중 다운로드")
        self.resize(600, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.desc = QLabel(
            "각 줄에 하나의 URL을 입력하세요.\n"
            "- 일반 에피소드 URL은 그대로 추가됩니다.\n"
            "- 시리즈 URL은 에피소드로 확장되어 여러 항목으로 추가됩니다."
        )
        self.desc.setWordWrap(True)
        layout.addWidget(self.desc)

        self.text = QTextEdit(self)
        self.text.setPlaceholderText("예:\nhttps://tver.jp/episodes/...\nhttps://tver.jp/series/...")
        layout.addWidget(self.text, 1)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.addStretch(1)
        self.ok_btn = QPushButton("추가")
        self.cancel_btn = QPushButton("취소")
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        btns.addWidget(self.ok_btn)
        btns.addWidget(self.cancel_btn)
        layout.addLayout(btns)

    def get_urls(self) -> list[str]:
        raw = self.text.toPlainText() or ""
        lines = [l.strip() for l in raw.splitlines()]
        out = []
        seen = set()
        for s in lines:
            if not s:
                continue
            if s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out
