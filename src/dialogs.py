# src/dialogs.py
# 수정: '일반' 탭의 테마 선택 라디오 버튼 순서를 '라이트 (기본값)', '다크' 순으로 변경

from __future__ import annotations
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSpinBox, QTabWidget, QWidget, QFileDialog, QDialogButtonBox, 
    QListWidget, QListWidgetItem, QAbstractItemView, QToolButton, QStyle,
    QRadioButton, QButtonGroup, QCheckBox
)
from src.utils import save_config

ROLE_KEY = Qt.ItemDataRole.UserRole

class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("설정")
        self.setMinimumSize(560, 520)
        root = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        root.addWidget(self.tabs)
        self._create_general_tab()
        self._create_filename_tab()
        self._create_quality_tab()
        self._create_post_action_tab()
        self._create_advanced_tab()
        self.buttons = QDialogButtonBox()
        save_btn = self.buttons.addButton("설정 저장", QDialogButtonBox.ButtonRole.AcceptRole)
        exit_btn = self.buttons.addButton("나가기", QDialogButtonBox.ButtonRole.RejectRole)
        root.addWidget(self.buttons)
        save_btn.clicked.connect(self._save_settings)
        exit_btn.clicked.connect(self.reject)

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
        self.concurrent_spinbox = QSpinBox(); self.concurrent_spinbox.setRange(1, 5)
        self.concurrent_spinbox.setValue(self.config.get("max_concurrent_downloads", 3))
        dl_count_layout.addWidget(self.concurrent_spinbox); dl_count_layout.addStretch(1); layout.addWidget(dl_count_group)
        theme_group = QWidget(); theme_layout = QVBoxLayout(theme_group); theme_layout.setContentsMargins(0,0,0,0)
        theme_layout.addWidget(QLabel("테마:"))
        self.theme_button_group = QButtonGroup(self)
        theme_radio_layout = QHBoxLayout()
        themes = {"라이트 (기본값)": "light", "다크": "dark"} # 순서 변경
        current_theme = self.config.get("theme", "light")
        for text, key in themes.items():
            radio = QRadioButton(text); radio.setProperty("config_value", key)
            self.theme_button_group.addButton(radio); theme_radio_layout.addWidget(radio)
            if key == current_theme: radio.setChecked(True)
        theme_radio_layout.addStretch(1); theme_layout.addLayout(theme_radio_layout); layout.addWidget(theme_group)
        layout.addStretch(1); self.tabs.addTab(tab, "일반")

    def _create_filename_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("파일명 구성 요소 선택 및 순서 설정:"))
        list_row = QHBoxLayout()
        self.order_list = QListWidget(); self.order_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.order_list.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        fm = self.order_list.fontMetrics(); row_h = max(28, fm.height() + 12)
        self.order_list.setStyleSheet("QListWidget::item{ padding:6px 8px; }")
        btn_col = QVBoxLayout()
        self.up_btn = QToolButton(toolTip="위로", shortcut="Alt+Up"); self.down_btn = QToolButton(toolTip="아래로", shortcut="Alt+Down")
        self.up_btn.setFixedSize(32, 32); self.down_btn.setFixedSize(32, 32)
        self.up_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        self.down_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        btn_col.addWidget(self.up_btn); btn_col.addWidget(self.down_btn); btn_col.addStretch(1)
        list_row.addWidget(self.order_list, 1); list_row.addLayout(btn_col); layout.addLayout(list_row, 1)
        self.part_names: dict[str, str] = {"series": "시리즈명", "upload_date": "방송날짜", "episode_number": "회차번호", "episode": "타이틀", "id": "고유ID"}
        parts_cfg: dict = self.config.get("filename_parts", {})
        current_order = self.config.get("filename_order", list(self.part_names.keys()))
        for key in current_order:
            if key not in self.part_names: continue
            item = QListWidgetItem(self.part_names[key]); item.setData(ROLE_KEY, key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable); item.setCheckState(Qt.CheckState.Checked if parts_cfg.get(key, True) else Qt.CheckState.Unchecked)
            item.setSizeHint(QSize(0, row_h)); self.order_list.addItem(item)
        pv = QHBoxLayout(); pv.addWidget(QLabel("파일명 미리보기:")); self.preview_label = QLabel(); pv.addWidget(self.preview_label, 1); layout.addLayout(pv)
        self.order_list.itemChanged.connect(self._update_preview)
        self.order_list.currentRowChanged.connect(self._sync_move_buttons)
        self.up_btn.clicked.connect(lambda: self._move_selected(-1)); self.down_btn.clicked.connect(lambda: self._move_selected(+1))
        self._update_preview(); self._sync_move_buttons(); self.tabs.addTab(tab, "파일명")

    def _move_selected(self, delta: int):
        row = self.order_list.currentRow(); new_row = row + delta
        if row < 0 or new_row < 0 or new_row >= self.order_list.count(): return
        item = self.order_list.takeItem(row); self.order_list.insertItem(new_row, item)
        self.order_list.setCurrentRow(new_row); self.order_list.scrollToItem(item)
        self._update_preview(); self._sync_move_buttons()

    def _sync_move_buttons(self, *_):
        row = self.order_list.currentRow(); cnt = self.order_list.count()
        self.up_btn.setEnabled(cnt > 1 and row > 0); self.down_btn.setEnabled(cnt > 1 and 0 <= row < cnt - 1)

    def _update_preview(self, *args):
        parts = [it.text() for i in range(self.order_list.count()) if (it := self.order_list.item(i)).checkState() == Qt.CheckState.Checked]
        self.preview_label.setText(" ".join(parts) + ".mp4")

    def _create_quality_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.addWidget(QLabel("다운로드 화질 선택:"))
        radio_layout = QVBoxLayout(); radio_layout.setSpacing(10); self.quality_button_group = QButtonGroup(self)
        qualities = {"최상 화질 (기본값)": "bv*+ba/b", "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]", "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]"}
        current_quality = self.config.get("quality", "bv*+ba/b")
        for text, key in qualities.items():
            radio = QRadioButton(text); radio.setProperty("config_value", key); self.quality_button_group.addButton(radio); radio_layout.addWidget(radio)
            if key == current_quality: radio.setChecked(True)
        layout.addLayout(radio_layout); layout.addStretch(1); self.tabs.addTab(tab, "화질")

    def _create_post_action_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.addWidget(QLabel("모든 다운로드 완료 후 작업:"))
        radio_layout = QVBoxLayout(); radio_layout.setSpacing(10); self.post_action_button_group = QButtonGroup(self)
        actions = {"아무 작업 안 함": "None", "다운로드 폴더 열기": "Open Folder", "1분 후 시스템 종료": "Shutdown"}
        current_action = self.config.get("post_action", "None")
        for text, key in actions.items():
            radio = QRadioButton(text); radio.setProperty("config_value", key); self.post_action_button_group.addButton(radio); radio_layout.addWidget(radio)
            if key == current_action: radio.setChecked(True)
        layout.addLayout(radio_layout); layout.addStretch(1); self.tabs.addTab(tab, "다운로드 후 작업")

    def _create_advanced_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setSpacing(20)
        bw_groupbox = QWidget(); bw_v_layout = QVBoxLayout(bw_groupbox); bw_v_layout.setContentsMargins(0,0,0,0)
        bw_v_layout.addWidget(QLabel("대역폭 제한:"))
        self.bw_limit_button_group = QButtonGroup(self); bw_radio_layout = QVBoxLayout(); bw_radio_layout.setSpacing(10)
        limits = {"제한 없음": "0", "1 MB/s": "1M", "5 MB/s": "5M", "10 MB/s": "10M", "50 MB/s": "50M"}
        current_limit = self.config.get("bandwidth_limit", "0")
        for text, key in limits.items():
            radio = QRadioButton(text); radio.setProperty("config_value", key); self.bw_limit_button_group.addButton(radio); bw_radio_layout.addWidget(radio)
            if key == current_limit: radio.setChecked(True)
        bw_v_layout.addLayout(bw_radio_layout); layout.addWidget(bw_groupbox)
        conv_groupbox = QWidget(); conv_v_layout = QVBoxLayout(conv_groupbox); conv_v_layout.setContentsMargins(0,0,0,0)
        conv_v_layout.addWidget(QLabel("다운로드 후 변환:"))
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
        layout.addStretch(1); self.tabs.addTab(tab, "고급")

    def _toggle_delete_checkbox(self):
        selected_button = self.conversion_button_group.checkedButton()
        is_conversion_selected = selected_button is not None and selected_button.property("config_value") != "none"
        self.delete_original_checkbox.setEnabled(is_conversion_selected)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "다운로드 폴더 선택", self.folder_path_edit.text())
        if folder: self.folder_path_edit.setText(folder)

    def _save_settings(self):
        self.config["download_folder"] = self.folder_path_edit.text()
        self.config["max_concurrent_downloads"] = self.concurrent_spinbox.value()
        if self.theme_button_group.checkedButton(): self.config["theme"] = self.theme_button_group.checkedButton().property("config_value")
        filename_parts: dict[str, bool] = {}; filename_order: list[str] = []
        for i in range(self.order_list.count()):
            it = self.order_list.item(i); key = it.data(ROLE_KEY)
            filename_order.append(key); filename_parts[key] = (it.checkState() == Qt.CheckState.Checked)
        self.config["filename_parts"] = filename_parts; self.config["filename_order"] = filename_order
        if self.quality_button_group.checkedButton(): self.config["quality"] = self.quality_button_group.checkedButton().property("config_value")
        if self.post_action_button_group.checkedButton(): self.config["post_action"] = self.post_action_button_group.checkedButton().property("config_value")
        if self.bw_limit_button_group.checkedButton(): self.config["bandwidth_limit"] = self.bw_limit_button_group.checkedButton().property("config_value")
        if self.conversion_button_group.checkedButton(): self.config["conversion_format"] = self.conversion_button_group.checkedButton().property("config_value")
        self.config["delete_on_conversion"] = self.delete_original_checkbox.isChecked()
        save_config(self.config)
        self.accept()