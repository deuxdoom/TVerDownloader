# src/series_dialog.py
# 수정: '전체 선택' 버튼이 _toggle_all_checkboxes(check=True)를 명시적으로 호출하도록 수정

from typing import List, Dict
from pathlib import Path

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QDialogButtonBox
)
from src.widgets import ThumbnailDownloader, THUMBNAIL_CACHE_DIR

class SeriesSelectionDialog(QDialog):
    """시리즈의 에피소드 목록을 보여주고 사용자가 다운로드할 항목을 선택하게 하는 다이얼로그."""
    
    def __init__(self, episode_info: List[Dict[str, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("시리즈 에피소드 선택")
        self.setMinimumSize(720, 540)

        self._thumb_threads: Dict[str, ThumbnailDownloader] = {}
        THUMBNAIL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

        root = QVBoxLayout(self); root.setContentsMargins(16, 16, 16, 16); root.setSpacing(10)
        desc_label = QLabel(f"다운로드할 에피소드를 선택하세요. (총 {len(episode_info)}개)"); root.addWidget(desc_label)
        
        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListWidget.ViewMode.ListMode)
        self.list_widget.setIconSize(QSize(128, 72))
        root.addWidget(self.list_widget, 1)

        for episode in episode_info:
            item = QListWidgetItem(episode["title"])
            item.setData(Qt.ItemDataRole.UserRole, episode["url"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.list_widget.addItem(item)
            self._load_or_download_thumbnail(item, episode)

        button_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("전체 선택")
        self.deselect_all_btn = QPushButton("전체 해제")
        button_layout.addWidget(self.select_all_btn); button_layout.addWidget(self.deselect_all_btn); button_layout.addStretch(1)
        self.dialog_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.dialog_buttons.button(QDialogButtonBox.StandardButton.Ok).setText("선택한 항목 추가")
        self.dialog_buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        button_layout.addWidget(self.dialog_buttons); root.addLayout(button_layout)
        
        # --- 시그널 연결 수정 ---
        self.select_all_btn.clicked.connect(lambda: self._toggle_all_checkboxes(check=True))
        self.deselect_all_btn.clicked.connect(lambda: self._toggle_all_checkboxes(check=False))
        self.dialog_buttons.accepted.connect(self.accept)
        self.dialog_buttons.rejected.connect(self.reject)

    def _load_or_download_thumbnail(self, item: QListWidgetItem, episode_meta: Dict[str, str]):
        thumb_url = episode_meta.get("thumbnail_url")
        if not thumb_url: return

        try:
            episode_id = episode_meta["url"].strip('/').split('/')[-1]
            cache_path = THUMBNAIL_CACHE_DIR / f"{episode_id}.jpg"
            if cache_path.exists():
                pixmap = QPixmap(str(cache_path))
                if not pixmap.isNull(): item.setIcon(QIcon(pixmap))
            else:
                thread = ThumbnailDownloader(thumb_url, self)
                thread.finished.connect(lambda result: self._on_thumb_finished(item, result, cache_path))
                self._thumb_threads[thumb_url] = thread
                thread.start()
        except Exception:
            pass

    def _on_thumb_finished(self, item: QListWidgetItem, result: tuple, cache_path: Path):
        try: url, data = result
        except (TypeError, ValueError): return
        
        self._thumb_threads.pop(url, None)
        
        if data:
            try: cache_path.write_bytes(data)
            except OSError: pass
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                item.setIcon(QIcon(pixmap))

    def _toggle_all_checkboxes(self, check: bool = True):
        """목록의 모든 체크박스 상태를 변경합니다."""
        state = Qt.CheckState.Checked if check else Qt.CheckState.Unchecked
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(state)

    def get_selected_urls(self) -> List[str]:
        """선택된(체크된) 항목들의 URL 목록을 반환합니다."""
        selected_urls = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_urls.append(item.data(Qt.ItemDataRole.UserRole))
        return selected_urls