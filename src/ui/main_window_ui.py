from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QTextEdit,
    QLabel, QListWidget, QFrame, QTabWidget, QToolButton,
    QComboBox, QAbstractItemView, QBoxLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize, QObject, QEvent, QTimer
from PyQt6.QtGui import QAction, QFont, QColor, QTextCursor, QTextCharFormat

import webbrowser

from src import autostart, shortcuts
from src.appicon import get_app_icon, app_icon_with_progress
from src.titlelogo import LOGO_HEIGHT, build_logo, left_padding
from src.utils import localized_app_name
from src.i18n import t
from src.icons import get_icon, get_hover_icon
from src.qss import palette, SIDE_MARGIN, SIDE_MARGIN_WIDE, COMFORTABLE_WIDTH, SECTION_SPACING
from src.qtparts import (GridListWidget, RoundedMenu, NoFocusDelegate,
                         HoverTabBar, apply_smooth_wheel, FlowLayout)
from src.window_frame import DragBar, ShadowShell, WindowFrame, extra_size
from src.widgets import FavoriteItemWidget, EmptyStateOverlay

class MainWindowUI(QObject):
    ICON_BUTTON_SIZE = 32
    ICON_SIZE = 20
    MIN_WIDTH = 680
    MIN_WIDTH_WITH_LOG = 710
    MIN_HEIGHT = 460
    """작은 작업 영역에서는 도구 행을 감싸고 로그를 아래로 내려 이 크기까지 허용한다."""
    SIDE_LIST_MIN_WIDTH = 548
    COMPACT_LOG_HEIGHT = 120
    WIDGET_SIZE_MAX = 16777215
    """좌우 배치에서는 카드 폭을 지키고, 위아래 배치에서는 로그가 목록 높이를 독점하지 않는다."""
    NOTICE_ICON_SPACE = 56
    """짧은 안내에서 아이콘과 좌우 여백을 뺀 나머지만 글자에 내준다."""
    NOTICE_SUCCESS_HOLD_MS = 10_000
    """경고를 대신한 좋은 소식을 보여 주는 시간(ms). 그 뒤에는 목록에 자리를 돌려준다.

    확인만 하면 되는 소식이라 계속 둘 이유가 없고, 그렇다고 곧바로 감추면 빨간 줄이
    초록으로 바뀌는 것을 놓친다. 10초는 사용자가 정한 값이다(2026-09-10).
    """
    DEFAULT_WIDTH = 1100
    DEFAULT_HEIGHT = 700
    """처음 뜰 때의 크기. 화면이 이보다 좁으면 `_apply_initial_geometry`가 줄인다."""
    TAB_ICONS = (("download", "ctx_download", "download_tab.tab_tooltip"),
                 ("tab_history", "ctx_history", "history_tab.tab_tooltip"),
                 ("tab_favorites", "ctx_favorites", "favorites_tab.tab_tooltip"))
    """탭마다 (아이콘, 강조색, 툴팁 키). 문자열 값을 직접 담으면 클래스 정의 시점(모듈
    로드 시)에 언어가 굳으므로 t()로 매번 새로 찾을 키만 담는다."""
    FAV_COLUMNS = 2
    FAV_MIN_CARD_WIDTH = 340
    LOG_PANE_WIDTH = 390
    """좌우 배치에서만 폭을 고정하고 목록이 좁아지면 로그를 아래로 옮긴다."""

    LEFT_PANE_MIN_WIDTH = 360

    TAB_MARGIN = SIDE_MARGIN
    TAB_SPACING = SECTION_SPACING
    """헤더·입력바·탭의 왼쪽 끝을 맞추도록 여백 기준을 QSS에서 함께 받는다."""

    HEADER_ROW_HEIGHT = 32
    """한 줄 높이를 맞추고, 긴 번역으로 감싼 도구 행은 필요한 만큼 늘린다."""

    SEARCH_INPUT_WIDTH = 200
    FAV_INPUT_WIDTH = 280
    """시리즈 URL은 190px 남짓이라 이만큼이면 충분하다. 다 먹게 두면 옆 버튼이 밀린다."""

    SHORTCUT_HINT_BUTTONS = {
        "open_settings": "settings_button",
        "toggle_log": "log_toggle_btn",
    }
    """툴팁 끝에 지금 걸린 조합을 붙일 버튼.

    조합을 사용자가 바꿀 수 있게 된 이상 지금 값이 화면 어딘가에는 보여야 한다.
    """

    def _tab_page(self, object_name: str):
        """탭 한 장과 그 세로 레이아웃을 같은 여백으로 만들어 돌려준다."""
        tab = QWidget(objectName=object_name)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(self.TAB_MARGIN, self.TAB_MARGIN,
                                  self.TAB_MARGIN, self.TAB_MARGIN)
        layout.setSpacing(self.TAB_SPACING)
        self._tab_layouts.append(layout)
        return tab, layout

    def _toolbar(self, parent_layout):
        bar = QWidget(objectName="PaneToolbar")
        row = FlowLayout(bar, self.TAB_SPACING)
        parent_layout.addWidget(bar)
        return bar, row

    def _button_group(self, *widgets):
        group = QWidget(objectName="ToolbarGroup")
        row = QHBoxLayout(group)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        for widget in widgets:
            row.addWidget(widget)
        return group

    def _make_pane_title(self, text: str) -> QLabel:
        """탭 제목 라벨. 높이를 고정해 제목 줄 전체 높이를 붙든다."""
        label = QLabel(text, objectName="PaneTitle")
        label.setMinimumHeight(self.HEADER_ROW_HEIGHT)
        return label

    def _hide_focus_rect(self, list_widget):
        """고른 행에 사각 초점 선이 그려지지 않게 한다. 델리게이트는 목록과 수명을 같이한다."""
        list_widget.setItemDelegate(NoFocusDelegate(list_widget))

    def _add_empty_state(self, list_widget, icon_name, title, description,
                         filtered_title="", filtered_description=""):
        """목록에 빈 상태 안내를 얹고 테마 전환 대상으로 등록한다."""
        overlay = EmptyStateOverlay(list_widget, icon_name, title, description,
                                    filtered_title, filtered_description,
                                    theme=self._theme)
        self._empty_states.append(overlay)
        return overlay

    def _make_search_input(self, placeholder: str = None) -> QLineEdit:
        """탭 제목 줄 오른쪽에 놓는 검색칸. 세 탭이 같은 모양을 쓴다.

        기본값을 None으로 두는 것은 t()를 매개변수 자리에 직접 넣으면 이 메서드를
        정의하는 모듈 로드 시점에 언어가 굳기 때문이다 - 본문에서 매번 새로 구한다.
        """
        box = QLineEdit(placeholderText=placeholder or t("common.search_placeholder"))
        box.setClearButtonEnabled(True)
        box.setFixedWidth(self.SEARCH_INPUT_WIDTH)
        return box

    EXTRA_WIDTH, EXTRA_HEIGHT = extra_size()
    """그림자 여백 때문에 창이 내용보다 커지는 폭과 높이.

    MIN_* · DEFAULT_*는 내용 기준 값이라, 창에 넣을 때는 이만큼 더한다. 더하지 않으면
    최소 폭 창에서 내용이 여백만큼 좁아져 카드가 눌린다.
    """

    @classmethod
    def window_size(cls, width: int, height: int) -> tuple[int, int]:
        """내용 크기를 그림자 여백까지 포함한 창 크기로 바꾼다."""
        return width + cls.EXTRA_WIDTH, height + cls.EXTRA_HEIGHT

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        main_window.setWindowIcon(get_app_icon())
        main_window.setMinimumSize(*self.window_size(self.MIN_WIDTH, self.MIN_HEIGHT))
        main_window.resize(*self.window_size(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT))
        self._icon_buttons = []
        self._empty_states = []
        self._theme = "light"
        self._icon_colors = palette("light")
        self._log_visible = True
        self._shortcut_hint_bases = {}
        self._shortcut_hints = {}
        self._tab_layouts = []
        self._notice = ("", "notice")
        self._notice_warned = False
        """경고를 한 번이라도 보여 줬는가. 좋은 소식을 보일지 가르는 기준이다."""
        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.timeout.connect(self._retire_notice)
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.timeout.connect(self._update_layout)

    def _register_icon(self, btn, icon_name, color_key="text"):
        """버튼에 아이콘 정보를 붙이고 테마 전환 대상으로 등록한다."""
        btn.setProperty("icon_name", icon_name)
        btn.setProperty("icon_color_key", color_key)
        self._icon_buttons.append(btn)
        self._paint_icon(btn)
        return btn

    def _paint_icon(self, btn):
        """버튼 아이콘을 지금 테마 색으로 다시 칠한다.

        `icon_hover_key`가 붙어 있으면 커서를 올렸을 때 쓸 색까지 함께 담는다 - 배경이
        확 바뀌는 닫기 단추에서 글리프가 묻히지 않게 하는 자리다.
        """
        color = self._icon_colors[btn.property("icon_color_key") or "text"]
        name = btn.property("icon_name")
        hover_key = btn.property("icon_hover_key")
        if hover_key:
            btn.setIcon(get_hover_icon(name, color, self._icon_colors[hover_key]))
            return
        btn.setIcon(get_icon(name, color))

    def _make_icon_button(self, icon_name, tooltip, checkable=False):
        btn = QToolButton(objectName="IconButton", toolTip=tooltip)
        btn.setFixedSize(self.ICON_BUTTON_SIZE, self.ICON_BUTTON_SIZE)
        btn.setIconSize(QSize(self.ICON_SIZE, self.ICON_SIZE))
        btn.setCheckable(checkable)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return self._register_icon(btn, icon_name)

    def apply_theme(self, theme):
        """테마 전환 시 아이콘 색을 다시 칠한다. QSS는 호출부에서 따로 적용한다."""
        previous_colors = self._icon_colors
        self._theme = theme
        self._icon_colors = palette(theme)
        self._recolor_log(previous_colors)
        self._apply_title_logo()
        self.update_theme_button(theme)
        self.update_pin_button(self.on_top_btn.isChecked())
        for btn in self._icon_buttons:
            self._paint_icon(btn)
        for overlay in self._empty_states:
            overlay.apply_theme(theme)
        self.refresh_tab_icons()
        self._paint_notice()

    def _recolor_log(self, previous_colors):
        """로그에 이미 들어간 안내도 새 테마 색으로 맞추되 본문과 선택은 보존한다."""
        if not hasattr(self, "log_output") or previous_colors == self._icon_colors:
            return
        mapping = {previous_colors[key].lower(): self._icon_colors[key]
                   for key in ("notice", "log_success", "danger", "warn")}
        document = self.log_output.document()
        block = document.begin()
        spans = []
        while block.isValid():
            fragment = block.begin()
            while not fragment.atEnd():
                text = fragment.fragment()
                color = mapping.get(text.charFormat().foreground().color().name().lower())
                if color:
                    spans.append((text.position(), text.length(), color))
                fragment += 1
            block = block.next()
        cursor = QTextCursor(document)
        cursor.beginEditBlock()
        for start, length, color in spans:
            cursor.setPosition(start)
            cursor.setPosition(start + length, QTextCursor.MoveMode.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            cursor.mergeCharFormat(fmt)
        cursor.endEditBlock()

    def update_theme_button(self, theme):
        """지금 테마가 아니라 '누르면 갈 테마'를 보여준다."""
        going_dark = theme == "light"
        self.theme_button.setProperty("icon_name", "theme_dark" if going_dark else "theme_light")
        self.theme_button.setToolTip(t("main_window.theme_dark_tooltip") if going_dark
                                     else t("main_window.theme_light_tooltip"))
        self._paint_icon(self.theme_button)

    def set_primary_action_enabled(self, enabled: bool):
        """다운로드 버튼의 아이콘 색을 활성 상태에 맞춘다. primary_fg는 비활성 배경에서 안 보인다."""
        self.add_button.setProperty("icon_color_key", "primary_fg" if enabled else "text_dim")
        self._paint_icon(self.add_button)

    LOGO_GAP = 8
    """앱 심벌과 제목 로고 글자 사이의 간격.

    로고 PNG 안의 투명 여백을 빼고 실제로 남는 간격이다 - 그 여백이 언어마다 달라
    (30px 높이에서 ko 18 / en 7 / jp 6) 그냥 두면 한국어만 심벌이 멀찍이 떨어져 보인다.
    """

    def _apply_title_logo(self):
        """헤더 제목을 앱 심벌 + 로고 이미지로 채운다. 못 읽으면 글자 제목으로 되돌아간다."""
        dpr = self.main_window.devicePixelRatioF() or 1.0
        self.app_symbol.setPixmap(get_app_icon().pixmap(QSize(LOGO_HEIGHT, LOGO_HEIGHT), dpr))
        pixmap = build_logo(self._theme, LOGO_HEIGHT, dpr)
        if pixmap is None:
            self.app_title.setText(localized_app_name())
            self.logo_gap.setFixedWidth(self.LOGO_GAP)
            return
        self.app_title.setPixmap(pixmap)
        self.logo_gap.setFixedWidth(max(0, self.LOGO_GAP - left_padding(pixmap)))

    def update_pin_button(self, on):
        self.on_top_btn.setProperty("icon_name", "pin_on" if on else "pin")
        self._paint_icon(self.on_top_btn)

    def _set_hinted_tooltip(self, attribute: str, base: str):
        """원래 문구를 기억해 두고, 뒤에 지금 걸린 조합을 붙여 툴팁으로 넣는다.

        이미 붙은 문자열에 다시 붙이면 설정을 열고 닫을 때마다 조합이 줄줄이 쌓인다.
        """
        self._shortcut_hint_bases[attribute] = base
        hint = self._shortcut_hints.get(attribute, "")
        getattr(self, attribute).setToolTip(f"{base} ({hint})" if hint else base)

    def apply_shortcut_hints(self, table: dict):
        """버튼 툴팁 끝에 지금 걸린 조합을 붙인다.

        문구는 버튼이 지금 들고 있는 것을 쓴다 - 로그 토글처럼 상태에 따라 문구가 바뀌는
        버튼이 있어, 처음 문구를 고정으로 잡으면 바뀐 뒤에 엉뚱한 안내가 남는다.
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
        """창을 두 겹으로 짠다 - 그림자를 그리는 껍데기와 그 안의 둥근 표면.

        내용은 모두 표면에 담긴다. 껍데기가 한 겹 더 있는 것은 제목 표시줄을 떼면서
        그림자를 우리가 그리게 됐고, 그림자가 번질 여백이 창 안에 있어야 하기 때문이다.
        """
        shell = ShadowShell()
        self.window_shell = shell
        self.window_frame = WindowFrame(self.main_window,
                                        on_changed=self.set_window_maximized)
        self.main_window.setCentralWidget(shell)
        root = QVBoxLayout(shell.surface); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        self._create_header(root)
        self._create_input_bar(root)
        self._create_tabs(root)
        shell.surface.installEventFilter(self)
        self.download_toolbar.installEventFilter(self)
        self._layout_timer.start(0)

    WINDOW_BUTTON_GAP = 18
    """앱 아이콘 단추 넷과 창 단추 셋 사이의 간격.

    하는 일이 달라(앱을 다루는 것 / 창을 다루는 것) 붙여 두면 일곱 개가 한 줄로 읽힌다.
    """

    def _create_header(self, root_layout):
        """헤더는 제목 표시줄을 대신한다 - 빈 자리를 끌면 창이 따라오고 두 번 누르면 최대화된다."""
        header = DragBar(objectName="AppHeader")
        header.frame = self.window_frame
        self.app_header = header
        layout = QHBoxLayout(header)
        layout.setContentsMargins(SIDE_MARGIN, 8, SIDE_MARGIN, 8); layout.setSpacing(4)
        self.app_symbol = QLabel(objectName="AppSymbol")
        self.app_symbol.setFixedSize(LOGO_HEIGHT, LOGO_HEIGHT)
        self.logo_gap = QWidget()
        self.logo_gap.setFixedHeight(1)
        self.app_title = QLabel(objectName="AppTitle")
        self.app_title.setFixedHeight(LOGO_HEIGHT)
        self._apply_title_logo()
        self.settings_button = self._make_icon_button("settings", t("main_window.settings_tooltip"))
        self.theme_button = self._make_icon_button("theme_dark", t("main_window.theme_dark_tooltip"))
        self.on_top_btn = self._make_icon_button("pin", t("main_window.pin_tooltip"), checkable=True)
        self.about_button = self._make_icon_button("info", t("main_window.about_tooltip"))
        self.min_button = self._make_icon_button("window_minimize", t("main_window.minimize_tooltip"))
        self.max_button = self._make_icon_button("window_maximize", t("main_window.maximize_tooltip"))
        self.close_button = self._make_icon_button("cancel", t("common.close"))
        self.close_button.setProperty("window_close", "true")
        self.close_button.setProperty("icon_hover_key", "danger_fg")
        self._paint_icon(self.close_button)
        layout.addWidget(self.app_symbol)
        layout.addWidget(self.logo_gap)
        layout.addWidget(self.app_title); layout.addStretch(1)
        for btn in (self.settings_button, self.theme_button,
                    self.on_top_btn, self.about_button):
            btn.setProperty("icon_color_key", "text_dim")
            self._paint_icon(btn)
            layout.addWidget(btn)
        layout.addSpacing(self.WINDOW_BUTTON_GAP)
        for btn in (self.min_button, self.max_button, self.close_button):
            layout.addWidget(btn)
        root_layout.addWidget(header)

    def set_window_maximized(self, maximized: bool):
        """최대화 상태를 창 모양과 최대화 단추에 함께 반영한다.

        모서리를 각지게 펴는 것은 화면에 꽉 찬 창에서 둥근 모서리 밖으로 바탕 화면이
        비쳐 보이기 때문이다. 단추는 지금 상태가 아니라 '누르면 갈 곳'을 보여 준다.

        **속성 이름을 `maximized`로 두면 안 된다** - Qt가 이미 쓰는 이름이라 우리가 적은
        문자열이 들어가지 않고 bool로 읽혀(실측: 넣은 뒤 읽어도 False) QSS 규칙이 영영
        걸리지 않는다. 모서리가 최대화해도 둥근 채 남는 것으로만 드러난다.
        """
        self.window_shell.set_maximized(maximized)
        flag = "true" if maximized else "false"
        for widget in (self.window_shell.surface, self.app_header):
            widget.setProperty("window_maximized", flag)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.max_button.setProperty("icon_name",
                                    "window_restore" if maximized else "window_maximize")
        self.max_button.setToolTip(t("main_window.restore_tooltip") if maximized
                                   else t("main_window.maximize_tooltip"))
        self._paint_icon(self.max_button)

    def toggle_maximized(self):
        """최대화와 원래 크기를 오간다. 최대화 단추와 헤더 더블클릭이 같은 길을 쓴다."""
        self.window_frame.toggle()

    def _create_input_bar(self, root_layout):
        input_bar = QFrame(objectName="InputBar")
        self.input_bar = input_bar
        layout = QHBoxLayout(input_bar)
        layout.setContentsMargins(SIDE_MARGIN, 12, SIDE_MARGIN, 12); layout.setSpacing(10)
        self.url_input = QLineEdit(placeholderText=t("main_window.url_placeholder"), objectName="UrlInput")
        self.url_input.setToolTip(t("main_window.url_tooltip"))
        self.bulk_button = QPushButton(t("main_window.bulk_add_button"))
        self.add_button = QPushButton(t("main_window.download_button"), objectName="PrimaryButton")
        self._register_icon(self.bulk_button, "bulk_add")
        self._register_icon(self.add_button, "download", color_key="primary_fg")
        for btn in (self.bulk_button, self.add_button):
            btn.setIconSize(QSize(self.ICON_SIZE, self.ICON_SIZE))
        for widget in (self.url_input, self.bulk_button, self.add_button):
            widget.setMinimumHeight(self.HEADER_ROW_HEIGHT + 4)
        layout.addWidget(self.url_input, 1); layout.addWidget(self.bulk_button); layout.addWidget(self.add_button)
        root_layout.addWidget(input_bar)

    def _create_tabs(self, root_layout):
        self.tabs = QTabWidget(objectName="MainTabs")
        self.tabs.setIconSize(QSize(self.ICON_SIZE, self.ICON_SIZE))
        self.tabs.setTabBar(HoverTabBar())
        self.tabs.setDocumentMode(True)
        tab_bar = self.tabs.tabBar()
        tab_bar.setDrawBase(False)
        tab_bar.setExpanding(False)
        self._create_download_tab()
        self._create_history_tab()
        self._create_favorites_tab()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.refresh_tab_icons()
        self._apply_tab_tooltips()
        root_layout.addWidget(self.tabs, 1)

    def _on_tab_changed(self, _index):
        self.refresh_tab_icons()
        self._layout_timer.start(0)

    def refresh_tab_icons(self):
        """선택된 탭만 진하게 칠한다.

        QTabBar는 QIcon의 Selected 모드를 쓰지 않아 선택이 바뀔 때마다 새로 만들어 넣는다.
        """
        current = self.tabs.currentIndex()
        for index, (name, ctx_key, _tooltip) in enumerate(self.TAB_ICONS):
            if index >= self.tabs.count():
                break
            color_key = ctx_key if index == current else "text_dim"
            self.tabs.setTabIcon(index, get_icon(name, self._icon_colors[color_key], self.ICON_SIZE))

    def _apply_tab_tooltips(self):
        for index, (_name, _ctx_key, tooltip_key) in enumerate(self.TAB_ICONS):
            if index >= self.tabs.count():
                break
            self.tabs.setTabToolTip(index, t(tooltip_key))

    def _create_download_tab(self):
        """사용자가 분할 폭을 복원할 필요 없이 창 크기에 맞춰 목록과 로그를 배치한다."""
        tab, layout = self._tab_page("DownloadTab")
        panes = QHBoxLayout(); panes.setContentsMargins(0, 0, 0, 0)
        self.download_panes = panes
        panes.setSpacing(self.TAB_SPACING)

        left_pane = QFrame(objectName="LeftPane"); left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(self.TAB_SPACING)
        self.download_toolbar, row = self._toolbar(left_layout)
        self.queue_start_button = QPushButton(t("download_tab.queue_start_button"), objectName="QueueStartButton")
        self.queue_start_button.setToolTip(t("download_tab.queue_start_tooltip"))
        self.queue_start_button.setVisible(False)
        self.cancel_selected_button = QPushButton(t("download_tab.cancel_selected_button"), objectName="DangerButton")
        self.cancel_selected_button.setToolTip(t("download_tab.cancel_selected_tooltip"))
        self.cancel_selected_button.setEnabled(False)
        self.clear_completed_button = QPushButton(t("download_tab.clear_completed_button"), objectName="CautionButton")
        self.queue_count_label = QLabel(t("download_tab.queue_count", queued=0, active=0), objectName="PaneSubtitle")
        self.log_toggle_btn = self._make_icon_button("log", t("download_tab.log_hide_tooltip"))
        summary = self._button_group(self._make_pane_title(t("download_tab.pane_title")), self.queue_count_label)
        row.addWidget(summary)
        row.addStretch()
        row.addWidget(self._button_group(self.queue_start_button, self.cancel_selected_button,
                                        self.clear_completed_button, self.log_toggle_btn))
        self.notice_bar = QPushButton(objectName="NoticeBar")
        self.notice_bar.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.notice_bar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.notice_bar.clicked.connect(self._open_notice_log)
        self.notice_bar.hide()
        left_layout.addWidget(self.notice_bar)
        self.download_list = QListWidget(objectName="DownloadList")
        self.download_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.download_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.download_list.setSpacing(6)
        self._hide_focus_rect(self.download_list)
        apply_smooth_wheel(self.download_list)
        self.download_empty = self._add_empty_state(
            self.download_list, "download", t("download_tab.empty_title"),
            t("download_tab.empty_description"))
        left_layout.addWidget(self.download_list, 1)

        right_pane = QFrame(objectName="RightPane"); right_layout = QVBoxLayout(right_pane)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(self.TAB_SPACING)
        self.log_header = QWidget(objectName="PaneToolbar")
        row_log = QHBoxLayout(self.log_header)
        row_log.setContentsMargins(0, 0, 0, 0)
        row_log.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.clear_log_button = QPushButton(t("download_tab.log_clear_button"))
        self.clear_log_button.setToolTip(t("download_tab.log_clear_tooltip"))
        row_log.addWidget(self._make_pane_title(t("download_tab.log_pane_title"))); row_log.addStretch(1)
        row_log.addWidget(self.clear_log_button)
        self.log_output = QTextEdit(objectName="LogOutput", readOnly=True)
        right_layout.addWidget(self.log_header); right_layout.addWidget(self.log_output, 1)
        right_pane.setFixedWidth(self.LOG_PANE_WIDTH)

        self.log_pane = right_pane
        left_pane.setMinimumWidth(self.LEFT_PANE_MIN_WIDTH)
        panes.addWidget(left_pane, 1); panes.addWidget(right_pane)
        layout.addLayout(panes, 1); self.tabs.addTab(tab, t("download_tab.tab_title"))

    def set_queue_start_visible(self, visible: bool):
        """되살린 항목이 있을 때만 시작 단추를 보여 주고 도구 행 높이를 다시 맞춘다."""
        self.queue_start_button.setVisible(visible)
        self.download_toolbar.layout().invalidate()
        self._layout_timer.start(0)

    def set_log_visible(self, visible: bool):
        """로그 표시 선택은 창 폭이 바뀌어도 유지하고 접은 동안의 안내는 별도로 남긴다."""
        self.log_pane.setVisible(visible)
        self.main_window.setMinimumWidth(
            (self.MIN_WIDTH_WITH_LOG if visible else self.MIN_WIDTH) + self.EXTRA_WIDTH)
        self._log_visible = visible
        self.update_log_toggle_button(visible)
        self._paint_notice()
        self._layout_timer.start(0)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.LayoutRequest):
            self._layout_timer.start(0)
        return False

    def _update_layout(self):
        """그림자 바깥 폭 대신 실제 내용 폭을 써서 배율과 로그 표시가 바뀌어도 잘림을 막는다."""
        surface = self.window_shell.surface
        comfortable = surface.width() >= COMFORTABLE_WIDTH
        margin = SIDE_MARGIN_WIDE if comfortable else SIDE_MARGIN
        for layout in self._tab_layouts:
            if layout.contentsMargins().left() != margin:
                layout.setContentsMargins(margin, margin, margin, margin)
        for widget in (self.app_header, self.input_bar):
            layout = widget.layout()
            current = layout.contentsMargins()
            if current.left() != margin:
                layout.setContentsMargins(margin, current.top(), margin, current.bottom())
        flag = "true" if comfortable else "false"
        if self.tabs.property("comfortable") != flag:
            self.tabs.setProperty("comfortable", flag)
            self.tabs.style().unpolish(self.tabs)
            self.tabs.style().polish(self.tabs)
        for toolbar in (self.download_toolbar, self.history_toolbar, self.favorites_toolbar):
            if toolbar.isVisible():
                height = toolbar.layout().heightForWidth(toolbar.width())
                if toolbar.height() != height or toolbar.minimumHeight() != height:
                    toolbar.setFixedHeight(height)
        available = surface.width() - 2 * margin - self.TAB_SPACING
        stacked = available < self.SIDE_LIST_MIN_WIDTH + self.LOG_PANE_WIDTH
        direction = QBoxLayout.Direction.TopToBottom if stacked else QBoxLayout.Direction.LeftToRight
        if self.download_panes.direction() != direction:
            self.download_panes.setDirection(direction)
        self.log_pane.setMinimumWidth(0 if stacked else self.LOG_PANE_WIDTH)
        self.log_pane.setMaximumWidth(self.WIDGET_SIZE_MAX if stacked else self.LOG_PANE_WIDTH)
        self.log_pane.setMaximumHeight(self.COMPACT_LOG_HEIGHT if stacked else self.WIDGET_SIZE_MAX)
        height = self.HEADER_ROW_HEIGHT if stacked else self.download_toolbar.height()
        if not stacked and self.notice_bar.isVisible():
            height += self.notice_bar.height() + self.TAB_SPACING
        if self.log_header.height() != height:
            self.log_header.setFixedHeight(height)
        text = self._notice[0]
        self.notice_bar.setText(self.notice_bar.fontMetrics().elidedText(
            text, Qt.TextElideMode.ElideRight,
            max(0, self.notice_bar.width() - self.NOTICE_ICON_SPACE)))

    def set_notice(self, text, color_key="notice"):
        """목록 위 한 줄 안내를 갈아 끼운다.

        **좋은 소식은 나쁜 소식을 대신할 때만, 그것도 잠깐만 보인다**(사용자 결정,
        2026-09-10). 경고가 그냥 사라지기만 하면 왜 사라졌는지 알 수 없어 빨간 줄이
        초록으로 바뀌는 것을 보여 주고, 확인한 뒤에는 목록에 자리를 돌려준다. 처음부터
        정상인 사람에게는 아예 뜨지 않는다.
        """
        self._notice_timer.stop()
        if color_key != "log_success":
            self._notice_warned = True
        elif self._notice_warned:
            self._notice_timer.start(self.NOTICE_SUCCESS_HOLD_MS)
        self._notice = (text, color_key)
        self._paint_notice()

    def _retire_notice(self):
        """다 보여 준 좋은 소식을 감춘다. 다음 경고가 오면 이 주기를 처음부터 다시 지난다."""
        self._notice_warned = False
        self._paint_notice()
        self._layout_timer.start(0)

    def _paint_notice(self):
        if not hasattr(self, "notice_bar"):
            return
        text, color_key = self._notice
        self.notice_bar.setText(text)
        self.notice_bar.setToolTip(text + "\n" + t("download_tab.log_show_tooltip"))
        if self.notice_bar.property("tone") != color_key:
            self.notice_bar.setProperty("tone", color_key)
            self.notice_bar.style().unpolish(self.notice_bar)
            self.notice_bar.style().polish(self.notice_bar)
        self.notice_bar.setIcon(get_icon("info", self._icon_colors[color_key], self.ICON_SIZE))
        tell = bool(text) and (color_key != "log_success" or self._notice_warned)
        self.notice_bar.setVisible(tell and not self._log_visible)
        self._layout_timer.start(0)

    def _open_notice_log(self):
        self.log_toggle_btn.click()

    def is_log_visible(self) -> bool:
        return self._log_visible

    def update_log_toggle_button(self, visible: bool):
        """지금 상태가 아니라 '누르면 일어날 일'을 알려 준다."""
        self._set_hinted_tooltip("log_toggle_btn",
                                 t("download_tab.log_hide_tooltip") if visible
                                 else t("download_tab.log_show_tooltip"))

    def _create_history_tab(self):
        tab, layout = self._tab_page("HistoryTab")
        self.history_toolbar, top_controls = self._toolbar(layout)
        self.history_del_btn = QPushButton(t("history_tab.delete_button"), objectName="DangerButton")
        self.history_del_btn.setToolTip(t("history_tab.delete_tooltip"))
        self.history_sort_combo = QComboBox()
        self.history_sort_combo.addItem(t("history_tab.sort_recent"))
        self.history_sort_combo.addItem(t("history_tab.sort_title"))
        self.history_search_input = self._make_search_input()
        top_controls.addWidget(self._make_pane_title(t("history_tab.pane_title")))
        top_controls.addStretch()
        top_controls.addWidget(self.history_del_btn)
        top_controls.addWidget(self.history_sort_combo)
        top_controls.addWidget(self.history_search_input)
        self.history_list = QListWidget(objectName="HistoryList")
        self.history_list.setSpacing(6)
        self._hide_focus_rect(self.history_list)
        apply_smooth_wheel(self.history_list)
        self.history_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.history_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history_empty = self._add_empty_state(
            self.history_list, "tab_history", t("history_tab.empty_title"),
            t("history_tab.empty_description"),
            t("history_tab.empty_filtered_title"), t("history_tab.empty_filtered_description"))
        layout.addWidget(self.history_list, 1)
        self.tabs.addTab(tab, t("history_tab.tab_title"))

    def _create_favorites_tab(self):
        tab, layout = self._tab_page("FavoritesTab")
        self.favorites_toolbar, row = self._toolbar(layout)
        row.addWidget(self._make_pane_title(t("favorites_tab.pane_title")))
        row.addStretch()
        self.fav_input = QLineEdit(placeholderText="https://tver.jp/series/...")
        self.fav_input.setFixedWidth(self.FAV_INPUT_WIDTH)
        self.fav_add_btn = QPushButton(t("favorites_tab.add_button"), objectName="AddButton")
        self.fav_del_btn = QPushButton(t("favorites_tab.delete_button"), objectName="DangerButton")
        self.fav_chk_btn = QPushButton(t("favorites_tab.refresh_button"), objectName="RefreshButton")
        self.fav_chk_btn.setToolTip(t("favorites_tab.refresh_tooltip"))
        self.fav_search_input = self._make_search_input()
        for widget in (self._button_group(self.fav_input, self.fav_add_btn),
                       self._button_group(self.fav_del_btn, self.fav_chk_btn), self.fav_search_input):
            row.addWidget(widget)
        self.fav_list = GridListWidget(columns=self.FAV_COLUMNS,
                                       min_item_width=self.FAV_MIN_CARD_WIDTH)
        self.fav_list.setObjectName("FavoritesList")
        self.fav_list.setSpacing(6)
        self._hide_focus_rect(self.fav_list)
        apply_smooth_wheel(self.fav_list)
        self.fav_list.set_item_height(FavoriteItemWidget.CARD_HEIGHT)
        self.fav_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.fav_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.fav_empty = self._add_empty_state(
            self.fav_list, "tab_favorites", t("favorites_tab.empty_title"),
            t("favorites_tab.empty_description"),
            t("favorites_tab.empty_filtered_title"), t("favorites_tab.empty_filtered_description"))
        layout.addWidget(self.fav_list, 1); self.tabs.addTab(tab, t("favorites_tab.tab_title"))

    TRAY_GITHUB_URL = "https://github.com/deuxdoom/TVerDownloader"

    def setup_tray(self, app_version):
        """트레이 아이콘과 우클릭 메뉴를 만든다.

        첫 항목은 '<앱 이름> 열기'다 - 이름만 적으면 제목처럼 읽혀 눌러도 되는 줄인지
        알기 어렵다. 구분선은 여는 일 / 설정 / 끝내는 일 세 덩이만 가른다. 시작 프로그램
        체크는 열 때마다 레지스트리를 다시 읽는다 - 밖에서 꺼 놓았을 수 있다.
        """
        tray_icon = self.main_window.tray_icon; tray_icon.setIcon(get_app_icon())
        self._tray_name = f"{localized_app_name()} {app_version}"
        self.update_tray_status(0, 0, None)
        tray_menu = RoundedMenu()

        restore_action = QAction(t("tray.open", app_name=localized_app_name()), self.main_window,
                                 triggered=self.main_window.bring_to_front)
        bold = QFont(restore_action.font()); bold.setBold(True)
        restore_action.setFont(bold)
        tray_menu.addAction(restore_action)
        tray_menu.addSeparator()

        self.autostart_action = QAction(t("tray.autostart"), self.main_window, checkable=True)
        self.autostart_action.toggled.connect(self.main_window.set_autostart)
        if not autostart.supported():
            self.autostart_action.setEnabled(False)
            self.autostart_action.setToolTip(t("tray.autostart_disabled_tooltip"))
        tray_menu.addAction(self.autostart_action)

        tray_menu.addAction(QAction(t("tray.github"), self.main_window,
                                    triggered=lambda: webbrowser.open(self.TRAY_GITHUB_URL)))

        tray_menu.addAction(QAction(t("tray.settings"), self.main_window,
                                    triggered=self.main_window.open_settings))
        tray_menu.addSeparator()

        tray_menu.addAction(QAction(t("tray.quit"), self.main_window,
                                    triggered=self.main_window.quit_application))

        tray_menu.aboutToShow.connect(self.sync_autostart_check)
        self.sync_autostart_check()
        tray_icon.setContextMenu(tray_menu); tray_icon.show()

    def update_tray_status(self, queued: int, active: int, percent=None):
        """트레이 툴팁을 지금 상태로 바꾼다.

        커서를 올려야 보이는 자리라 평소에는 앱 이름만 두고, 받는 중일 때만 줄을 늘린다.
        진행률은 실제로 도는 것이 있을 때만 붙는다(percent가 None이면 뺀다). 늘 보이는
        고리도 같은 값으로 바꾼다 - 둘이 다른 숫자를 말하면 어느 쪽을 믿을지 알 수 없다.
        """
        lines = [self._tray_name]
        if queued or active:
            head = t("tray.status", queued=queued, active=active)
            lines.append(f"{head} · {percent}%" if percent is not None else head)
        self.main_window.tray_icon.setToolTip("\n".join(lines))
        self.main_window.tray_icon.setIcon(app_icon_with_progress(percent))

    def sync_autostart_check(self):
        """레지스트리의 실제 상태로 체크를 맞춘다. toggled가 되돌아 또 쓰지 않게 잠시 끊는다."""
        self.autostart_action.blockSignals(True)
        self.autostart_action.setChecked(autostart.is_enabled())
        self.autostart_action.blockSignals(False)
