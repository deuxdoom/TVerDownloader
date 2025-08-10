# src/widgets.py
# 수정:
# - 즐겨찾기 탭의 각 항목을 표시하는 FavoriteItemWidget 클래스 신규 추가
# - FavoriteItemWidget는 썸네일 다운로드 및 표시 기능을 포함

from __future__ import annotations
import os
import urllib.request
from typing import Optional, Dict

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QPixmap, QImage, QAction
from PyQt6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QProgressBar, QDialog,
    QScrollArea, QSizePolicy, QMenu, QFileDialog
)

# ───────── 썸네일 다운로더 ─────────
class ThumbnailDownloader(QThread):
    finished = pyqtSignal(object)
    def __init__(self, url: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            with urllib.request.urlopen(self.url, timeout=10) as r:
                data = r.read()
        except Exception:
            data = None
        self.finished.emit((self.url, data))

# ───────── 썸네일 팝업 (기능 수정) ─────────
class ImagePreviewDialog(QDialog):
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle("썸네일 미리보기")
        self.setMinimumSize(640, 360)
        self.setModal(True)
        self._original_pixmap = pixmap
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.image_label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.image_label)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.addWidget(self.scroll_area)
        self.image_label.mousePressEvent = self._handle_mouse_press

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._update_scaled_pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self):
        if not self._original_pixmap or self._original_pixmap.isNull(): return
        target_size = self.scroll_area.viewport().size()
        scaled_pixmap = self._original_pixmap.scaled(
            target_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(scaled_pixmap)

    def _handle_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.pos())

    def _show_context_menu(self, position):
        menu = QMenu(self)
        save_action = QAction("이미지 저장", self)
        save_action.triggered.connect(self._save_image)
        menu.addAction(save_action)
        global_position = self.image_label.mapToGlobal(position)
        menu.exec(global_position)

    def _save_image(self):
        if not self._original_pixmap or self._original_pixmap.isNull(): return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "이미지 저장", "thumbnail.png", "Image Files (*.png *.jpg *.jpeg)")
        if file_path:
            self._original_pixmap.save(file_path)

