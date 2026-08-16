from __future__ import annotations
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSpinBox, QStackedWidget, QWidget, QFileDialog, QDialogButtonBox,
    QListWidget, QListWidgetItem, QAbstractItemView,
    QRadioButton, QButtonGroup, QCheckBox, QMessageBox, QFrame, QComboBox,
    QFormLayout, QGroupBox, QGridLayout, QKeySequenceEdit
)
from src import shortcuts
from src.icons import get_icon
from src.message import confirm
from src.qss import palette
from src.utils import save_config, PARALLEL_MAX
from src.widgets import THUMBNAIL_CACHE_DIR

ROLE_KEY = Qt.ItemDataRole.UserRole

PREVIEW_SAMPLES = {
    "series": "アメトーーク！",
    "upload_date": "20260807",
    "episode_number": "1005",
    "episode": "【粗品参戦】ダチョウ倶楽部を考えよう2026…有吉＆劇団＆出川",
    "id": "[epi6hzy79h]",
}

class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self._theme = config.get("theme", "light")
        self.setWindowTitle("설정")
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
        save_btn = self.buttons.addButton("설정 저장", QDialogButtonBox.ButtonRole.AcceptRole)
        save_btn.setObjectName("PrimaryButton")
        exit_btn = self.buttons.addButton("나가기", QDialogButtonBox.ButtonRole.RejectRole)
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
        if not confirm(self, "캐시 삭제", "정말로 모든 썸네일 캐시를 삭제하시겠습니까?",
                       icon_name="nav_cache", color_key="danger", theme=self._theme):
            return
        count = 0
        try:
            for f in THUMBNAIL_CACHE_DIR.glob('**/*'):
                if f.is_file(): f.unlink(); count += 1
            QMessageBox.information(self, "완료", f"썸네일 캐시 {count}개를 삭제했습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"캐시 삭제 중 오류 발생:\n{e}")
        finally:
            self._update_cache_label()

    def _create_general_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setSpacing(15)
        folder_group = QWidget(); folder_layout = QVBoxLayout(folder_group); folder_layout.setContentsMargins(0,0,0,0)
        folder_layout.addWidget(QLabel("다운로드 폴더:"))
        row = QHBoxLayout()
        self.folder_path_edit = QLineEdit(self.config.get("download_folder", "")); self.folder_path_edit.setReadOnly(True)
        self.folder_path_edit.setObjectName("PathDisplayEdit")
        row.addWidget(self.folder_path_edit, 1)
        browse = QPushButton("찾아보기..."); browse.clicked.connect(self._browse_folder); row.addWidget(browse)
        folder_layout.addLayout(row); layout.addWidget(folder_group)
        dl_count_group = QWidget(); dl_count_layout = QHBoxLayout(dl_count_group); dl_count_layout.setContentsMargins(0,0,0,0)
        dl_count_layout.addWidget(QLabel("최대 동시 다운로드 개수:"))
        self.concurrent_spinbox = QSpinBox(objectName="StepperSpinBox")
        self.concurrent_spinbox.setRange(1, PARALLEL_MAX)
        self.concurrent_spinbox.setValue(self.config.get("max_concurrent_downloads", 5))
        self.concurrent_spinbox.setMinimumSize(96, 36)
        dl_count_layout.addWidget(self.concurrent_spinbox); dl_count_layout.addStretch(1); layout.addWidget(dl_count_group)

        close_group = QWidget(); close_layout = QVBoxLayout(close_group); close_layout.setContentsMargins(0, 0, 0, 0)
        close_layout.addWidget(QLabel("닫기 버튼(X)을 눌렀을 때:"))
        self.close_action_group = QButtonGroup(self)
        close_radio_layout = QVBoxLayout(); close_radio_layout.setSpacing(10)
        close_actions = {"트레이로 이동": "tray", "프로그램 종료": "exit"}
        current_close = self.config.get("close_action", "exit")
        for text, key in close_actions.items():
            radio = QRadioButton(text); radio.setProperty("config_value", key)
            self.close_action_group.addButton(radio); close_radio_layout.addWidget(radio)
            if key == current_close: radio.setChecked(True)
        close_layout.addLayout(close_radio_layout); layout.addWidget(close_group)

        clip_group = QWidget(); clip_layout = QVBoxLayout(clip_group); clip_layout.setContentsMargins(0, 0, 0, 0)
        clip_layout.setSpacing(10)
        clip_layout.addWidget(QLabel("클립보드:"))
        self.clipboard_watch_checkbox = QCheckBox("TVer 주소를 복사하면 입력창에 자동으로 넣기")
        self.clipboard_watch_checkbox.setChecked(self.config.get("clipboard_watch", False))
        self.clipboard_watch_checkbox.setToolTip(
            "TVer 주소를 복사하면 위쪽 입력창에 자동으로 채워 넣습니다.\n"
            "다운로드가 저절로 시작되지는 않고, 입력창에 이미 내용이 있으면 건드리지 않습니다.\n"
            "TVer 주소가 아닌 클립보드 내용은 어디로도 보내지 않습니다.\n"
            "꺼 두면 클립보드를 아예 감시하지 않습니다."
        )
        clip_layout.addWidget(self.clipboard_watch_checkbox); layout.addWidget(clip_group)

        fav_group = QWidget(); fav_layout = QVBoxLayout(fav_group); fav_layout.setContentsMargins(0, 0, 0, 0)
        fav_layout.setSpacing(10)
        fav_layout.addWidget(QLabel("즐겨찾기:"))
        self.fav_autocheck_checkbox = QCheckBox("프로그램을 켤 때 새 회차를 확인하기")
        self.fav_autocheck_checkbox.setChecked(self.config.get("auto_check_favorites_on_start", True))
        self.fav_autocheck_checkbox.setToolTip(
            "프로그램을 켠 뒤 잠시 있다가 즐겨찾기에 담긴 시리즈를 모두 확인합니다.\n"
            "TVer는 일본 지역 제한이 있어, VPN을 켜기 전에 확인이 돌면 전부 실패로 끝납니다.\n"
            "윈도우 시작과 함께 켜지도록 해 두었다면 꺼 두는 편이 낫습니다.\n"
            "꺼도 즐겨찾기 탭의 '갱신'으로 언제든 직접 확인할 수 있습니다."
        )
        fav_layout.addWidget(self.fav_autocheck_checkbox); layout.addWidget(fav_group)

        update_group = QWidget(); update_layout = QVBoxLayout(update_group)
        update_layout.setContentsMargins(0, 0, 0, 0); update_layout.setSpacing(10)
        update_layout.addWidget(QLabel("업데이트:"))
        self.auto_update_checkbox = QCheckBox("프로그램을 켤 때 새 버전 확인하기")
        self.auto_update_checkbox.setChecked(self.config.get("auto_update_check", True))
        self.auto_update_checkbox.setToolTip(
            "프로그램을 켠 뒤 새 버전이 나왔는지 확인하고, 있으면 알려 줍니다.\n"
            "받을지 말지는 그때 고르면 되고, 저절로 받아지지는 않습니다.\n"
            "'지금 업데이트'를 누르면 새 버전을 받아 그 자리에서 갈아 끼웁니다.\n"
            "이때 설정·기록·즐겨찾기와 bin 폴더는 그대로 둡니다.\n"
            "꺼 두면 확인 자체를 하지 않습니다."
        )
        update_layout.addWidget(self.auto_update_checkbox); layout.addWidget(update_group)

        layout.addStretch(1); self._add_page(tab, "일반", "settings")

    SHORTCUT_EDIT_WIDTH = 190
    """조합 입력칸 폭. 'Ctrl+Shift+F12'까지 잘리지 않는다."""

    def _create_shortcuts_tab(self):
        """동작마다 조합 입력칸을 하나씩 놓는다.

        QKeySequenceEdit는 눌린 키를 그대로 받아 적는다. 조합을 글자로 적게 하면
        'Ctrl + L'인지 'Control+l'인지부터 헷갈리고, 그 키가 실제로 눌리는 키인지
        확인할 방법도 없다.

        빈 칸 안내 문구는 Qt가 자기 번역에서 넣는다(setup_translations). 직접
        바꿔 봐야 QKeySequenceEdit가 상태를 되돌릴 때마다 원래 문구로 덮인다.
        """
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setSpacing(12)
        guide = QLabel("입력칸을 누른 뒤 원하는 키를 누르면 바뀝니다. "
                       "칸을 비우면 그 단축키는 사용하지 않습니다.")
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
            editor.setToolTip(definition.hint)
            editor.keySequenceChanged.connect(self._sync_shortcut_warning)
            hint = QLabel(definition.hint, objectName="PaneSubtitle")
            hint.setWordWrap(True)
            grid.addWidget(QLabel(definition.label), row, 0)
            grid.addWidget(editor, row, 1)
            grid.addWidget(hint, row + 1, 0, 1, 2)
            self.shortcut_edits[definition.key] = editor
        layout.addLayout(grid)

        self.shortcut_warning = QLabel(objectName="ShortcutWarning")
        self.shortcut_warning.setWordWrap(True)
        layout.addWidget(self.shortcut_warning)

        note = QLabel("Ctrl·Alt 없이 쓰는 조합은 글자를 입력하는 동안에는 동작하지 않습니다.",
                      objectName="PaneSubtitle")
        note.setWordWrap(True)
        layout.addWidget(note)

        button_row = QHBoxLayout()
        self.shortcut_reset_button = QPushButton("기본값으로 되돌리기")
        self.shortcut_reset_button.clicked.connect(self._reset_shortcuts)
        button_row.addWidget(self.shortcut_reset_button); button_row.addStretch(1)
        layout.addLayout(button_row)

        layout.addStretch(1)
        self._sync_shortcut_warning()
        self._add_page(tab, "단축키", "nav_shortcut")
        self._shortcut_page_row = self.nav.count() - 1

    def _shortcut_table(self) -> dict[str, str]:
        """입력칸에 적힌 조합을 저장 표기로 모은다."""
        return {key: shortcuts.normalize(editor.keySequence().toString())
                for key, editor in self.shortcut_edits.items()}

    def _sync_shortcut_warning(self):
        """겹치는 조합이 있으면 고치는 자리에서 바로 알린다.

        저장할 때만 알리면 어느 칸이 문제인지 되짚어야 한다.
        """
        clashes = shortcuts.conflicts(self._shortcut_table())
        if not clashes:
            self.shortcut_warning.setText("")
            return
        lines = ["같은 조합을 나눠 쓰고 있습니다. 이대로면 눌러도 어느 쪽도 동작하지 않습니다."]
        for text, keys in clashes:
            labels = " · ".join(shortcuts.DEF_BY_KEY[key].label for key in keys)
            lines.append(f"{shortcuts.display(text)} → {labels}")
        self.shortcut_warning.setText("\n".join(lines))

    def _reset_shortcuts(self):
        for key, editor in self.shortcut_edits.items():
            editor.setKeySequence(QKeySequence(shortcuts.DEF_BY_KEY[key].default))
        self._sync_shortcut_warning()

    def _create_filename_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setSpacing(8)
        layout.addWidget(QLabel("파일명 구성 요소 선택 및 순서 설정 (항목을 끌어서 순서 변경):"))

        self.order_list = QListWidget()
        self.order_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.order_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.order_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.order_list.setDropIndicatorShown(True)
        self.order_list.setDragDropOverwriteMode(False)
        self.order_list.setStyleSheet("QListWidget::item{ padding:6px 8px; }")
        fm = self.order_list.fontMetrics(); row_h = max(28, fm.height() + 12)

        self.part_names: dict[str, str] = {"series": "시리즈명", "upload_date": "방송날짜", "episode_number": "회차번호", "episode": "타이틀", "id": "고유ID"}
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
        pv.addWidget(QLabel("파일명 미리보기:"))
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
        self._add_page(tab, "파일명", "nav_filename")

    def _update_preview(self, *args):
        parts = []
        for i in range(self.order_list.count()):
            item = self.order_list.item(i)
            if item.checkState() != Qt.CheckState.Checked:
                continue
            key = item.data(ROLE_KEY)
            parts.append(PREVIEW_SAMPLES.get(key, item.text()))
        self.preview_label.setText((" ".join(parts) + ".mp4") if parts else "(선택된 항목이 없습니다)")

    def _create_quality_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setSpacing(15)

        q_groupbox = QWidget(); q_layout = QVBoxLayout(q_groupbox); q_layout.setContentsMargins(0,0,0,0)
        q_layout.addWidget(QLabel("다운로드 화질 선택:"))
        q_radio_layout = QVBoxLayout(); q_radio_layout.setSpacing(10); self.quality_button_group = QButtonGroup(self)
        qualities = {"최상 화질 (기본값)": "bv*+ba/b", "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]", "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]"}
        current_quality = self.config.get("quality", "bv*+ba/b")
        for text, key in qualities.items():
            radio = QRadioButton(text); radio.setProperty("config_value", key); self.quality_button_group.addButton(radio); q_radio_layout.addWidget(radio)
            if key == current_quality: radio.setChecked(True)
        q_layout.addLayout(q_radio_layout); layout.addWidget(q_groupbox)

        c_groupbox = QWidget(); c_layout = QVBoxLayout(c_groupbox); c_layout.setContentsMargins(0,0,0,0)
        c_layout.addWidget(QLabel("선호 코덱 (재인코딩):"))
        self.codec_combo = QComboBox()
        self.codec_map = {
            "원본 유지 (재인코딩 없음, 기본값)": "original",
            "AVC/H.264 (최고 호환성)": "avc",
            "HEVC/H.265 (고효율)": "hevc",
            "VP9 (웹 표준)": "vp9",
            "AV1 (차세대)": "av1",
        }
        current_codec = self.config.get("preferred_codec", "original")
        for text, key in self.codec_map.items():
            self.codec_combo.addItem(text, userData=key)
            if key == current_codec:
                self.codec_combo.setCurrentText(text)
        c_layout.addWidget(self.codec_combo)
        layout.addWidget(c_groupbox)

        hw_groupbox = QWidget()
        hw_v_layout = QVBoxLayout(hw_groupbox)
        hw_v_layout.setContentsMargins(0,0,0,0)
        hw_v_layout.addWidget(QLabel("코덱 변환 가속 (GPU 인코딩):"))
        self.hw_encoder_combo = QComboBox()
        self.hw_encoder_map = {
            "CPU (기본값, 호환성)": "cpu",
            "NVIDIA (NVENC)": "nvidia",
            "Intel (QSV)": "intel",
            "AMD (AMF)": "amd"
        }
        current_hw = self.config.get("hardware_encoder", "cpu")
        for text, key in self.hw_encoder_map.items():
            self.hw_encoder_combo.addItem(text, userData=key)
            if key == current_hw:
                self.hw_encoder_combo.setCurrentText(text)
        hw_v_layout.addWidget(self.hw_encoder_combo)
        layout.addWidget(hw_groupbox)
        self._hw_group = hw_groupbox

        quality_group = QWidget()
        quality_layout = QFormLayout(quality_group)
        quality_layout.setContentsMargins(0, 5, 0, 5)
        quality_layout.setSpacing(10)
        quality_layout.addRow(QLabel("상세 품질 설정 (숫자가 낮을수록 고품질)"))

        self.q_cpu_h264_crf = QSpinBox()
        self.q_cpu_h264_crf.setRange(0, 51)
        self.q_cpu_h264_crf.setValue(self.config.get("quality_cpu_h264_crf", 26))
        quality_layout.addRow("CPU H.264 CRF (권장: 26):", self.q_cpu_h264_crf)

        self.q_cpu_h265_crf = QSpinBox()
        self.q_cpu_h265_crf.setRange(0, 51)
        self.q_cpu_h265_crf.setValue(self.config.get("quality_cpu_h265_crf", 31))
        quality_layout.addRow("CPU H.265 CRF (권장: 31):", self.q_cpu_h265_crf)

        self.q_cpu_vp9_crf = QSpinBox()
        self.q_cpu_vp9_crf.setRange(0, 63)
        self.q_cpu_vp9_crf.setValue(self.config.get("quality_cpu_vp9_crf", 36))
        quality_layout.addRow("CPU VP9 CRF (권장: 36):", self.q_cpu_vp9_crf)

        self.q_cpu_av1_crf = QSpinBox()
        self.q_cpu_av1_crf.setRange(0, 63)
        self.q_cpu_av1_crf.setValue(self.config.get("quality_cpu_av1_crf", 41))
        quality_layout.addRow("CPU AV1 CRF (권장: 41):", self.q_cpu_av1_crf)

        self.q_gpu_cq = QSpinBox()
        self.q_gpu_cq.setRange(0, 51)
        self.q_gpu_cq.setValue(self.config.get("quality_gpu_cq", 30))
        quality_layout.addRow("GPU CQ/CQP (권장: 30):", self.q_gpu_cq)

        layout.addWidget(quality_group)
        self._crf_group = quality_group
        self.codec_combo.currentIndexChanged.connect(self._sync_codec_dependent_state)
        self._sync_codec_dependent_state()
        layout.addStretch(1); self._add_page(tab, "화질", "nav_quality")

    def _create_subtitle_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setSpacing(15)

        self.download_subs_checkbox = QCheckBox("자막 다운로드 활성화")
        self.download_subs_checkbox.setChecked(self.config.get("download_subtitles", True))
        layout.addWidget(self.download_subs_checkbox)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        self.embed_subs_checkbox = QCheckBox("자막을 동영상 파일에 병합 (Embed)")
        self.embed_subs_checkbox.setChecked(self.config.get("embed_subtitles", False))
        layout.addWidget(self.embed_subs_checkbox)

        self.sub_fmt_groupbox = QGroupBox("별도 파일 저장 시 포맷")
        sub_fmt_layout = QVBoxLayout(self.sub_fmt_groupbox)
        sub_fmt_layout.setSpacing(10)

        self.subtitle_format_button_group = QButtonGroup(self)
        self.sub_format_vtt = QRadioButton("VTT (원본)")
        self.sub_format_vtt.setProperty("config_value", "vtt")
        self.sub_format_srt = QRadioButton("SRT (변환, 호환성 좋음)")
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
        self._add_page(tab, "자막", "nav_subtitle")

    def _create_advanced_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setSpacing(20)

        conv_groupbox = QWidget(); conv_v_layout = QVBoxLayout(conv_groupbox); conv_v_layout.setContentsMargins(0,0,0,0)
        conv_v_layout.addWidget(QLabel("다운로드 후 변환 (컨테이너):"))
        self.conversion_button_group = QButtonGroup(self); conv_radio_layout = QVBoxLayout(); conv_radio_layout.setSpacing(10)
        formats = {"변환 안 함 (MP4)": "none", "AVI로 변환": "avi", "MOV로 변환": "mov", "오디오만 추출 (MP3)": "mp3"}
        current_format = self.config.get("conversion_format", "none")
        for text, key in formats.items():
            radio = QRadioButton(text); radio.setProperty("config_value", key); self.conversion_button_group.addButton(radio); conv_radio_layout.addWidget(radio)
            if key == current_format: radio.setChecked(True)
        conv_v_layout.addLayout(conv_radio_layout)
        self.delete_original_checkbox = QCheckBox("변환 후 원본 파일 삭제")
        self.delete_original_checkbox.setChecked(self.config.get("delete_on_conversion", False))
        self.conversion_button_group.buttonToggled.connect(self._toggle_delete_checkbox)
        self._toggle_delete_checkbox()
        conv_v_layout.addWidget(self.delete_original_checkbox); layout.addWidget(conv_groupbox)

        exclude_groupbox = QWidget()
        exclude_v_layout = QVBoxLayout(exclude_groupbox)
        exclude_v_layout.setContentsMargins(0,0,0,0)
        exclude_v_layout.addWidget(QLabel("시리즈 분석 시 제외할 키워드 (쉼표,로 구분):"))
        current_keywords = self.config.get("series_exclude_keywords", [])
        self.exclude_keywords_edit = QLineEdit(", ".join(current_keywords))
        self.exclude_keywords_edit.setPlaceholderText("예: 予告, SP, ダイジェスト")
        exclude_v_layout.addWidget(self.exclude_keywords_edit)
        layout.addWidget(exclude_groupbox)

        self.embed_thumbnail_checkbox = QCheckBox("영상 파일에 썸네일 포함 (탐색기·플레이어 미리보기)")
        self.embed_thumbnail_checkbox.setChecked(self.config.get("embed_thumbnail", False))
        self.embed_thumbnail_checkbox.setToolTip(
            "yt-dlp에 --embed-thumbnail 옵션을 전달해 표지 그림을 mp4 안에 넣습니다.\n"
            "앱 목록의 썸네일과 달리 탐색기와 외부 플레이어에서도 미리보기가 보입니다.\n"
            "포함에 실패해도 영상 다운로드 자체는 그대로 완료됩니다."
        )
        layout.addWidget(self.embed_thumbnail_checkbox)

        self.ignore_ssl_checkbox = QCheckBox("SSL 인증서 검증 건너뛰기 (연결 오류 시에만 사용)")
        self.ignore_ssl_checkbox.setChecked(self.config.get("ignore_ssl_errors", False))
        self.ignore_ssl_checkbox.setToolTip(
            "체크하면 yt-dlp에 --no-check-certificate 옵션을 전달합니다.\n"
            "중간자 공격에 노출될 수 있으므로 인증서 오류로 다운로드가 실패할 때만 사용하세요."
        )
        layout.addWidget(self.ignore_ssl_checkbox)

        layout.addStretch(1); self._add_page(tab, "고급", "nav_advanced")

    def _create_cache_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setSpacing(15)
        info_layout = QHBoxLayout()
        info_layout.addWidget(QLabel("현재 썸네일 캐시 크기:"))
        self.cache_size_label = QLabel("계산 중..."); self.cache_size_label.setObjectName("PaneSubtitle")
        info_layout.addWidget(self.cache_size_label); info_layout.addStretch(1)
        layout.addLayout(info_layout)
        self.clear_cache_button = QPushButton("썸네일 캐시 지우기"); self.clear_cache_button.setObjectName("DangerButton")
        self.clear_cache_button.clicked.connect(self._clear_thumbnail_cache)
        layout.addWidget(self.clear_cache_button)
        layout.addStretch(1); self._add_page(tab, "캐시", "nav_cache")

    def _sync_codec_dependent_state(self):
        """'원본 유지'면 재인코딩 관련 설정을 흐리게 한다.

        숨기지는 않는다. 사라지면 그런 설정이 있었는지조차 모르게 되지만,
        흐리게 남아 있으면 '지금은 해당 없음'이 전달된다. (UI_REDESIGN.md 6항)
        """
        reencoding = self.codec_combo.currentData() != "original"
        self._hw_group.setEnabled(reencoding)
        self._crf_group.setEnabled(reencoding)

    def _toggle_delete_checkbox(self):
        selected_button = self.conversion_button_group.checkedButton()
        is_conversion_selected = selected_button is not None and selected_button.property("config_value") != "none"
        self.delete_original_checkbox.setEnabled(is_conversion_selected)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "다운로드 폴더 선택", self.folder_path_edit.text())
        if folder: self.folder_path_edit.setText(folder)

    def _save_settings(self):
        shortcut_table = self._shortcut_table()
        if shortcuts.conflicts(shortcut_table):
            self.nav.setCurrentRow(self._shortcut_page_row)
            self._sync_shortcut_warning()
            QMessageBox.warning(self, "단축키 충돌",
                                "같은 조합을 두 동작이 나눠 쓰고 있습니다.\n"
                                "겹치는 조합을 고친 뒤 다시 저장해 주세요.")
            return
        self.config[shortcuts.CONFIG_KEY] = shortcut_table
        self.config["download_folder"] = self.folder_path_edit.text()
        self.config["max_concurrent_downloads"] = self.concurrent_spinbox.value()
        if self.close_action_group.checkedButton():
            self.config["close_action"] = self.close_action_group.checkedButton().property("config_value")
        self.config["clipboard_watch"] = self.clipboard_watch_checkbox.isChecked()
        self.config["auto_check_favorites_on_start"] = self.fav_autocheck_checkbox.isChecked()
        self.config["auto_update_check"] = self.auto_update_checkbox.isChecked()
        filename_parts: dict[str, bool] = {}; filename_order: list[str] = []
        for i in range(self.order_list.count()):
            it = self.order_list.item(i); key = it.data(ROLE_KEY)
            filename_order.append(key); filename_parts[key] = (it.checkState() == Qt.CheckState.Checked)
        self.config["filename_parts"] = filename_parts; self.config["filename_order"] = filename_order

        if self.quality_button_group.checkedButton(): self.config["quality"] = self.quality_button_group.checkedButton().property("config_value")
        self.config["preferred_codec"] = self.codec_combo.currentData()
        self.config["hardware_encoder"] = self.hw_encoder_combo.currentData()
        self.config["quality_cpu_h264_crf"] = self.q_cpu_h264_crf.value()
        self.config["quality_cpu_h265_crf"] = self.q_cpu_h265_crf.value()
        self.config["quality_cpu_vp9_crf"] = self.q_cpu_vp9_crf.value()
        self.config["quality_cpu_av1_crf"] = self.q_cpu_av1_crf.value()
        self.config["quality_gpu_cq"] = self.q_gpu_cq.value()

        self.config["download_subtitles"] = self.download_subs_checkbox.isChecked()
        self.config["embed_subtitles"] = self.embed_subs_checkbox.isChecked()
        if self.subtitle_format_button_group.checkedButton():
            self.config["subtitle_format"] = self.subtitle_format_button_group.checkedButton().property("config_value")

        if self.conversion_button_group.checkedButton(): self.config["conversion_format"] = self.conversion_button_group.checkedButton().property("config_value")
        self.config["delete_on_conversion"] = self.delete_original_checkbox.isChecked()
        self.config["embed_thumbnail"] = self.embed_thumbnail_checkbox.isChecked()
        self.config["ignore_ssl_errors"] = self.ignore_ssl_checkbox.isChecked()
        keywords_str = self.exclude_keywords_edit.text()
        self.config["series_exclude_keywords"] = [k.strip() for k in keywords_str.split(',') if k.strip()]

        if not save_config(self.config):
            QMessageBox.warning(
                self, "설정 저장 실패",
                "설정 파일을 저장하지 못했습니다.\n"
                "프로그램 폴더에 쓰기 권한이 있는지 확인해 주세요.\n"
                "변경한 내용은 이번 실행에만 적용되며 다음 실행 시 사라집니다."
            )
        self.accept()
