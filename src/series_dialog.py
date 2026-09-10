from pathlib import Path
from typing import Dict, List

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QDialogButtonBox
)
from src.i18n import t
from src.thumbnails import start_thumbnail_download, THUMBNAIL_CACHE_DIR
from src.window_frame import apply_dialog_frame

class SeriesSelectionDialog(QDialog):
    """시리즈의 회차 목록에서 받을 것을 고르는 창."""

    def __init__(self, episode_info: List[Dict[str, str]], parent=None,
                 theme: str = "light"):
        super().__init__(parent)
        self.setWindowTitle(t("series.title"))
        self.setMinimumSize(720, 540)

        self._pending_thumbs: Dict[str, List[tuple[QListWidgetItem, Path]]] = {}
        THUMBNAIL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

        root = QVBoxLayout(self); root.setContentsMargins(16, 16, 16, 16); root.setSpacing(10)
        desc_label = QLabel(t("series.description", count=len(episode_info))); root.addWidget(desc_label)

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
        self.select_all_btn = QPushButton(t("series.select_all"))
        self.deselect_all_btn = QPushButton(t("series.deselect_all"))
        button_layout.addWidget(self.select_all_btn); button_layout.addWidget(self.deselect_all_btn); button_layout.addStretch(1)
        self.dialog_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.dialog_buttons.button(QDialogButtonBox.StandardButton.Ok).setText(t("series.add_selected"))
        self.dialog_buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("PrimaryButton")
        self.dialog_buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("common.cancel"))
        button_layout.addWidget(self.dialog_buttons); root.addLayout(button_layout)

        self.select_all_btn.clicked.connect(lambda: self._toggle_all_checkboxes(check=True))
        self.deselect_all_btn.clicked.connect(lambda: self._toggle_all_checkboxes(check=False))
        self.dialog_buttons.accepted.connect(self.accept)
        self.dialog_buttons.rejected.connect(self.reject)

        apply_dialog_frame(self, theme, icon_name="download",
                           color_key="ctx_download")

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
                waiting = self._pending_thumbs.setdefault(thumb_url, [])
                waiting.append((item, cache_path))
                if len(waiting) == 1:
                    start_thumbnail_download(thumb_url, self._on_thumb_finished)
        except Exception:
            pass

    def _on_thumb_finished(self, result: tuple):
        try: url, data = result
        except (TypeError, ValueError): return

        waiting = self._pending_thumbs.pop(url, None)
        if not waiting or not data: return

        pixmap = QPixmap()
        if not pixmap.loadFromData(data): return
        icon = QIcon(pixmap)
        for item, cache_path in waiting:
            try: cache_path.write_bytes(data)
            except OSError: pass
            item.setIcon(icon)

    def _toggle_all_checkboxes(self, check: bool = True):
        state = Qt.CheckState.Checked if check else Qt.CheckState.Unchecked
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(state)

    def get_selected_urls(self) -> List[str]:
        selected_urls = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_urls.append(item.data(Qt.ItemDataRole.UserRole))
        return selected_urls
