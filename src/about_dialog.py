from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialogButtonBox, QWidget, QFrame
)
from PyQt6.QtCore import Qt, QTimer
from src import updater
from src.appicon import get_app_icon
from src.message import notify
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
        self._theme = theme
        self._version = version
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

    CHECK_LABEL = "업데이트 확인"
    CHECKING_LABEL = "확인 중..."

    def _build_buttons(self) -> QHBoxLayout:
        """왼쪽에 할 일 셋, 오른쪽에 닫기.

        예전에는 밑줄만 있는 링크 모양(LinkButton)이라 눌러도 되는 것인지
        분명하지 않았다. 기본 QPushButton 모양(테두리 + 라운드)으로 바꿔
        나머지 창의 단추들과 같아 보이게 한다.
        """
        row = QHBoxLayout()
        row.setSpacing(6)
        youtube_btn = QPushButton("제작자 유투브", objectName="AboutYouTube")
        youtube_btn.clicked.connect(open_developer_link)
        contact_btn = QPushButton("문의하기", objectName="AboutContact")
        contact_btn.clicked.connect(open_feedback_link)

        self.check_btn = QPushButton(self.CHECK_LABEL, objectName="AboutUpdate")
        self.check_btn.clicked.connect(self._check_update)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.button(QDialogButtonBox.StandardButton.Close).setText("닫기")
        close_box.rejected.connect(self.reject)

        row.addWidget(youtube_btn)
        row.addWidget(contact_btn)
        row.addWidget(self.check_btn)
        row.addStretch(1)
        row.addWidget(close_box)
        return row

    def _check_update(self):
        """눌러서 하는 새 버전 확인.

        **스레드를 쓰지 않는다.** 시작할 때 도는 확인도 이미 같은 조회를 메인
        스레드에서 그대로 하고(updater.CHECK_TIMEOUT은 10초), 여기서만 따로
        스레드를 두면 창이 먼저 닫혔을 때의 뒷정리를 관리해야 한다. 눌러서 하는
        조회 한 번에 그만한 장치를 붙일 이유가 없다.

        누르는 순간 단추를 잠그고 글을 바꾼 뒤, 그 변화가 화면에 실제로 찍히도록
        한 번 처리하고 나서 물어본다. 안 그러면 굳은 동안 단추가 그대로 보여
        눌리지 않은 것으로 오해된다.
        """
        self.check_btn.setEnabled(False)
        self.check_btn.setText(self.CHECKING_LABEL)
        QApplication.processEvents()
        try:
            release = updater.fetch_latest(self._log)
        finally:
            self.check_btn.setEnabled(True)
            self.check_btn.setText(self.CHECK_LABEL)
        self._on_checked(release is not None, release or {})

    def _on_checked(self, ok: bool, release: dict):
        """확인 결과를 알린다. **최신이어도 반드시 무언가 보여 준다.**

        시작할 때 도는 확인은 새 버전이 없으면 조용히 지나가지만, 눌러서 하는
        확인이 그러면 눌렀는데 아무 일도 안 일어난 것으로 보인다.
        """
        self.check_btn.setEnabled(True)
        self.check_btn.setText(self.CHECK_LABEL)

        if not ok:
            notify(self, "업데이트 확인",
                   "새 버전이 있는지 확인하지 못했습니다.\n\n"
                   "인터넷 연결을 확인한 뒤 다시 시도해 주세요.",
                   icon_name="info", color_key="warn", theme=self._theme)
            return

        if not updater.has_newer(release, self._version):
            notify(self, "업데이트 확인",
                   f"이미 최신 버전입니다. (v{self._version})",
                   icon_name="info", theme=self._theme)
            return

        window = self.parent()
        self.accept()
        QTimer.singleShot(0, lambda: updater.prompt_and_update(
            window, release, self._log,
            pending_downloads=self._pending_downloads(window),
            single_button=True))

    @staticmethod
    def _pending_downloads(window) -> int:
        """받는 중이거나 기다리는 항목 수. 셀 수 없으면 0."""
        manager = getattr(window, "download_manager", None)
        return manager.pending_count() if manager is not None else 0

    def _log(self, text: str):
        """메인 창 로그로 흘려보낸다. 창이 없으면 버린다."""
        append = getattr(self.parent(), "append_log", None)
        if callable(append):
            append(text)

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
