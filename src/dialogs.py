from __future__ import annotations
import html
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QKeySequence, QColor, QPalette
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSpinBox, QStackedWidget, QWidget, QFileDialog, QDialogButtonBox,
    QListWidget, QListWidgetItem, QAbstractItemView, QStyledItemDelegate,
    QRadioButton, QButtonGroup, QCheckBox, QFrame, QComboBox,
    QGroupBox, QGridLayout, QKeySequenceEdit, QSizePolicy
)
from src import i18n, shortcuts
from src.i18n import t
from src.icons import get_icon
from src.message import confirm, notify
from src.qss import palette, blend, FILENAME_PART_COLORS, FILENAME_PART_MUTED
from src.utils import (save_config, PARALLEL_MAX, FRAGMENTS_MIN, FRAGMENTS_MAX,
                       MAX_TOTAL_CONNECTIONS, canonicalize_config_fragments,
                       canonicalize_config_codec, canonicalize_config_encoder)
from src.thumbnails import THUMBNAIL_CACHE_DIR

ROLE_KEY = Qt.ItemDataRole.UserRole

PREVIEW_SAMPLES = {
    "series": "ドラえもん",
    "upload_date": "20260810",
    "episode_number": "199",
    "episode": "「のび太の惑星探査ミッション」",
    "id": "[epo78piojx]",
}
"""미리보기에 넣는 본보기 값.

**한 줄에 들어갈 만큼 짧게 둔다** - 두 줄로 접히면 체크 하나를 여닫을 때마다 글 전체가
밀려서, 정작 어느 조각이 빠졌는지가 그 움직임에 묻힌다. 확장자는 적지 않는다.
"""


def fit_combo_width(combo: QComboBox) -> None:
    """콤보를 항목이 요구하는 폭에 묶는다.

    가로로 늘어나게 두면 `한국어` 한 단어짜리 콤보가 창 폭을 통째로 차지한다(실측 530px).
    폭을 픽셀로 굳히지 않고 sizeHint에 맡기는 것은, 그 값이 가장 긴 항목에서 나와
    언어마다 알맞게 잡히고(ko 154 / es 280) QSS가 글꼴을 바꿔도 따라오기 때문이다.
    """
    combo.setSizePolicy(QSizePolicy.Policy.Fixed, combo.sizePolicy().verticalPolicy())


def part_color(theme: str, key: str, on: bool) -> str:
    """파일명 조각 하나에 쓸 글자색. 꺼 둔 것은 배경에 섞어 흐리게 만든다."""
    colors = palette(theme)
    base = FILENAME_PART_COLORS[theme].get(key, colors["text"])
    return base if on else blend(base, colors["bg"], FILENAME_PART_MUTED)


class PartColorDelegate(QStyledItemDelegate):
    """구성 요소 목록의 글자를 조각마다 정해 둔 색으로 그린다.

    ForegroundRole에 적어 두면 체크를 여닫을 때마다 다시 적어야 하고, 적는 일이
    itemChanged를 울려 같은 함수로 되돌아온다. 고른 행의 HighlightedText도 여기서 막는다 -
    끌어 옮기는 동안 그 항목만 색을 잃으면 지금 옮기는 것이 미리보기의 어디인지 짚을 수 없다.
    """

    def __init__(self, theme: str, parent=None):
        super().__init__(parent)
        self._theme = theme

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        color = QColor(part_color(
            self._theme, index.data(ROLE_KEY),
            option.checkState == Qt.CheckState.Checked,
        ))
        option.palette.setColor(QPalette.ColorRole.Text, color)
        option.palette.setColor(QPalette.ColorRole.HighlightedText, color)


