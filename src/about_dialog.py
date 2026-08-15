from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialogButtonBox, QWidget, QFrame
)
from PyQt6.QtCore import Qt
from src.appicon import get_app_icon
from src.qss import palette
from src.utils import open_developer_link, open_feedback_link, localized_app_name

FEATURES = [
    "에피소드 · 시리즈 URL 분석과 다중 추가",
    "주소 끌어다 놓기와 클립보드 자동 인식",
    "다운로드 대기열과 동시 다운로드 수 조절 (최대 20)",
    "즐겨찾기 시리즈 등록, 시작 시 신규 회차 자동 확인",
    "화질 선택, 코덱 재인코딩(GPU 가속), 자막 병합",
    "끌어놓기로 정렬하는 사용자 정의 파일명 형식",
    "바꿔 쓸 수 있는 키보드 단축키",
    "썸네일 미리보기, 다운로드 기록, 트레이 최소화",
]
"""정보 창에 한 줄씩 그대로 찍히는 목록.

스크롤 영역이 없어서 줄이 늘면 창이 그만큼 길어진다. 항목을 더할 때는 줄 수와
한 줄 길이를 함께 본다. 창 폭이 520px로 고정이라 여백을 뺀 478px를 넘는 문구는
잘린다(줄바꿈하지 않는다).
"""

LINKS = [
    ("yt-dlp", "https://github.com/yt-dlp/yt-dlp"),
    ("FFmpeg", "https://ffmpeg.org/"),
    ("PyQt6", "https://pypi.org/project/PyQt6/"),
    ("GitHub", "https://github.com/deuxdoom/TVerDownloader"),
]


class AboutDialog(QDialog):
    def __init__(self, version: str, parent: QWidget | None = None, theme: str = "light"):
        super().__init__(parent)
        self._colors = palette(theme)
        self.setWindowTitle("정보")
        self.setWindowIcon(get_app_icon())
        self.setModal(True)
        self.setFixedWidth(520)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(14)

        root.addLayout(self._build_header(version))
        root.addWidget(self._label(
            "TVer 콘텐츠를 개인 용도로 내려받는 데스크톱 앱입니다. "
            "지역 제한이 있는 서비스라 일본 VPN 환경에서 사용하는 것을 권장합니다.",
            wrap=True,
        ))
        root.addWidget(self._separator())

        root.addWidget(self._label("주요 기능", object_name="PaneTitle"))
        features = QVBoxLayout()
        features.setContentsMargins(2, 0, 0, 0)
        features.setSpacing(4)
        for text in FEATURES:
            features.addWidget(self._label(f"· {text}"))
        root.addLayout(features)

        root.addWidget(self._separator())

        anchor = f'color:{self._colors["accent"]}; text-decoration:none;'
        links_html = "  ·  ".join(
            f'<a href="{url}" style="{anchor}">{name}</a>' for name, url in LINKS
        )
        links = self._label(links_html, object_name="PaneSubtitle")
        links.setOpenExternalLinks(True)
        links.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(links)

        root.addWidget(self._label(
            "콘텐츠 제공자의 약관과 저작권을 지키는 범위에서 사용해 주세요.",
            object_name="PaneSubtitle", wrap=True,
        ))

        root.addStretch(1)
        root.addLayout(self._build_buttons())

    def _build_header(self, version: str) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(12)
        icon_label = QLabel()
        icon_label.setPixmap(get_app_icon().pixmap(40, 40))
        icon_label.setFixedSize(40, 40)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_box.addWidget(self._label(localized_app_name(), object_name="SectionTitle"))
        title_box.addWidget(self._label(f"버전 {version}", object_name="PaneSubtitle"))

        header.addWidget(icon_label)
        header.addLayout(title_box)
        header.addStretch(1)
        return header

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(4)
        youtube_btn = QPushButton("제작자 유투브", objectName="LinkButton")
        youtube_btn.clicked.connect(open_developer_link)
        contact_btn = QPushButton("문의하기", objectName="LinkButton")
        contact_btn.clicked.connect(open_feedback_link)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.button(QDialogButtonBox.StandardButton.Close).setText("닫기")
        close_box.rejected.connect(self.reject)

        row.addWidget(youtube_btn)
        row.addWidget(contact_btn)
        row.addStretch(1)
        row.addWidget(close_box)
        return row

    def _label(self, text: str, object_name: str = "", wrap: bool = False) -> QLabel:
        label = QLabel(text)
        if object_name:
            label.setObjectName(object_name)
        label.setWordWrap(wrap)
        return label

    def _separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setObjectName("Separator")
        line.setFixedHeight(1)
        return line
