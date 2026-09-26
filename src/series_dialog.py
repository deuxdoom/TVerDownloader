from typing import Dict, List

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QDialogButtonBox
)
from src.i18n import t
from src.thumbnails import (cache_key_for, discard_thumbnail_requests, lookup_thumbnail,
                            remember_thumbnail, start_thumbnail_download)
from src.utils import THUMB_LIST_SIZE, pick_thumbnail
from src.window_frame import apply_dialog_frame

class SeriesSelectionDialog(QDialog):
    """시리즈의 회차 목록에서 받을 것을 고르는 창."""

    ICON_W, ICON_H = 128, 72

    def __init__(self, episode_info: List[Dict[str, str]], parent=None,
                 theme: str = "light"):
        super().__init__(parent)
        self.setWindowTitle(t("series.title"))
        self.setMinimumSize(720, 540)

        self._pending_thumbs: Dict[str, List[tuple[QListWidgetItem, str]]] = {}

        root = QVBoxLayout(self); root.setContentsMargins(16, 16, 16, 16); root.setSpacing(10)
        desc_label = QLabel(t("series.description", count=len(episode_info))); root.addWidget(desc_label)

        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListWidget.ViewMode.ListMode)
        self.list_widget.setIconSize(QSize(self.ICON_W, self.ICON_H))
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
        """캐시에 있으면 곧바로 얹고, 없으면 작업 스레드에 맡긴다. 같은 그림은 한 번만 받는다.

        **원본을 풀어 아이콘에 넣지 않는다.** 예전에는 회차마다 1280x720을 창 스레드에서 풀어
        예순 화짜리 창 하나가 뜨는 데 0.57초, 그림만 200MB가 넘었다(실측).
        """
        page_url = str(episode_meta.get("url", ""))
        thumb_url = pick_thumbnail(page_url, episode_meta.get("thumbnail_url"), THUMB_LIST_SIZE)
        if not thumb_url:
            return
        episode_id = page_url.strip('/').split('/')[-1]
        key = cache_key_for(episode_id, thumb_url)
        pixmap = lookup_thumbnail(key, self.ICON_W, self.ICON_H, self.devicePixelRatioF(), 0)
        if pixmap is not None:
            item.setIcon(QIcon(pixmap))
            return
        waiting = self._pending_thumbs.setdefault(thumb_url, [])
        waiting.append((item, key))
        if len(waiting) == 1:
            start_thumbnail_download(thumb_url, self._on_thumb_finished, key)

    def _on_thumb_finished(self, result: tuple):
        try:
            url, _data, image = result
        except (TypeError, ValueError):
            return
        waiting = self._pending_thumbs.pop(url, None)
        if not waiting or image is None or image.isNull():
            return
        for item, key in waiting:
            item.setIcon(QIcon(remember_thumbnail(key, image, self.ICON_W, self.ICON_H,
                                                  self.devicePixelRatioF(), 0)))

    def done(self, result: int):
        """닫힐 때 아직 시작하지 않은 그림 요청을 거둔다. 남기면 닫힌 창의 몫이 자리를 차지한다."""
        discard_thumbnail_requests(self)
        self._pending_thumbs.clear()
        super().done(result)

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