# ───────── 다운로드 아이템 위젯 ─────────
class DownloadItemWidget(QWidget):
    play_requested = pyqtSignal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.setObjectName("DownloadItem")
        self.url = url
        self.status: str = "대기"
        self.final_filepath: Optional[str] = None
        self._thumb_url: Optional[str] = None
        self._thumb_downloader: Optional[ThumbnailDownloader] = None
        self._orig_thumb_pm: Optional[QPixmap] = None

        root = QHBoxLayout(self); root.setContentsMargins(12, 10, 12, 10); root.setSpacing(12)
        
        self.thumb_label = QLabel(objectName="Thumb", alignment=Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setFixedSize(180, 102)
        self.thumb_label.mousePressEvent = self._on_thumb_clicked
        root.addWidget(self.thumb_label)

        center_widget = QWidget(); center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0); center_layout.setSpacing(6)
        
        self.title_label = QLabel("제목 로딩 중…", objectName="Title", wordWrap=True)
        self.status_label = QLabel("대기", objectName="Status")
        self.progress = QProgressBar(self, objectName="Progress", textVisible=False, minimumHeight=16)

        center_layout.addWidget(self.title_label); center_layout.addWidget(self.status_label)
        center_layout.addWidget(self.progress); root.addWidget(center_widget, 1)

    def mouseDoubleClickEvent(self, event):
        if self.status == "완료" and self.final_filepath and os.path.isfile(self.final_filepath):
            self.play_requested.emit(self.final_filepath)
        super().mouseDoubleClickEvent(event)

    def _on_thumb_clicked(self, event):
        if self._orig_thumb_pm and not self._orig_thumb_pm.isNull():
            ImagePreviewDialog(self._orig_thumb_pm, self).exec()

    def update_progress(self, payload: dict):
        if "thumbnail" in payload and payload["thumbnail"] != self._thumb_url:
            self._thumb_url = payload["thumbnail"]
            self._start_thumb_download(self._thumb_url)
        
        if payload.get("title"): self.title_label.setText(payload["title"])
        if "final_filepath" in payload: self.final_filepath = payload["final_filepath"]

        component = payload.get("component")
        percent = payload.get("percent", self.progress.value())
        if component == "비디오": progress_value = int(percent / 2)
        elif component == "오디오": progress_value = 50 + int(percent / 2)
        else: progress_value = self.progress.value()
        self.progress.setValue(progress_value)

        if "status" in payload:
            self.status = payload["status"]
            status_text = self.status
            if self.status == "다운로드 중":
                speed = payload.get('speed', ''); eta = payload.get('eta', '')
                comp_text = f"{component} " if component else ""
                speed_eta_text = f"... {speed} (남은 시간: {eta})" if speed and eta else "..."
                status_text = f"{comp_text}다운 중{speed_eta_text}"
            self.status_label.setText(status_text)
            state_prop = "active"
            if self.status == "완료":
                state_prop = "done"; self.progress.setValue(100)
            elif self.status in ("오류", "취소됨", "실패", "중단"):
                state_prop = "error"
            if self.progress.property("state") != state_prop:
                self.progress.setProperty("state", state_prop)
                self.progress.style().unpolish(self.progress)
                self.progress.style().polish(self.progress)
        self.update()

    def _start_thumb_download(self, url: str):
        if self._thumb_downloader and self._thumb_downloader.isRunning():
            self._thumb_downloader.terminate()
        self._thumb_downloader = ThumbnailDownloader(url, self)
        self._thumb_downloader.finished.connect(self._on_thumb_finished)
        self._thumb_downloader.start()

    def _on_thumb_finished(self, result: tuple):
        try: url, data = result
        except (TypeError, ValueError): return
        if url != self._thumb_url or not data: return
        pm = QPixmap();
        if pm.loadFromData(data):
            self._orig_thumb_pm = pm
            scaled_pm = pm.scaled(
                self.thumb_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.thumb_label.setPixmap(scaled_pm)

# ───────── 즐겨찾기 아이템 위젯 (신규) ─────────
class FavoriteItemWidget(QWidget):
    """즐겨찾기 탭의 각 시리즈 항목을 표시하는 위젯 (썸네일 포함)."""
    def __init__(self, url: str, meta: Dict[str, str], parent=None):
        super().__init__(parent)
        self.setObjectName("FavoriteItem")
        self.url = url
        self.meta = meta
        
        # UI 구성
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(12)

        self.thumb_label = QLabel(objectName="Thumb", alignment=Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setFixedSize(128, 72) # 다운로드 탭보다 작은 썸네일
        root.addWidget(self.thumb_label)

        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(4)
        
        self.url_label = QLabel(self.url)
        self.url_label.setWordWrap(True)
        self.last_check_label = QLabel(f"마지막 확인: {self.meta.get('last_check', '-')}")
        self.last_check_label.setObjectName("PaneSubtitle")

        info_layout.addWidget(self.url_label)
        info_layout.addWidget(self.last_check_label)
        info_layout.addStretch(1)
        root.addWidget(info_widget, 1)

        # 썸네일 다운로드 시작
        self._start_thumb_download()

    def _start_thumb_download(self):
        """시리즈 URL에서 ID를 추출하여 썸네일 URL을 만들고 다운로드를 시작합니다."""
        try:
            series_id = self.url.strip('/').split('/')[-1]
            if not series_id.startswith('sr'): return

            thumb_url = f"https://statics.tver.jp/images/content/thumbnail/series/large/{series_id}.jpg"
            
            self.downloader = ThumbnailDownloader(thumb_url, self)
            self.downloader.finished.connect(self._on_thumb_finished)
            self.downloader.start()
        except Exception:
            pass # URL 구조가 다르거나 ID 추출 실패 시 무시

    def _on_thumb_finished(self, result: tuple):
        try:
            url, data = result
        except (TypeError, ValueError):
            return
        
        if data:
            pm = QPixmap()
            if pm.loadFromData(data):
                scaled_pm = pm.scaled(
                    self.thumb_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.thumb_label.setPixmap(scaled_pm)