from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton
)

from src.i18n import t
from src.window_frame import apply_dialog_frame


class BulkAddDialog(QDialog):
    def __init__(self, parent=None, initial_urls: list[str] | None = None,
                 theme: str = "light"):
        super().__init__(parent)
        self.setWindowTitle(t("bulk.title"))
        self.resize(600, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.desc = QLabel(t("bulk.description"))
        self.desc.setWordWrap(True)
        layout.addWidget(self.desc)

        self.text = QTextEdit(self)
        self.text.setPlaceholderText(t("bulk.placeholder"))
        layout.addWidget(self.text, 1)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.addStretch(1)
        self.ok_btn = QPushButton(t("bulk.add"), objectName="PrimaryButton")
        self.cancel_btn = QPushButton(t("common.cancel"))
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        btns.addWidget(self.ok_btn)
        btns.addWidget(self.cancel_btn)
        layout.addLayout(btns)

        apply_dialog_frame(self, theme, icon_name="bulk_add")

        if initial_urls:
            self.set_urls(initial_urls)

    def set_urls(self, urls: list[str]):
        """입력칸을 주어진 주소 목록으로 채운다.

        끌어다 놓은 것이 여럿일 때 이 창을 거치게 해서, 무엇이 들어왔는지 보고 지울 기회를 남긴다.
        """
        self.text.setPlainText("\n".join(urls))

    def append_url(self, url: str) -> bool:
        """열려 있는 창 끝에 주소 한 줄을 덧붙이고, 실제로 늘었는지 돌려준다.

        클립보드 감시가 창이 떠 있는 동안 물어올 때 쓴다. 이미 적힌 주소면 아무것도 하지
        않는다 - 같은 주소를 두 번 복사하는 것은 흔한 일이고, 그때마다 줄이 늘면 확인
        버튼을 누르기 전에 목록부터 손봐야 한다.
        """
        urls = self.get_urls()
        if url in urls:
            return False
        self.set_urls(urls + [url])
        self.text.moveCursor(QTextCursor.MoveOperation.End)
        return True

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
