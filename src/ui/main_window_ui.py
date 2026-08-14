# src/ui/main_window_ui.py
# 수정:
# - QAbstractItemView import 추가
# - _create_download_tab: download_list의 SelectionMode를 ExtendedSelection으로 설정하여 다중 선택 허용

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QTextEdit,
    QLabel, QListWidget, QFrame, QSplitter, QTabWidget, QToolButton, QMenu,
    QComboBox, QAbstractItemView
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction

from src.icon import get_app_icon
from src.titlelogo import LOGO_HEIGHT, build_logo
from src.utils import localized_app_name
from src.icons import get_icon
from src.qss import palette

class MainWindowUI:
    # 클릭 영역 32x32, 아이콘 20px (로고 30px와 균형을 맞춘 값)
    ICON_BUTTON_SIZE = 32
    ICON_SIZE = 20
    # 좌우 분할 구조라 폭이 좁아지면 카드와 로그가 서로를 밀어낸다.
    MIN_WIDTH = 940
    MIN_HEIGHT = 620
    # 세그먼트 컨트롤 탭 순서와 아이콘
    TAB_ICONS = (("download", "ctx_download"),
                 ("tab_history", "ctx_history"),
                 ("tab_favorites", "ctx_favorites"))

    def __init__(self, main_window):
        self.main_window = main_window
        main_window.setWindowIcon(get_app_icon())
        main_window.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        main_window.resize(1100, 700)
        # 테마가 바뀌면 다시 칠해야 하는 버튼들
        self._icon_buttons = []
        self._theme = "light"
        self._icon_colors = palette("light")

    # ── 아이콘 ────────────────────────────────────────────────────────────
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
        for btn in (self.settings_button, self.theme_button, self.on_top_btn, self.about_button):
            layout.addWidget(btn)
        root_layout.addWidget(header)

    def _create_input_bar(self, root_layout):
        input_bar = QFrame(objectName="InputBar")
        layout = QHBoxLayout(input_bar); layout.setContentsMargins(16, 12, 16, 12); layout.setSpacing(10)
        self.url_input = QLineEdit(placeholderText="TVer 영상 URL 붙여넣기", objectName="UrlInput")
        self.bulk_button = QPushButton("다중 추가")
        self.add_button = QPushButton("다운로드", objectName="PrimaryButton")
        # 다운로드 버튼은 accent로 채워지므로 아이콘도 그 위에서 읽히는 색으로 칠한다.
        self._register_icon(self.bulk_button, "bulk_add")
        self._register_icon(self.add_button, "download", color_key="primary_fg")
        for btn in (self.bulk_button, self.add_button):
            btn.setIconSize(QSize(self.ICON_SIZE, self.ICON_SIZE))
        layout.addWidget(self.url_input, 1); layout.addWidget(self.bulk_button); layout.addWidget(self.add_button)
        root_layout.addWidget(input_bar)

    def _create_tabs(self, root_layout):
        self.tabs = QTabWidget(objectName="MainTabs")
        self.tabs.setIconSize(QSize(self.ICON_SIZE, self.ICON_SIZE))
        # 세그먼트 컨트롤 모양은 QSS가 그린다. 구조는 QTabWidget 그대로다.
        self.tabs.setDocumentMode(True)
        tab_bar = self.tabs.tabBar()
        tab_bar.setDrawBase(False)          # 탭 아래 기본 밑줄 제거
        tab_bar.setExpanding(False)         # 탭이 폭 전체로 늘어나지 않게
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
            # 선택된 탭만 그 탭의 포인트 컬러로 칠해 화면마다 다른 인상을 준다.
            color_key = ctx_key if index == current else "text_dim"
            self.tabs.setTabIcon(index, get_icon(name, self._icon_colors[color_key], self.ICON_SIZE))

    def _create_download_tab(self):
        tab = QWidget(objectName="DownloadTab"); layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12); layout.setSpacing(8)
        splitter = QSplitter(Qt.Orientation.Horizontal, objectName="MainSplitter")
        left_pane = QFrame(objectName="LeftPane"); left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(8, 8, 8, 8); row = QHBoxLayout()
        self.queue_label = QLabel("다운로드 목록", objectName="PaneTitle")
        self.clear_completed_button = QPushButton("완료 항목 삭제")
        self.queue_count_label = QLabel("0 대기 / 0 진행", objectName="PaneSubtitle")
        row.addWidget(self.queue_label); row.addStretch(1)
        row.addWidget(self.clear_completed_button)
        row.addWidget(self.queue_count_label)
        left_layout.addLayout(row)
        self.download_list = QListWidget(objectName="DownloadList")
        self.download_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # --- 다중 선택 모드 설정 ---
        self.download_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.download_list.setSpacing(6)
        left_layout.addWidget(self.download_list, 1)
        right_pane = QFrame(objectName="RightPane"); right_layout = QVBoxLayout(right_pane)
        right_layout.setContentsMargins(8, 8, 8, 8); row_log = QHBoxLayout()
        self.log_title = QLabel("로그", objectName="PaneTitle")
        self.clear_log_button = QPushButton("지우기")
        row_log.addWidget(self.log_title); row_log.addStretch(1); row_log.addWidget(self.clear_log_button)
        self.log_output = QTextEdit(objectName="LogOutput", readOnly=True)
        right_layout.addLayout(row_log); right_layout.addWidget(self.log_output, 1)
        splitter.addWidget(left_pane); splitter.addWidget(right_pane); splitter.setSizes([640, 480])
        layout.addWidget(splitter, 1); self.tabs.addTab(tab, "다운로드")

    def _create_history_tab(self):
        tab = QWidget(objectName="HistoryTab")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        top_controls = QHBoxLayout()
        self.history_title = QLabel("다운로드 기록", objectName="PaneTitle")
        self.history_sort_combo = QComboBox()
        self.history_sort_combo.addItem("다운로드 최신순")
        self.history_sort_combo.addItem("제목 오름차순")
        self.history_search_input = QLineEdit(placeholderText="검색...")
        self.history_search_input.setClearButtonEnabled(True)
        self.history_search_input.setFixedWidth(200)
        top_controls.addWidget(self.history_title)
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
        tab = QWidget(objectName="FavoritesTab")
        layout = QVBoxLayout(tab); layout.setContentsMargins(12, 12, 12, 12); layout.setSpacing(8)
        row = QHBoxLayout(); row.addWidget(QLabel("즐겨찾기 (시리즈)", objectName="PaneTitle")); row.addStretch(1); layout.addLayout(row)
        ctrl = QHBoxLayout()
        self.fav_input = QLineEdit(placeholderText="TVer 시리즈 URL (예: https://tver.jp/series/....)")
        self.fav_add_btn = QPushButton("추가")
        self.fav_del_btn = QPushButton("삭제", objectName="DangerButton")
        self.fav_chk_btn = QPushButton("신규 영상 확인")
        ctrl.addWidget(self.fav_input, 1); ctrl.addWidget(self.fav_add_btn); ctrl.addWidget(self.fav_del_btn)
        ctrl.addWidget(self.fav_chk_btn); layout.addLayout(ctrl)
        self.fav_list = QListWidget(objectName="FavoritesList"); self.fav_list.setSpacing(6)
        self.fav_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self.fav_list, 1); self.tabs.addTab(tab, "즐겨찾기")
    
    def setup_tray(self, app_version):
        tray_icon = self.main_window.tray_icon; tray_icon.setIcon(get_app_icon())
        tray_icon.setToolTip(f"{localized_app_name()} {app_version}")
        tray_menu = QMenu()
        restore_action = QAction("창 복원", self.main_window, triggered=self.main_window.bring_to_front)
        quit_action = QAction("완전 종료", self.main_window, triggered=self.main_window.quit_application)
        tray_menu.addAction(restore_action); tray_menu.addAction(quit_action)
        tray_icon.setContextMenu(tray_menu); tray_icon.show()