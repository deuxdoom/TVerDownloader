import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QCheckBox, QComboBox, QSpinBox, QTabWidget, QWidget, QGridLayout,
                             QFileDialog, QDialogButtonBox, QListWidget, QListWidgetItem, QAbstractItemView,
                             QApplication)
from PyQt6.QtCore import Qt, QMimeData
from src.utils import save_config, load_config

class FileNameItemWidget(QWidget):
    """체크박스와 라벨을 포함한 커스텀 위젯"""
    def __init__(self, key, name, checked=True, parent=None):
        super().__init__(parent)
        self.key = key
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.checkbox = QCheckBox(name)
        self.checkbox.setChecked(checked)
        self.checkbox.setStyleSheet("font-size: 16px;")  # 텍스트 크기 증가 유지
        layout.addWidget(self.checkbox)
        layout.addStretch()

class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("설정")
        self.setMinimumWidth(500)
        self.layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        self.create_general_tab()
        self.create_filename_tab()
        self.create_quality_tab()
        self.create_post_action_tab()
        self.buttons = QDialogButtonBox()
        save_button = self.buttons.addButton("설정 저장", QDialogButtonBox.ButtonRole.AcceptRole)
        cancel_button = self.buttons.addButton("취소/나가기", QDialogButtonBox.ButtonRole.RejectRole)
        self.layout.addWidget(self.buttons)
        save_button.clicked.connect(self.save_settings)
        cancel_button.clicked.connect(self.reject)

    def create_general_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QLabel("다운로드 폴더:"))
        self.folder_path_edit = QLineEdit(self.config.get("download_folder", ""))
        self.folder_path_edit.setReadOnly(True)
        folder_layout.addWidget(self.folder_path_edit)
        browse_button = QPushButton("찾아보기...")
        browse_button.clicked.connect(self.browse_folder)
        folder_layout.addWidget(browse_button)
        layout.addLayout(folder_layout)
        concurrent_layout = QHBoxLayout()
        concurrent_layout.addWidget(QLabel("최대 동시 다운로드 개수:"))
        self.concurrent_spinbox = QSpinBox()
        self.concurrent_spinbox.setRange(1, 5)
        self.concurrent_spinbox.setValue(self.config.get("max_concurrent_downloads", 3))
        concurrent_layout.addWidget(self.concurrent_spinbox)
        concurrent_layout.addStretch(1)
        layout.addLayout(concurrent_layout)
        layout.addStretch(1)
        self.tabs.addTab(tab, "일반")

    def create_filename_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("파일명 구성 요소 선택 및 순서 설정:"))
        self.order_list = QListWidget()
        self.order_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.order_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        part_names = {
            "series": "시리즈명",
            "upload_date": "방송날짜",
            "episode_number": "회차번호",
            "episode": "타이틀",
            "id": "에피소드 ID"
        }
        parts = self.config.get("filename_parts", {})
        current_order = self.config.get("filename_order", list(part_names.keys()))
        for key in current_order:
            if key in part_names:
                item = QListWidgetItem()
                widget = FileNameItemWidget(key, part_names[key], parts.get(key, True), self)
                widget.checkbox.stateChanged.connect(self.update_preview)  # 체크박스 상태 변경 시 미리보기 갱신
                item.setSizeHint(widget.sizeHint())
                self.order_list.addItem(item)
                self.order_list.setItemWidget(item, widget)
        self.order_list.model().rowsMoved.connect(self.update_preview)  # 순서 변경 시 미리보기 갱신
        layout.addWidget(self.order_list)

        # 파일명 미리보기 추가
        preview_layout = QHBoxLayout()
        preview_layout.addWidget(QLabel("파일명 미리보기:"))
        self.preview_label = QLabel()
        preview_layout.addWidget(self.preview_label)
        preview_layout.addStretch()
        layout.addLayout(preview_layout)
        self.update_preview()  # 초기 미리보기 설정
        layout.addStretch(1)
        self.tabs.addTab(tab, "파일명")

    def update_preview(self, *args):
        """파일명 미리보기 업데이트 함수"""
        selected_parts = []
        for i in range(self.order_list.count()):
            item = self.order_list.item(i)
            widget = self.order_list.itemWidget(item)
            if widget.checkbox.isChecked():
                selected_parts.append(widget.checkbox.text())
        preview_text = " ".join(selected_parts)  # 공백으로 구분
        if "에피소드 ID" in selected_parts:
            preview_text = preview_text.replace("에피소드 ID", "[에피소드 ID]")
        preview_text += ".mp4" if preview_text else "(선택된 항목 없음)"
        self.preview_label.setText(preview_text)

    def create_quality_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("다운로드 화질/포맷 선택:"))
        self.quality_combo = QComboBox()
        qualities = {
            "최상 화질 (기본값)": "bv*+ba/b",
            "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
            "오디오만 추출 (MP3)": "audio_only"
        }
        for text, key in qualities.items():
            self.quality_combo.addItem(text, key)
        current_quality = self.config.get("quality", "bv*+ba/b")
        index = self.quality_combo.findData(current_quality)
        if index >= 0:
            self.quality_combo.setCurrentIndex(index)
        layout.addWidget(self.quality_combo)
        layout.addStretch(1)
        self.tabs.addTab(tab, "화질")

    def create_post_action_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("모든 다운로드 완료 후 작업:"))
        self.post_action_combo = QComboBox()
        actions = {"None": "아무 작업 안 함", "Open Folder": "다운로드 폴더 열기", "Shutdown": "1분 후 시스템 종료"}
        for key, text in actions.items():
            self.post_action_combo.addItem(text, key)
        current_action = self.config.get("post_action", "None")
        index = self.post_action_combo.findData(current_action)
        if index >= 0:
            self.post_action_combo.setCurrentIndex(index)
        layout.addWidget(self.post_action_combo)
        layout.addStretch(1)
        self.tabs.addTab(tab, "다운로드 후 작업")

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "다운로드 폴더 선택", self.folder_path_edit.text())
        if folder:
            self.folder_path_edit.setText(folder)

    def save_settings(self):
        self.config["download_folder"] = self.folder_path_edit.text()
        self.config["max_concurrent_downloads"] = self.concurrent_spinbox.value()
        self.config["filename_parts"] = {}
        self.config["filename_order"] = []
        for i in range(self.order_list.count()):
            item = self.order_list.item(i)
            widget = self.order_list.itemWidget(item)
            key = widget.key
            self.config["filename_parts"][key] = widget.checkbox.isChecked()
            self.config["filename_order"].append(key)
        self.config["quality"] = self.quality_combo.currentData()
        self.config["post_action"] = self.post_action_combo.currentData()
        save_config(self.config)
        self.accept()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0].toLocalFile()
            if os.path.isfile(url):
                self.parent().add_url_to_queue(url)
                self.accept()
            event.acceptProposedAction()