class SettingsDialog(QDialog):

    LANGUAGE_SYSTEM = "system"
    """언어 콤보의 '자동 감지' 항목이 설정에 담는 값. i18n.resolve_code가 이 값을 OS 언어로 푼다."""

    def __init__(self, config: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self._theme = config.get("theme", "light")
        self.language_changed = False
        """언어를 실제로 바꿔 저장했는지. 호출부가 이것만 보고 재시작을 묻는다 -
        저장할 때마다 물으면 언어를 건드리지 않은 사람에게도 재시작 안내가 뜬다.

        **설정값 문자열이 아니라 실제로 쓰게 될 언어를 견준다.** 한국어 윈도우에서
        `자동 감지`와 `한국어`는 같은 결과인데, 문자열만 보면 그 사이를 오갈 때마다
        아무것도 달라지지 않는데도 재시작을 묻는다."""
        self.setWindowTitle(t("settings.title"))
        self.setMinimumSize(760, 580)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.nav = QListWidget(objectName="SettingsNav")
        self.nav.setFixedWidth(172)
        self.nav.setIconSize(QSize(18, 18))
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(self.nav)

        right = QVBoxLayout()
        right.setContentsMargins(20, 16, 20, 16)
        right.setSpacing(12)
        self.section_title = QLabel(objectName="SectionTitle")
        right.addWidget(self.section_title)
        self.pages = QStackedWidget()
        right.addWidget(self.pages, 1)

        self._create_general_tab()
        self._create_shortcuts_tab()
        self._create_filename_tab()
        self._create_quality_tab()
        self._create_subtitle_tab()
        self._create_advanced_tab()
        self._create_cache_tab()

        self.buttons = QDialogButtonBox()
        save_btn = self.buttons.addButton(t("settings.save"), QDialogButtonBox.ButtonRole.AcceptRole)
        save_btn.setObjectName("PrimaryButton")
        exit_btn = self.buttons.addButton(t("settings.exit"), QDialogButtonBox.ButtonRole.RejectRole)
        right.addWidget(self.buttons)
        root.addLayout(right, 1)

        save_btn.clicked.connect(self._save_settings)
        exit_btn.clicked.connect(self.reject)

        self.nav.currentRowChanged.connect(self._on_nav_changed)
        self.nav.setCurrentRow(0)

    def _nav_icon(self, icon_name: str) -> QIcon:
        """평소엔 흐리게, 선택되면 accent로 보이는 아이콘을 만든다."""
        colors = palette(self._theme)
        normal = get_icon(icon_name, colors["text_dim"], 18).pixmap(18, 18)
        selected = get_icon(icon_name, colors["ctx_settings"], 18).pixmap(18, 18)
        icon = QIcon(normal)
        if not selected.isNull():
            icon.addPixmap(selected, QIcon.Mode.Selected)
        return icon

    def _add_page(self, widget: QWidget, title: str, icon_name: str):
        """페이지를 스택에 넣고 좌측 내비게이션 항목을 추가한다."""
        self.pages.addWidget(widget)
        item = QListWidgetItem(self._nav_icon(icon_name), title)
        item.setSizeHint(QSize(0, 40))
        self.nav.addItem(item)

    def _on_nav_changed(self, row: int):
        if row < 0:
            return
        self.pages.setCurrentIndex(row)
        self.section_title.setText(self.nav.item(row).text())

    def showEvent(self, event):
        super().showEvent(event)
        self._update_cache_label()

    def _calculate_cache_size(self) -> str:
        try:
            total_size = sum(f.stat().st_size for f in THUMBNAIL_CACHE_DIR.glob('**/*') if f.is_file())
            if total_size < 1024: return f"{total_size} Bytes"
            elif total_size < 1024**2: return f"{total_size/1024:.2f} KB"
            else: return f"{total_size/1024**2:.2f} MB"
        except FileNotFoundError: return "0 Bytes"

    def _update_cache_label(self):
        self.cache_size_label.setText(self._calculate_cache_size())

    def _clear_thumbnail_cache(self):
        if not confirm(self, t("settings.cache_confirm_title"), t("settings.cache_confirm_body"),
                       icon_name="nav_cache", color_key="danger", theme=self._theme):
            return
        count = 0
        try:
            for f in THUMBNAIL_CACHE_DIR.glob('**/*'):
                if f.is_file(): f.unlink(); count += 1
            notify(self, t("settings.cache_done_title"),
                   t("settings.cache_done_body", count=count),
                   icon_name="nav_cache", theme=self._theme)
        except Exception as e:
            notify(self, t("settings.cache_error_title"),
                   t("settings.cache_error_body", error=e),
                   icon_name="nav_cache", color_key="danger", theme=self._theme)
        finally:
            self._update_cache_label()

    def _create_general_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setSpacing(15)

        lang_group = QWidget(); lang_layout = QVBoxLayout(lang_group)
        lang_layout.setContentsMargins(0, 0, 0, 0); lang_layout.setSpacing(10)
        lang_layout.addWidget(QLabel(t("settings.language_label")))
        self.language_combo = QComboBox()
        self.language_combo.setToolTip(t("settings.language_tooltip"))
        self.language_combo.addItem(t("settings.language_system"), userData=self.LANGUAGE_SYSTEM)
        for info in i18n.available_languages():
            self.language_combo.addItem(info.display_name, userData=info.code)
        current_language = self.config.get("language", self.LANGUAGE_SYSTEM)
        index = self.language_combo.findData(current_language)
        self.language_combo.setCurrentIndex(index if index >= 0 else 0)
        fit_combo_width(self.language_combo)
        lang_layout.addWidget(self.language_combo); layout.addWidget(lang_group)

        folder_group = QWidget(); folder_layout = QVBoxLayout(folder_group); folder_layout.setContentsMargins(0,0,0,0)
        folder_layout.addWidget(QLabel(t("settings.folder_label")))
        row = QHBoxLayout()
        self.folder_path_edit = QLineEdit(self.config.get("download_folder", "")); self.folder_path_edit.setReadOnly(True)
        self.folder_path_edit.setObjectName("PathDisplayEdit")
        row.addWidget(self.folder_path_edit, 1)
        browse = QPushButton(t("settings.browse")); browse.clicked.connect(self._browse_folder); row.addWidget(browse)
        folder_layout.addLayout(row); layout.addWidget(folder_group)
        dl_count_group = QWidget(); dl_count_layout = QHBoxLayout(dl_count_group); dl_count_layout.setContentsMargins(0,0,0,0)
        parallel_label = QLabel(t("settings.parallel_label"))
        dl_count_layout.addWidget(parallel_label)
        self.concurrent_spinbox = QSpinBox(objectName="StepperSpinBox")
        self.concurrent_spinbox.setRange(1, PARALLEL_MAX)
        self.concurrent_spinbox.setValue(self.config.get("max_concurrent_downloads", 5))
        self.concurrent_spinbox.setMinimumSize(96, 36)
        dl_count_layout.addWidget(self.concurrent_spinbox); dl_count_layout.addStretch(1); layout.addWidget(dl_count_group)

        frag_group = QWidget(); frag_layout = QHBoxLayout(frag_group); frag_layout.setContentsMargins(0, 0, 0, 0)
        fragments_label = QLabel(t("settings.fragments_label"))
        frag_layout.addWidget(fragments_label)
        self.fragments_spinbox = QSpinBox(objectName="StepperSpinBox")
        self.fragments_spinbox.setRange(FRAGMENTS_MIN, FRAGMENTS_MAX)
        self.fragments_spinbox.setValue(canonicalize_config_fragments(self.config))
        self.fragments_spinbox.setMinimumSize(96, 36)
        self.fragments_spinbox.setToolTip(t("settings.fragments_tooltip"))
        frag_layout.addWidget(self.fragments_spinbox); frag_layout.addStretch(1); layout.addWidget(frag_group)
        self._align_labels(parallel_label, fragments_label)

        close_group = QWidget(); close_layout = QVBoxLayout(close_group); close_layout.setContentsMargins(0, 0, 0, 0)
        close_layout.addWidget(QLabel(t("settings.close_label")))
        self.close_action_group = QButtonGroup(self)
        close_radio_layout = QVBoxLayout(); close_radio_layout.setSpacing(10)
        close_actions = (("tray", "settings.close_tray"), ("exit", "settings.close_exit"))
        current_close = self.config.get("close_action", "exit")
        for key, label_key in close_actions:
            radio = QRadioButton(t(label_key)); radio.setProperty("config_value", key)
            self.close_action_group.addButton(radio); close_radio_layout.addWidget(radio)
            if key == current_close: radio.setChecked(True)
        close_layout.addLayout(close_radio_layout); layout.addWidget(close_group)

        clip_group = QWidget(); clip_layout = QVBoxLayout(clip_group); clip_layout.setContentsMargins(0, 0, 0, 0)
        clip_layout.setSpacing(10)
        clip_layout.addWidget(QLabel(t("settings.clipboard_label")))
        self.clipboard_watch_checkbox = QCheckBox(t("settings.clipboard_check"))
        self.clipboard_watch_checkbox.setChecked(self.config.get("clipboard_watch", True))
        self.clipboard_watch_checkbox.setToolTip(t("settings.clipboard_tooltip"))
        clip_layout.addWidget(self.clipboard_watch_checkbox); layout.addWidget(clip_group)

        fav_group = QWidget(); fav_layout = QVBoxLayout(fav_group); fav_layout.setContentsMargins(0, 0, 0, 0)
        fav_layout.setSpacing(10)
        fav_layout.addWidget(QLabel(t("settings.favorites_label")))
        self.fav_autocheck_checkbox = QCheckBox(t("settings.fav_autocheck_check"))
        self.fav_autocheck_checkbox.setChecked(self.config.get("auto_check_favorites_on_start", False))
        self.fav_autocheck_checkbox.setToolTip(t("settings.fav_autocheck_tooltip"))
        fav_layout.addWidget(self.fav_autocheck_checkbox); layout.addWidget(fav_group)

        update_group = QWidget(); update_layout = QVBoxLayout(update_group)
        update_layout.setContentsMargins(0, 0, 0, 0); update_layout.setSpacing(10)
        update_layout.addWidget(QLabel(t("settings.update_label")))
        self.auto_update_checkbox = QCheckBox(t("settings.auto_update_check"))
        self.auto_update_checkbox.setChecked(self.config.get("auto_update_check", True))
        self.auto_update_checkbox.setToolTip(t("settings.auto_update_tooltip"))
        update_layout.addWidget(self.auto_update_checkbox); layout.addWidget(update_group)

        layout.addStretch(1); self._add_page(tab, t("settings.nav_general"), "settings")
        self._general_page_row = self.nav.count() - 1

    SHORTCUT_EDIT_WIDTH = 190
    """조합 입력칸 폭. 'Ctrl+Shift+F12'까지 잘리지 않는다."""

    def _create_shortcuts_tab(self):
        """동작마다 조합 입력칸을 하나씩 놓는다.

        QKeySequenceEdit는 눌린 키를 그대로 받아 적는다. 글자로 적게 하면 'Ctrl + L'인지
        'Control+l'인지부터 헷갈린다. 빈 칸 안내 문구는 Qt 번역에서 온다 - 직접 바꿔 봐야
        QKeySequenceEdit가 상태를 되돌릴 때마다 덮인다.
        """
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setSpacing(12)
        guide = QLabel(t("settings.shortcut_guide"))
        guide.setWordWrap(True)
        layout.addWidget(guide)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12); grid.setVerticalSpacing(4)
        grid.setColumnStretch(0, 1)
        self.shortcut_edits: dict[str, QKeySequenceEdit] = {}
        current = shortcuts.resolve(self.config)
        for index, definition in enumerate(shortcuts.SHORTCUT_DEFS):
            row = index * 2
            editor = QKeySequenceEdit(QKeySequence(current[definition.key]))
            editor.setMaximumSequenceLength(1)
            editor.setClearButtonEnabled(True)
            editor.setFixedWidth(self.SHORTCUT_EDIT_WIDTH)
            editor.setToolTip(definition.hint())
            editor.keySequenceChanged.connect(self._sync_shortcut_warning)
            hint = QLabel(definition.hint(), objectName="PaneSubtitle")
            hint.setWordWrap(True)
            grid.addWidget(QLabel(definition.label()), row, 0)
            grid.addWidget(editor, row, 1)
            grid.addWidget(hint, row + 1, 0, 1, 2)
            self.shortcut_edits[definition.key] = editor
        layout.addLayout(grid)

        self.shortcut_warning = QLabel(objectName="ShortcutWarning")
        self.shortcut_warning.setWordWrap(True)
        layout.addWidget(self.shortcut_warning)

        note = QLabel(t("settings.shortcut_note"), objectName="PaneSubtitle")
        note.setWordWrap(True)
        layout.addWidget(note)

        button_row = QHBoxLayout()
        self.shortcut_reset_button = QPushButton(t("settings.shortcut_reset"))
        self.shortcut_reset_button.clicked.connect(self._reset_shortcuts)
        button_row.addWidget(self.shortcut_reset_button); button_row.addStretch(1)
        layout.addLayout(button_row)

        layout.addStretch(1)
        self._sync_shortcut_warning()
        self._add_page(tab, t("settings.nav_shortcuts"), "nav_shortcut")
        self._shortcut_page_row = self.nav.count() - 1

    def _shortcut_table(self) -> dict[str, str]:
        """입력칸에 적힌 조합을 저장 표기로 모은다."""
        return {key: shortcuts.normalize(editor.keySequence().toString())
                for key, editor in self.shortcut_edits.items()}

    def _sync_shortcut_warning(self):
        """겹치는 조합이 있으면 고치는 자리에서 바로 알린다. 저장할 때만 알리면 되짚어야 한다."""
        clashes = shortcuts.conflicts(self._shortcut_table())
        if not clashes:
            self.shortcut_warning.setText("")
            return
        lines = [t("settings.shortcut_conflict_header")]
        for text, keys in clashes:
            labels = " · ".join(shortcuts.DEF_BY_KEY[key].label() for key in keys)
            lines.append(f"{shortcuts.display(text)} → {labels}")
        self.shortcut_warning.setText("\n".join(lines))

    def _reset_shortcuts(self):
        for key, editor in self.shortcut_edits.items():
            editor.setKeySequence(QKeySequence(shortcuts.DEF_BY_KEY[key].default))
        self._sync_shortcut_warning()

    def _create_filename_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setSpacing(8)
        layout.addWidget(QLabel(t("settings.filename_guide")))

        self.order_list = QListWidget(objectName="FilenameOrderList")
        self.order_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.order_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.order_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.order_list.setDropIndicatorShown(True)
        self.order_list.setDragDropOverwriteMode(False)
        self.order_list.setItemDelegate(PartColorDelegate(self._theme, self.order_list))
        fm = self.order_list.fontMetrics(); row_h = max(28, fm.height() + 12)

        self.part_names: dict[str, str] = {
            key: t(f"settings.part_{key}")
            for key in ("series", "upload_date", "episode_number", "episode", "id")
        }
        parts_cfg: dict = self.config.get("filename_parts", {})
        current_order = self.config.get("filename_order", list(self.part_names.keys()))
        for key in current_order:
            if key not in self.part_names: continue
            item = QListWidgetItem(self.part_names[key]); item.setData(ROLE_KEY, key)
            item.setFlags(
                (item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled)
                & ~Qt.ItemFlag.ItemIsDropEnabled
            )
            item.setCheckState(Qt.CheckState.Checked if parts_cfg.get(key, True) else Qt.CheckState.Unchecked)
            item.setSizeHint(QSize(0, row_h)); self.order_list.addItem(item)

        self.order_list.setFixedHeight(
            self.order_list.count() * row_h + self.order_list.frameWidth() * 2 + 4
        )
        layout.addWidget(self.order_list)

        pv = QVBoxLayout(); pv.setSpacing(4)
        pv.addWidget(QLabel(t("settings.filename_preview_label")))
        self.preview_label = QLabel(objectName="FilenamePreview")
        self.preview_label.setWordWrap(True)
        self.preview_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        pv.addWidget(self.preview_label)
        layout.addLayout(pv)
        layout.addStretch(1)

        self.order_list.itemChanged.connect(self._update_preview)
        self.order_list.model().rowsMoved.connect(self._update_preview)
        self.order_list.model().rowsInserted.connect(self._update_preview)
        self._update_preview()
        self._add_page(tab, t("settings.nav_filename"), "nav_filename")

    def _update_preview(self, *args):
        """고른 조각을 차례대로 이어 미리보기를 다시 적는다.

        서식 있는 글이라 조각마다 위 목록과 같은 색을 입힐 수 있다. 그 대신 본보기 값을
        반드시 이스케이프해야 한다 - 꺾은괄호가 든 제목이 오면 그 대목이 통째로 사라진다.
        """
        spans = []
        for i in range(self.order_list.count()):
            item = self.order_list.item(i)
            if item.checkState() != Qt.CheckState.Checked:
                continue
            key = item.data(ROLE_KEY)
            sample = html.escape(PREVIEW_SAMPLES.get(key, item.text()))
            spans.append(
                f'<span style="color:{part_color(self._theme, key, True)};">{sample}</span>'
            )
        if not spans:
            dim = palette(self._theme)["text_dim"]
            empty = html.escape(t("settings.filename_preview_empty"))
            spans = [f'<span style="color:{dim};">{empty}</span>']
        self.preview_label.setText(" ".join(spans))

    def _create_quality_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setSpacing(15)

        q_groupbox = QWidget(); q_layout = QVBoxLayout(q_groupbox); q_layout.setContentsMargins(0,0,0,0)
        q_layout.addWidget(QLabel(t("settings.quality_label")))
        q_radio_layout = QVBoxLayout(); q_radio_layout.setSpacing(10); self.quality_button_group = QButtonGroup(self)
        qualities = (
            ("bv*+ba/b", "settings.quality_best"),
            ("bestvideo[height<=1080]+bestaudio/best[height<=1080]", "settings.quality_1080p"),
            ("bestvideo[height<=720]+bestaudio/best[height<=720]", "settings.quality_720p"),
        )
        current_quality = self.config.get("quality", "bv*+ba/b")
        for key, label_key in qualities:
            radio = QRadioButton(t(label_key)); radio.setProperty("config_value", key); self.quality_button_group.addButton(radio); q_radio_layout.addWidget(radio)
            if key == current_quality: radio.setChecked(True)
        q_layout.addLayout(q_radio_layout); layout.addWidget(q_groupbox)

        c_groupbox = QWidget(); c_layout = QVBoxLayout(c_groupbox); c_layout.setContentsMargins(0,0,0,0)
        c_layout.addWidget(QLabel(t("settings.codec_label")))
        self.codec_combo = QComboBox()
        self.codec_map = {
            t("settings.codec_original"): "original",
            t("settings.codec_avc"): "avc",
            t("settings.codec_hevc"): "hevc",
        }
        self.codec_combo.setToolTip(t("settings.codec_tooltip"))
        current_codec = canonicalize_config_codec(self.config)
        for text, key in self.codec_map.items():
            self.codec_combo.addItem(text, userData=key)
            if key == current_codec:
                self.codec_combo.setCurrentText(text)
        fit_combo_width(self.codec_combo)
        c_layout.addWidget(self.codec_combo)
        layout.addWidget(c_groupbox)

        hw_groupbox = QWidget()
        hw_v_layout = QVBoxLayout(hw_groupbox)
        hw_v_layout.setContentsMargins(0,0,0,0)
        hw_v_layout.addWidget(QLabel(t("settings.encoder_label")))
        self.hw_encoder_combo = QComboBox()
        self.hw_encoder_map = {
            t("settings.encoder_cpu"): "cpu",
            t("settings.encoder_nvidia"): "nvidia",
        }
        self.hw_encoder_combo.setToolTip(t("settings.encoder_tooltip"))
        current_hw = canonicalize_config_encoder(self.config)
        for text, key in self.hw_encoder_map.items():
            self.hw_encoder_combo.addItem(text, userData=key)
            if key == current_hw:
                self.hw_encoder_combo.setCurrentText(text)
        fit_combo_width(self.hw_encoder_combo)
        hw_v_layout.addWidget(self.hw_encoder_combo)
        layout.addWidget(hw_groupbox)
        self._hw_group = hw_groupbox

        self.codec_combo.currentIndexChanged.connect(self._sync_codec_dependent_state)
        self._sync_codec_dependent_state()
        layout.addStretch(1); self._add_page(tab, t("settings.nav_quality"), "nav_quality")

    def _create_subtitle_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setSpacing(15)

        self.download_subs_checkbox = QCheckBox(t("settings.subs_download"))
        self.download_subs_checkbox.setChecked(self.config.get("download_subtitles", True))
        layout.addWidget(self.download_subs_checkbox)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        self.embed_subs_checkbox = QCheckBox(t("settings.subs_embed"))
        self.embed_subs_checkbox.setChecked(self.config.get("embed_subtitles", False))
        layout.addWidget(self.embed_subs_checkbox)

        self.sub_fmt_groupbox = QGroupBox(t("settings.subs_format_group"))
        sub_fmt_layout = QVBoxLayout(self.sub_fmt_groupbox)
        sub_fmt_layout.setSpacing(10)

        self.subtitle_format_button_group = QButtonGroup(self)
        self.sub_format_vtt = QRadioButton(t("settings.subs_vtt"))
        self.sub_format_vtt.setProperty("config_value", "vtt")
        self.sub_format_srt = QRadioButton(t("settings.subs_srt"))
        self.sub_format_srt.setProperty("config_value", "srt")

        self.subtitle_format_button_group.addButton(self.sub_format_vtt)
        self.subtitle_format_button_group.addButton(self.sub_format_srt)

        sub_fmt_layout.addWidget(self.sub_format_vtt)
        sub_fmt_layout.addWidget(self.sub_format_srt)

        current_sub_format = self.config.get("subtitle_format", "vtt")
        if current_sub_format == "srt":
            self.sub_format_srt.setChecked(True)
        else:
            self.sub_format_vtt.setChecked(True)

        layout.addWidget(self.sub_fmt_groupbox)

        def update_ui_state():
            is_download_enabled = self.download_subs_checkbox.isChecked()
            is_embed_enabled = self.embed_subs_checkbox.isChecked()
            self.embed_subs_checkbox.setEnabled(is_download_enabled)
            self.sub_fmt_groupbox.setEnabled(is_download_enabled and not is_embed_enabled)

        self.download_subs_checkbox.toggled.connect(update_ui_state)
        self.embed_subs_checkbox.toggled.connect(update_ui_state)
        update_ui_state()
        layout.addStretch(1)
        self._add_page(tab, t("settings.nav_subtitle"), "nav_subtitle")

    def _create_advanced_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setSpacing(20)

        exclude_groupbox = QWidget()
        exclude_v_layout = QVBoxLayout(exclude_groupbox)
        exclude_v_layout.setContentsMargins(0,0,0,0)
        exclude_v_layout.addWidget(QLabel(t("settings.exclude_label")))
        current_keywords = self.config.get("series_exclude_keywords", [])
        self.exclude_keywords_edit = QLineEdit(", ".join(current_keywords))
        self.exclude_keywords_edit.setPlaceholderText(t("settings.exclude_placeholder"))
        exclude_v_layout.addWidget(self.exclude_keywords_edit)
        layout.addWidget(exclude_groupbox)

        self.embed_thumbnail_checkbox = QCheckBox(t("settings.embed_thumb_check"))
        self.embed_thumbnail_checkbox.setChecked(self.config.get("embed_thumbnail", False))
        self.embed_thumbnail_checkbox.setToolTip(t("settings.embed_thumb_tooltip"))
        layout.addWidget(self.embed_thumbnail_checkbox)

        self.ignore_ssl_checkbox = QCheckBox(t("settings.ignore_ssl_check"))
        self.ignore_ssl_checkbox.setChecked(self.config.get("ignore_ssl_errors", False))
        self.ignore_ssl_checkbox.setToolTip(t("settings.ignore_ssl_tooltip"))
        layout.addWidget(self.ignore_ssl_checkbox)

        layout.addStretch(1); self._add_page(tab, t("settings.nav_advanced"), "nav_advanced")

    def _create_cache_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setSpacing(15)
        info_layout = QHBoxLayout()
        info_layout.addWidget(QLabel(t("settings.cache_size_label")))
        self.cache_size_label = QLabel(t("settings.cache_calculating")); self.cache_size_label.setObjectName("PaneSubtitle")
        info_layout.addWidget(self.cache_size_label); info_layout.addStretch(1)
        layout.addLayout(info_layout)
        self.clear_cache_button = QPushButton(t("settings.cache_clear_button")); self.clear_cache_button.setObjectName("DangerButton")
        self.clear_cache_button.clicked.connect(self._clear_thumbnail_cache)
        layout.addWidget(self.clear_cache_button)
        layout.addStretch(1); self._add_page(tab, t("settings.nav_cache"), "nav_cache")

    def _sync_codec_dependent_state(self):
        """'원본 유지'면 재인코딩 관련 설정을 흐리게 한다.

        숨기지는 않는다 - 사라지면 그런 설정이 있었는지조차 모르게 된다.
        """
        self._hw_group.setEnabled(self.codec_combo.currentData() != "original")

    @staticmethod
    def _align_labels(*labels: QLabel):
        """나란히 놓인 설명들의 폭을 맞춰 뒤의 입력칸이 한 줄로 서게 한다.

        성격이 같은 값(동시 다운로드 수 · 조각 수)이라 함께 읽는다. 폭은 sizeHint에서
        가져온다 - 숫자로 박아 두면 서체와 배율에 따라 어느 환경에서는 글이 잘린다.
        """
        widest = max(label.sizeHint().width() for label in labels)
        for label in labels:
            label.setMinimumWidth(widest)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, t("settings.folder_dialog_title"),
                                                  self.folder_path_edit.text())
        if folder: self.folder_path_edit.setText(folder)

    def _check_connection_total(self) -> bool:
        """동시 다운로드 수와 조각 수의 곱이 상한 안에 있는지 본다. 넘으면 알리고 막는다.

        저장할 때 막는 것은 단축키 충돌과 같은 이유다 - 넘긴 채로 저장되면 다음 다운로드에서야
        실패하고, 그때는 무엇 때문인지 짚기 어렵다. 고쳐서 바로 다시 누를 수 있게 일반 탭으로
        돌려놓는다.
        """
        parallel = self.concurrent_spinbox.value()
        fragments = self.fragments_spinbox.value()
        total = parallel * fragments
        if total <= MAX_TOTAL_CONNECTIONS:
            return True
        self.nav.setCurrentRow(self._general_page_row)
        notify(
            self, t("settings.connection_title"),
            t("settings.connection_body", parallel=parallel, fragments=fragments,
              total=total, maximum=MAX_TOTAL_CONNECTIONS),
            icon_name="info", color_key="warn", theme=self._theme,
        )
        return False

    def _save_settings(self):
        """설정을 파일에 쓰고 창을 닫는다.

        **바뀐 값을 self.config에 곧바로 적지 않는다.** 그 사전은 메인 창과 같은 것을
        가리켜서, 파일 저장이 실패한 뒤 사용자가 창을 닫으면 **파일과 다른 값이 실행 중인
        앱에만 남는다.** 다 모아 두었다가 성공한 뒤 한 번에 옮긴다.

        저장에는 `merged`를 넘긴다 - pending만 쓰면 창이 다루지 않는 설정(창 크기·테마
        같은 것)이 통째로 사라진다.
        """
        shortcut_table = self._shortcut_table()
        if shortcuts.conflicts(shortcut_table):
            self.nav.setCurrentRow(self._shortcut_page_row)
            self._sync_shortcut_warning()
            notify(self, t("settings.shortcut_conflict_title"),
                   t("settings.shortcut_conflict_body"),
                   icon_name="nav_shortcut", color_key="warn", theme=self._theme)
            return
        if not self._check_connection_total():
            return
        language = self.language_combo.currentData()
        pending: dict = {}
        pending["language"] = language
        pending[shortcuts.CONFIG_KEY] = shortcut_table
        pending["download_folder"] = self.folder_path_edit.text()
        pending["max_concurrent_downloads"] = self.concurrent_spinbox.value()
        pending["concurrent_fragments"] = self.fragments_spinbox.value()
        if self.close_action_group.checkedButton():
            pending["close_action"] = self.close_action_group.checkedButton().property("config_value")
        pending["clipboard_watch"] = self.clipboard_watch_checkbox.isChecked()
        pending["auto_check_favorites_on_start"] = self.fav_autocheck_checkbox.isChecked()
        pending["auto_update_check"] = self.auto_update_checkbox.isChecked()
        filename_parts: dict[str, bool] = {}; filename_order: list[str] = []
        for i in range(self.order_list.count()):
            it = self.order_list.item(i); key = it.data(ROLE_KEY)
            filename_order.append(key); filename_parts[key] = (it.checkState() == Qt.CheckState.Checked)
        pending["filename_parts"] = filename_parts; pending["filename_order"] = filename_order

        if self.quality_button_group.checkedButton(): pending["quality"] = self.quality_button_group.checkedButton().property("config_value")
        pending["preferred_codec"] = self.codec_combo.currentData()
        pending["hardware_encoder"] = self.hw_encoder_combo.currentData()

        pending["download_subtitles"] = self.download_subs_checkbox.isChecked()
        pending["embed_subtitles"] = self.embed_subs_checkbox.isChecked()
        if self.subtitle_format_button_group.checkedButton():
            pending["subtitle_format"] = self.subtitle_format_button_group.checkedButton().property("config_value")

        pending["embed_thumbnail"] = self.embed_thumbnail_checkbox.isChecked()
        pending["ignore_ssl_errors"] = self.ignore_ssl_checkbox.isChecked()
        keywords_str = self.exclude_keywords_edit.text()
        pending["series_exclude_keywords"] = [k.strip() for k in keywords_str.split(',') if k.strip()]

        merged = dict(self.config)
        merged.update(pending)
        if not save_config(merged):
            notify(self, t("settings.save_failed_title"),
                   t("settings.save_failed_body"),
                   icon_name="info", color_key="warn", theme=self._theme)
            return
        self.config.update(pending)
        self.language_changed = i18n.resolve_code(language) != i18n.current_code()
        self.accept()
