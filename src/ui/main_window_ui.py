from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QTextEdit,
    QLabel, QListWidget, QFrame, QTabWidget, QToolButton,
    QComboBox, QAbstractItemView
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction, QFont

import webbrowser

from src import autostart, shortcuts
from src.appicon import get_app_icon
from src.titlelogo import LOGO_HEIGHT, build_logo
from src.utils import localized_app_name
from src.icons import get_icon
from src.qss import palette
from src.widgets import GridListWidget, FavoriteItemWidget, RoundedMenu

class MainWindowUI:
    ICON_BUTTON_SIZE = 32
    ICON_SIZE = 20
    MIN_WIDTH = 940
    MIN_WIDTH_WITH_LOG = 970
    """로그를 편 상태의 최소 창 폭.

    로그가 LOG_PANE_WIDTH로 고정이므로, 그 옆에 다운로드 카드가 잘리지 않고 들어갈
    폭(548px)과 탭 여백을 더한 값이다. 로그 폭을 줄이면 이 값도 같은 만큼 함께
    내려야 왼쪽 목록에 돌아가는 폭이 그대로 유지된다. 한쪽만 고치면 최소 폭에서
    목록이 넓어지거나(로그만 줄임) 카드가 눌린다(최소 폭만 줄임).

    로그를 접으면 MIN_WIDTH로 돌아가 좁은 화면에서도 쓸 수 있다.
    """
    MIN_HEIGHT = 620
    TAB_ICONS = (("download", "ctx_download"),
                 ("tab_history", "ctx_history"),
                 ("tab_favorites", "ctx_favorites"))
    FAV_COLUMNS = 2
    FAV_MIN_CARD_WIDTH = 340
    LOG_PANE_WIDTH = 390
    """로그 패널 고정 폭.

    로그는 읽고 지나가는 곳이라 목록보다 좁아도 된다. 480px일 때는 최소 폭 창에서
    화면의 45%를 가져가 정작 카드가 뒤로 밀렸다. 바꿀 때는 MIN_WIDTH_WITH_LOG도
    같은 만큼 움직인다.
    """

    LEFT_PANE_MIN_WIDTH = 360

    TAB_MARGIN = 12
    TAB_SPACING = 8
    """세 탭이 같은 여백을 쓴다. 탭을 옮길 때 제목이 제자리에 있어야 한다."""

    HEADER_ROW_HEIGHT = 32
    """탭 제목 줄의 높이. 줄 안에 무엇이 들어가든 이 높이로 고정한다.

    줄 높이는 그 안에서 가장 큰 위젯이 정한다. 탭마다 놓이는 위젯이 달라
    그대로 두면 아이콘 버튼(32)이 있는 탭과 입력칸(31)만 있는 탭의 높이가
    1px 어긋나고, 그만큼 아래 목록 상자가 위아래로 튄다.
    """

    SEARCH_INPUT_WIDTH = 200
    FAV_INPUT_WIDTH = 280
    """시리즈 URL은 190px 남짓이라 입력칸이 이만큼이면 충분하다.
    남는 폭을 다 먹게 두면 옆 버튼들이 화면 끝으로 밀려 읽기 어렵다."""

    SHORTCUT_HINT_BUTTONS = {
        "open_settings": "settings_button",
        "toggle_log": "log_toggle_btn",
    }
    """툴팁 끝에 지금 걸린 조합을 붙일 버튼.

    조합을 사용자가 바꿀 수 있게 된 이상 지금 값이 화면 어딘가에는 보여야 한다.
    툴팁이 그 자리로 가장 방해가 적고, 버튼이 곧 그 동작이라 설명이 따로 없어도 된다.
    """

    def _tab_page(self, object_name: str):
        """탭 한 장과 그 세로 레이아웃을 같은 여백으로 만들어 돌려준다."""
        tab = QWidget(objectName=object_name)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(self.TAB_MARGIN, self.TAB_MARGIN,
                                  self.TAB_MARGIN, self.TAB_MARGIN)
        layout.setSpacing(self.TAB_SPACING)
        return tab, layout

    def _make_pane_title(self, text: str) -> QLabel:
        """탭 제목 라벨. 높이를 고정해 제목 줄 전체 높이를 붙든다."""
        label = QLabel(text, objectName="PaneTitle")
        label.setMinimumHeight(self.HEADER_ROW_HEIGHT)
        return label

    def _make_search_input(self, placeholder: str = "검색...") -> QLineEdit:
        """탭 제목 줄 오른쪽에 놓는 검색칸. 세 탭이 같은 모양을 쓴다."""
        box = QLineEdit(placeholderText=placeholder)
        box.setClearButtonEnabled(True)
        box.setFixedWidth(self.SEARCH_INPUT_WIDTH)
        return box

    def __init__(self, main_window):
        self.main_window = main_window
        main_window.setWindowIcon(get_app_icon())
        main_window.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        main_window.resize(1100, 700)
        self._icon_buttons = []
        self._theme = "light"
        self._icon_colors = palette("light")
        self._log_visible = True
        self._shortcut_hint_bases = {}
        self._shortcut_hints = {}

    def _register_icon(self, btn, icon_name, color_key="text"):
        """버튼에 아이콘 정보를 붙이고 테마 전환 대상으로 등록한다."""
        btn.setProperty("icon_name", icon_name)
        btn.setProperty("icon_color_key", color_key)
        self._icon_buttons.append(btn)
        self._paint_icon(btn)
        return btn

    def _paint_icon(self, btn):
        color = self._icon_colors[btn.property("icon_color_key") or "text"]
        btn.setIcon(get_icon(btn.property("icon_name"), color))

    def _make_icon_button(self, icon_name, tooltip, checkable=False):
        btn = QToolButton(objectName="IconButton", toolTip=tooltip)
        btn.setFixedSize(self.ICON_BUTTON_SIZE, self.ICON_BUTTON_SIZE)
        btn.setIconSize(QSize(self.ICON_SIZE, self.ICON_SIZE))
        btn.setCheckable(checkable)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return self._register_icon(btn, icon_name)

    def apply_theme(self, theme):
        """테마 전환 시 아이콘 색을 다시 칠한다. QSS는 호출부에서 따로 적용한다."""
        self._theme = theme
        self._icon_colors = palette(theme)
        self._apply_title_logo()
        self.update_theme_button(theme)
        self.update_pin_button(self.on_top_btn.isChecked())
        for btn in self._icon_buttons:
            self._paint_icon(btn)
        self.refresh_tab_icons()

    def update_theme_button(self, theme):
        """지금 테마가 아니라 '누르면 갈 테마'를 보여준다."""
        going_dark = theme == "light"
        self.theme_button.setProperty("icon_name", "theme_dark" if going_dark else "theme_light")
        self.theme_button.setToolTip("다크 테마로 전환" if going_dark else "라이트 테마로 전환")
        self._paint_icon(self.theme_button)

    def set_primary_action_enabled(self, enabled: bool):
        """다운로드 버튼의 아이콘 색을 활성 상태에 맞춘다.

        primary_fg 아이콘을 비활성 배경에 그대로 두면 보이지 않는다.
        """
        self.add_button.setProperty("icon_color_key", "primary_fg" if enabled else "text_dim")
        self._paint_icon(self.add_button)

    def _apply_title_logo(self):
        """헤더 제목을 로고 이미지로 채운다.

        파일이 없거나 읽지 못하면 글자 제목으로 되돌아가므로, 로고가 빠져도
        앱은 그대로 쓸 수 있다.
        """
        dpr = self.main_window.devicePixelRatioF() or 1.0
        pixmap = build_logo(self._theme, LOGO_HEIGHT, dpr)
        if pixmap is None:
            self.app_title.setText(localized_app_name())
            return
        self.app_title.setPixmap(pixmap)

    def update_pin_button(self, on):
        self.on_top_btn.setProperty("icon_name", "pin_on" if on else "pin")
        self._paint_icon(self.on_top_btn)

    def _set_hinted_tooltip(self, attribute: str, base: str):
        """원래 문구를 기억해 두고, 뒤에 지금 걸린 조합을 붙여 툴팁으로 넣는다.

        이미 붙은 문자열에 다시 붙이면 설정을 열고 닫을 때마다 조합이 줄줄이
        쌓인다. 문구와 조합을 따로 들고 있다가 불릴 때마다 새로 만든다.
        """
        self._shortcut_hint_bases[attribute] = base
        hint = self._shortcut_hints.get(attribute, "")
        getattr(self, attribute).setToolTip(f"{base} ({hint})" if hint else base)

    def apply_shortcut_hints(self, table: dict):
        """버튼 툴팁 끝에 지금 걸린 조합을 붙인다.

        조합만 따로 적어 두고 문구는 버튼이 지금 들고 있는 것을 그대로 쓴다. 로그
        토글처럼 상태에 따라 문구가 바뀌는 버튼이 있어, 처음 문구를 고정으로 잡아
        두면 바뀐 뒤에 엉뚝한 안내가 남는다. 조합을 비워 둔 동작은 붙일 것이 없으므로
        원래 문구로 되돌린다.
        """
        for key, attribute in self.SHORTCUT_HINT_BUTTONS.items():
            button = getattr(self, attribute, None)
            if button is None:
                continue
            text = table.get(key, "")
            self._shortcut_hints[attribute] = shortcuts.display(text) if text else ""
            self._set_hinted_tooltip(
                attribute, self._shortcut_hint_bases.get(attribute, button.toolTip()))

    def setup_ui(self):
        central = QWidget()
        self.main_window.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        self._create_header(root)
        self._create_input_bar(root)
        self._create_tabs(root)

    def _create_header(self, root_layout):
        header = QFrame(objectName="AppHeader")
        layout = QHBoxLayout(header); layout.setContentsMargins(16, 8, 16, 8); layout.setSpacing(4)
        self.app_title = QLabel(objectName="AppTitle")
        self.app_title.setFixedHeight(LOGO_HEIGHT)
        self._apply_title_logo()
        self.settings_button = self._make_icon_button("settings", "설정")
        self.theme_button = self._make_icon_button("theme_dark", "다크 테마로 전환")
        self.on_top_btn = self._make_icon_button("pin", "항상 위", checkable=True)
        self.about_button = self._make_icon_button("info", "정보")
        layout.addWidget(self.app_title); layout.addStretch(1)
        for btn in (self.settings_button, self.theme_button,
                    self.on_top_btn, self.about_button):
            layout.addWidget(btn)
        root_layout.addWidget(header)

    def _create_input_bar(self, root_layout):
        input_bar = QFrame(objectName="InputBar")
        layout = QHBoxLayout(input_bar); layout.setContentsMargins(16, 12, 16, 12); layout.setSpacing(10)
        self.url_input = QLineEdit(placeholderText="TVer 영상 URL 붙여넣기 또는 끌어다 놓기", objectName="UrlInput")
        self.url_input.setToolTip(
            "브라우저 주소창에서 주소를 끌어다 놓아도 됩니다.\n"
            "여러 개를 한 번에 놓으면 다중 추가 창이 열립니다.")
        self.bulk_button = QPushButton("다중 추가")
        self.add_button = QPushButton("다운로드", objectName="PrimaryButton")
        self._register_icon(self.bulk_button, "bulk_add")
        self._register_icon(self.add_button, "download", color_key="primary_fg")
        for btn in (self.bulk_button, self.add_button):
            btn.setIconSize(QSize(self.ICON_SIZE, self.ICON_SIZE))
        layout.addWidget(self.url_input, 1); layout.addWidget(self.bulk_button); layout.addWidget(self.add_button)
        root_layout.addWidget(input_bar)

    def _create_tabs(self, root_layout):
        self.tabs = QTabWidget(objectName="MainTabs")
        self.tabs.setIconSize(QSize(self.ICON_SIZE, self.ICON_SIZE))
        self.tabs.setDocumentMode(True)
        tab_bar = self.tabs.tabBar()
        tab_bar.setDrawBase(False)
        tab_bar.setExpanding(False)
        tab_bar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._create_download_tab()
        self._create_history_tab()
        self._create_favorites_tab()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.refresh_tab_icons()
        root_layout.addWidget(self.tabs, 1)

    def _on_tab_changed(self, _index):
        self.refresh_tab_icons()

    def refresh_tab_icons(self):
        """선택된 탭만 진하게 칠한다.

        QTabBar는 QIcon의 Selected 모드를 쓰지 않아서, 선택이 바뀔 때마다
        해당 색으로 새로 만들어 넣어야 한다.
        """
        current = self.tabs.currentIndex()
        for index, (name, ctx_key) in enumerate(self.TAB_ICONS):
            if index >= self.tabs.count():
                break
            color_key = ctx_key if index == current else "text_dim"
            self.tabs.setTabIcon(index, get_icon(name, self._icon_colors[color_key], self.ICON_SIZE))

    def _create_download_tab(self):
        """다운로드 목록과 로그를 좌우로 놓는다.

        로그는 폭을 고정한다. 스플리터로 사용자가 끌어 줄일 수 있게 두면 그때마다
        복원할 폭을 기억해야 하고, 창이 뜨기 전에는 그 값을 신뢰할 수 없어 상태가
        어긋난다. 고정폭이면 그 부류의 문제가 처음부터 생기지 않는다.
        """
        tab, layout = self._tab_page("DownloadTab")
        panes = QHBoxLayout(); panes.setContentsMargins(0, 0, 0, 0)
        panes.setSpacing(self.TAB_SPACING)

        left_pane = QFrame(objectName="LeftPane"); left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(self.TAB_SPACING); row = QHBoxLayout()
        self.cancel_selected_button = QPushButton("선택 항목 취소")
        self.cancel_selected_button.setToolTip(
            "진행 중인 항목은 중지하고, 대기 중인 항목은 대기열에서 뺍니다.\n"
            "여러 개를 선택하면 한 번에 처리합니다.")
        self.cancel_selected_button.setEnabled(False)
        self.clear_completed_button = QPushButton("완료 항목 삭제")
        self.queue_count_label = QLabel("0 대기 / 0 진행", objectName="PaneSubtitle")
        self.log_toggle_btn = self._make_icon_button("log", "로그 숨기기")
        row.addWidget(self._make_pane_title("다운로드 목록")); row.addStretch(1)
        row.addWidget(self.cancel_selected_button)
        row.addWidget(self.clear_completed_button)
        row.addWidget(self.queue_count_label)
        row.addWidget(self.log_toggle_btn)
        left_layout.addLayout(row)
        self.download_list = QListWidget(objectName="DownloadList")
        self.download_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.download_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.download_list.setSpacing(6)
        left_layout.addWidget(self.download_list, 1)

        right_pane = QFrame(objectName="RightPane"); right_layout = QVBoxLayout(right_pane)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(self.TAB_SPACING); row_log = QHBoxLayout()
        self.clear_log_button = QPushButton("지우기")
        self.clear_log_button.setToolTip("로그 패널의 내용을 비웁니다.")
        row_log.addWidget(self._make_pane_title("로그")); row_log.addStretch(1)
        row_log.addWidget(self.clear_log_button)
        self.log_output = QTextEdit(objectName="LogOutput", readOnly=True)
        right_layout.addLayout(row_log); right_layout.addWidget(self.log_output, 1)
        right_pane.setFixedWidth(self.LOG_PANE_WIDTH)

        self.log_pane = right_pane
        left_pane.setMinimumWidth(self.LEFT_PANE_MIN_WIDTH)
        panes.addWidget(left_pane, 1); panes.addWidget(right_pane)
        layout.addLayout(panes, 1); self.tabs.addTab(tab, "다운로드")

    def set_log_visible(self, visible: bool):
        """로그 패널을 접거나 편다. 폭이 고정이라 되돌릴 상태가 없다.

        편 상태에서는 창 최소 폭도 함께 올린다. 그러지 않으면 좁은 창에서
        고정폭 로그가 목록을 밀어내 카드가 잘린다.
        """
        self.log_pane.setVisible(visible)
        self.main_window.setMinimumWidth(
            self.MIN_WIDTH_WITH_LOG if visible else self.MIN_WIDTH)
        self._log_visible = visible
        self.update_log_toggle_button(visible)

    def is_log_visible(self) -> bool:
        return self._log_visible

    def update_log_toggle_button(self, visible: bool):
        """지금 상태가 아니라 '누르면 일어날 일'을 알려 준다."""
        self._set_hinted_tooltip("log_toggle_btn",
                                 "로그 숨기기" if visible else "로그 보기")

    def _create_history_tab(self):
        tab, layout = self._tab_page("HistoryTab")
        top_controls = QHBoxLayout()
        self.history_sort_combo = QComboBox()
        self.history_sort_combo.addItem("다운로드 최신순")
        self.history_sort_combo.addItem("제목 오름차순")
        self.history_search_input = self._make_search_input()
        top_controls.addWidget(self._make_pane_title("다운로드 기록"))
        top_controls.addStretch(1)
        top_controls.addWidget(self.history_sort_combo)
        top_controls.addWidget(self.history_search_input)
        layout.addLayout(top_controls)
        self.history_list = QListWidget(objectName="HistoryList")
        self.history_list.setSpacing(6)
        self.history_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self.history_list, 1)
        self.tabs.addTab(tab, "기록")

    def _create_favorites_tab(self):
        tab, layout = self._tab_page("FavoritesTab")
        row = QHBoxLayout()
        row.addWidget(self._make_pane_title("즐겨찾기 (시리즈)"))
        row.addStretch(1)
        self.fav_input = QLineEdit(placeholderText="https://tver.jp/series/...")
        self.fav_input.setFixedWidth(self.FAV_INPUT_WIDTH)
        self.fav_add_btn = QPushButton("추가")
        self.fav_del_btn = QPushButton("삭제", objectName="DangerButton")
        self.fav_chk_btn = QPushButton("갱신")
        self.fav_chk_btn.setToolTip("등록한 시리즈를 모두 확인해 새로 올라온 회차를 찾습니다.")
        self.fav_search_input = self._make_search_input()
        for widget in (self.fav_input, self.fav_add_btn, self.fav_del_btn,
                       self.fav_chk_btn, self.fav_search_input):
            row.addWidget(widget)
        layout.addLayout(row)
        self.fav_list = GridListWidget(columns=self.FAV_COLUMNS,
                                       min_item_width=self.FAV_MIN_CARD_WIDTH)
        self.fav_list.setObjectName("FavoritesList")
        self.fav_list.setSpacing(6)
        self.fav_list.set_item_height(FavoriteItemWidget.CARD_HEIGHT)
        self.fav_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.fav_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self.fav_list, 1); self.tabs.addTab(tab, "즐겨찾기")

    TRAY_GITHUB_URL = "https://github.com/deuxdoom/TVerDownloader"

    def setup_tray(self, app_version):
        """트레이 아이콘과 우클릭 메뉴를 만든다.

        첫 항목은 '<앱 이름> 열기'이고 누르면 창이 돌아온다. 트레이 메뉴를 열었다는
        것은 대개 창을 다시 보려던 것이라 가장 자주 쓰는 동작을 맨 위에 둔다. 이름만
        적어 두면 제목처럼 읽혀 눌러도 되는 줄인지 알기 어려워서 '열기'를 붙인다.
        굵게 표시해 기본 동작임을 함께 보인다.

        구분선은 둘만 쓴다. 항목마다 그으면 다섯 줄짜리 메뉴가 선으로 더 채워져
        오히려 읽기 어렵다. 창을 여는 일 / 설정에 해당하는 것들 / 끝내는 일, 이렇게
        성격이 다른 세 덩이만 가른다. 종료를 따로 떼는 것은 되돌릴 수 없는 동작이라
        위 항목을 누르려다 잘못 짚는 것을 막기 위해서다.

        시작 프로그램 체크는 열 때마다 레지스트리를 다시 읽는다(aboutToShow).
        다른 프로그램이나 작업 관리자에서 꺼 놓았을 수 있는데, 앱이 마지막으로 쓴
        값을 기억해 두면 실제와 다른 상태를 보여 주게 된다.

        설정은 창을 되살리지 않고 바로 연다. 트레이에 넣어 둔 채로 동시 다운로드 수만
        바꾸고 싶은 경우가 있어서, 창까지 끌어내면 하던 일을 되돌려 놓아야 한다.
        """
        tray_icon = self.main_window.tray_icon; tray_icon.setIcon(get_app_icon())
        tray_icon.setToolTip(f"{localized_app_name()} {app_version}")
        tray_menu = RoundedMenu()

        restore_action = QAction(f"{localized_app_name()} 열기", self.main_window,
                                 triggered=self.main_window.bring_to_front)
        bold = QFont(restore_action.font()); bold.setBold(True)
        restore_action.setFont(bold)
        tray_menu.addAction(restore_action)
        tray_menu.addSeparator()

        self.autostart_action = QAction("윈도우 시작 시 실행", self.main_window, checkable=True)
        self.autostart_action.toggled.connect(self.main_window.set_autostart)
        if not autostart.supported():
            self.autostart_action.setEnabled(False)
            self.autostart_action.setToolTip(
                "빌드된 실행 파일에서만 켤 수 있습니다.")
        tray_menu.addAction(self.autostart_action)

        tray_menu.addAction(QAction("GitHub 페이지", self.main_window,
                                    triggered=lambda: webbrowser.open(self.TRAY_GITHUB_URL)))

        tray_menu.addAction(QAction("설정", self.main_window,
                                    triggered=self.main_window.open_settings))
        tray_menu.addSeparator()

        tray_menu.addAction(QAction("프로그램 종료", self.main_window,
                                    triggered=self.main_window.quit_application))

        tray_menu.aboutToShow.connect(self.sync_autostart_check)
        self.sync_autostart_check()
        tray_icon.setContextMenu(tray_menu); tray_icon.show()

    def sync_autostart_check(self):
        """레지스트리에 걸린 실제 상태로 체크 표시를 맞춘다.

        toggled 신호가 다시 돌아 레지스트리를 또 쓰지 않도록 잠시 끊는다.
        """
        self.autostart_action.blockSignals(True)
        self.autostart_action.setChecked(autostart.is_enabled())
        self.autostart_action.blockSignals(False)
