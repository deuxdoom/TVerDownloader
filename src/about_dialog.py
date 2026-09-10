from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialogButtonBox, QWidget, QFrame
)
from PyQt6.QtCore import Qt, QTimer
from src import updater
from src.appicon import get_app_icon
from src.i18n import t
from src.message import notify
from src.qss import palette
from src.utils import open_developer_link, open_site_link, localized_app_name
from src.window_frame import apply_dialog_frame


def features() -> list[str]:
    """정보 창에 한 줄씩 그대로 찍히는 목록. lang/*.ini의 about.features(줄마다 한 항목).

    **전부 훑는 곳이 아니라 무엇을 하는 앱인지 한눈에 보는 곳이다.** 줄을 더하지 말고 기존
    줄을 고쳐 쓴다. 스크롤이 없어 줄이 늘면 창이 길어지고, 폭 520px에서 478px을 넘는 문구는
    줄바꿈 없이 잘린다. 함수로 둔 것은(모듈 상수가 아니라) 호출마다 지금 언어로 다시
    읽어야 해서다 - 상수면 이 모듈이 처음 import되는 순간의 언어로 굳는다.
    """
    return t("about.features").splitlines()


def intro() -> str:
    """창을 열면 맨 먼저 읽는 두 줄. lang/*.ini의 about.intro.

    **VPN을 권장이 아니라 필수로 적는다** - 켜지 않으면 하나도 받아지지 않아, '권장'으로 적으면
    프로그램이 고장 난 것으로 읽힌다. 빈 줄은 두지 않는다(아래 구분선과 겹쳐 문단이 갈라져 보인다).
    """
    return t("about.intro")


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
        self.setWindowTitle(t("about.title"))
        self.setWindowIcon(get_app_icon())
        self.setModal(True)
        self.setFixedWidth(520)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(14)

        root.addLayout(self._build_header(version))
        root.addWidget(self._label(intro(), wrap=True))
        root.addWidget(self._separator())

        root.addWidget(self._label(t("about.features_title"), object_name="PaneTitle"))
        features_layout = QVBoxLayout()
        features_layout.setContentsMargins(2, 0, 0, 0)
        features_layout.setSpacing(4)
        for text in features():
            features_layout.addWidget(self._label(f"· {text}"))
        root.addLayout(features_layout)

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
            t("about.terms_notice"),
            object_name="PaneSubtitle", wrap=True,
        ))

        root.addStretch(1)
        root.addLayout(self._build_buttons())
        apply_dialog_frame(self, theme, resizable=False,
                           icon_name="info")

    def _build_header(self, version: str) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(12)
        icon_label = QLabel()
        icon_label.setPixmap(get_app_icon().pixmap(40, 40))
        icon_label.setFixedSize(40, 40)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_box.addWidget(self._label(localized_app_name(), object_name="SectionTitle"))
        title_box.addWidget(self._label(t("about.version", version=version), object_name="PaneSubtitle"))

        header.addWidget(icon_label)
        header.addLayout(title_box)
        header.addStretch(1)
        return header

    CHECK_LABEL_KEY = "about.check_update"
    CHECKING_LABEL_KEY = "about.checking"

    def _build_buttons(self) -> QHBoxLayout:
        """왼쪽에 할 일 셋, 오른쪽에 닫기.

        밑줄만 있는 링크 모양은 눌러도 되는지 분명하지 않아 기본 QPushButton 모양으로 둔다.
        """
        row = QHBoxLayout()
        row.setSpacing(6)
        youtube_btn = QPushButton(t("about.youtube"), objectName="AboutYouTube")
        youtube_btn.clicked.connect(open_developer_link)
        site_btn = QPushButton(t("about.site"), objectName="AboutSite")
        site_btn.clicked.connect(open_site_link)

        self.check_btn = QPushButton(t(self.CHECK_LABEL_KEY), objectName="AboutUpdate")
        self.check_btn.clicked.connect(self._check_update)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.button(QDialogButtonBox.StandardButton.Close).setText(t("common.close"))
        close_box.rejected.connect(self.reject)

        row.addWidget(youtube_btn)
        row.addWidget(site_btn)
        row.addWidget(self.check_btn)
        row.addStretch(1)
        row.addWidget(close_box)
        return row

    def _check_update(self):
        """눌러서 하는 새 버전 확인.

        **스레드를 쓰지 않는다** - 시작할 때 도는 확인도 같은 조회를 메인 스레드에서 하고,
        여기만 스레드를 두면 창이 먼저 닫혔을 때의 뒷정리를 관리해야 한다. 누르는 순간 단추를
        잠그고, 그 변화가 화면에 실제로 찍히도록 한 번 처리한 뒤 물어본다.
        """
        self.check_btn.setEnabled(False)
        self.check_btn.setText(t(self.CHECKING_LABEL_KEY))
        QApplication.processEvents()
        try:
            release = updater.fetch_latest(self._log)
        finally:
            self.check_btn.setEnabled(True)
            self.check_btn.setText(t(self.CHECK_LABEL_KEY))
        self._on_checked(release is not None, release or {})

    def _on_checked(self, ok: bool, release: dict):
        """확인 결과를 알린다. **최신이어도 반드시 무언가 보여 준다.**

        시작할 때 도는 확인과 달리, 눌러서 한 확인이 조용하면 아무 일도 안 일어난 것으로 보인다.
        """
        self.check_btn.setEnabled(True)
        self.check_btn.setText(t(self.CHECK_LABEL_KEY))

        if not ok:
            notify(self, t(self.CHECK_LABEL_KEY),
                   t("about.check_failed_body"),
                   icon_name="info", color_key="warn", theme=self._theme)
            return

        if not updater.has_newer(release, self._version):
            notify(self, t(self.CHECK_LABEL_KEY),
                   t("about.up_to_date", version=self._version),
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
