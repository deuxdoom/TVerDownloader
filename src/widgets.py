# src/widgets.py
# FIX: Add checks in _set_thumbnail_pixmap for FavoriteItemWidget
#      and HistoryItemWidget to prevent RuntimeError when label is deleted.

from __future__ import annotations
import os
import urllib.request
from typing import Optional, Dict
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QPixmap, QImage, QAction
from PyQt6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QProgressBar, QDialog,
    QScrollArea, QSizePolicy, QMenu, QFileDialog
)

THUMBNAIL_CACHE_DIR = Path("thumbnails")

class ThumbnailDownloader(QThread):
    finished = pyqtSignal(object)
    def __init__(self, url: str, parent: Optional[object] = None):
        super().__init__(parent)
        self.url = url
    def run(self):
        try:
            # Use a context manager for urlopen
            with urllib.request.urlopen(self.url, timeout=10) as r:
                data = r.read()
        except Exception:
            data = None
        self.finished.emit((self.url, data))

class ImagePreviewDialog(QDialog):
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle("썸네일 미리보기"); self.setMinimumSize(640, 360); self.setModal(True)
        self._original_pixmap = pixmap
        self.scroll_area = QScrollArea(self); self.scroll_area.setWidgetResizable(True)
        self.image_label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter); self.scroll_area.setWidget(self.image_label)
        layout = QVBoxLayout(self); layout.setContentsMargins(5, 5, 5, 5); layout.addWidget(self.scroll_area)
        self.image_label.mousePressEvent = self._handle_mouse_press

    def showEvent(self, event): super().showEvent(event); QTimer.singleShot(0, self._update_scaled_pixmap)
    def resizeEvent(self, event): super().resizeEvent(event); self._update_scaled_pixmap()
    def _update_scaled_pixmap(self):
        if not self._original_pixmap or self._original_pixmap.isNull(): return
        target_size = self.scroll_area.viewport().size()
        scaled_pixmap = self._original_pixmap.scaled(target_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(scaled_pixmap)
    def _handle_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.accept()
        elif event.button() == Qt.MouseButton.RightButton: self._show_context_menu(event.pos())
    def _show_context_menu(self, position):
        menu = QMenu(self); save_action = QAction("이미지 저장", self)
        save_action.triggered.connect(self._save_image); menu.addAction(save_action)
        global_position = self.image_label.mapToGlobal(position); menu.exec(global_position)
    def _save_image(self):
        if not self._original_pixmap or self._original_pixmap.isNull(): return
        file_path, _ = QFileDialog.getSaveFileName(self, "이미지 저장", "thumbnail.png", "Image Files (*.png *.jpg *.jpeg)")
        if file_path: self._original_pixmap.save(file_path)

class DownloadItemWidget(QWidget):
    play_requested = pyqtSignal(str)
    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.setObjectName("DownloadItem"); self.url = url; self.status: str = "대기"
        self.final_filepath: Optional[str] = None; self._thumb_url: Optional[str] = None
        self._thumb_downloader: Optional[ThumbnailDownloader] = None; self._orig_thumb_pm: Optional[QPixmap] = None
        root = QHBoxLayout(self); root.setContentsMargins(12, 10, 12, 10); root.setSpacing(12)
        self.thumb_label = QLabel(objectName="Thumb", alignment=Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setFixedSize(180, 102); self.thumb_label.mousePressEvent = self._on_thumb_clicked; root.addWidget(self.thumb_label)
        center_widget = QWidget(); center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0); center_layout.setSpacing(6)
        self.title_label = QLabel("제목 로딩 중…", objectName="Title", wordWrap=True)
        self.status_label = QLabel("대기", objectName="Status")
        self.progress = QProgressBar(self, objectName="Progress", textVisible=False, minimumHeight=16)
        center_layout.addWidget(self.title_label); center_layout.addWidget(self.status_label)
        center_layout.addWidget(self.progress); root.addWidget(center_widget, 1)

    def mouseDoubleClickEvent(self, event):
        if self.status == "완료" and self.final_filepath and os.path.isfile(self.final_filepath): self.play_requested.emit(self.final_filepath)
        super().mouseDoubleClickEvent(event)

    def _on_thumb_clicked(self, event):
        if self._orig_thumb_pm and not self._orig_thumb_pm.isNull(): ImagePreviewDialog(self._orig_thumb_pm, self).exec()

    def reset_for_retry(self):
        self.status = "대기"
        self.final_filepath = None
        self.progress.setValue(0)
        if self.progress.property("state") != "active":
            self.progress.setProperty("state", "active")
            self.progress.style().unpolish(self.progress)
            self.progress.style().polish(self.progress)
        self.status_label.setText("대기")

    def update_progress(self, payload: dict):
        if "thumbnail" in payload and payload["thumbnail"] != self._thumb_url:
            self._thumb_url = payload["thumbnail"]; self._start_thumb_download(self._thumb_url)
        if payload.get("title"): self.title_label.setText(payload["title"])
        if "final_filepath" in payload: self.final_filepath = payload["final_filepath"]
        component = payload.get("component"); percent = payload.get("percent", self.progress.value())
        if component == "비디오": progress_value = int(percent / 2)
        elif component == "오디오": progress_value = 50 + int(percent / 2)
        else: progress_value = self.progress.value()
        self.progress.setValue(progress_value)
        if "status" in payload:
            self.status = payload["status"]; status_text = self.status
            if self.status == "다운로드 중":
                speed = payload.get('speed', ''); eta = payload.get('eta', '')
                comp_text = f"{component} " if component else ""
                speed_eta_text = f"... {speed} (남은 시간: {eta})" if speed and eta else "..."
                status_text = f"{comp_text}다운 중{speed_eta_text}"
            self.status_label.setText(status_text)
            state_prop = "active"
            if self.status == "완료": state_prop = "done"; self.progress.setValue(100)
            elif self.status in ("오류", "취소됨", "실패", "중단", "변환 오류"): state_prop = "error"
            if self.progress.property("state") != state_prop:
                self.progress.setProperty("state", state_prop); self.progress.style().unpolish(self.progress); self.progress.style().polish(self.progress)
        self.update()

    def _start_thumb_download(self, url: str):
        if self._thumb_downloader and self._thumb_downloader.isRunning(): self._thumb_downloader.terminate()
        self._thumb_downloader = ThumbnailDownloader(url, self); self._thumb_downloader.finished.connect(self._on_thumb_finished); self._thumb_downloader.start()

    def _on_thumb_finished(self, result: tuple):
        try: url, data = result
        except (TypeError, ValueError): return
        # Check if widget still exists before processing
        if self is None: return
        if url != self._thumb_url or not data: return
        pm = QPixmap();
        if pm.loadFromData(data):
            self._orig_thumb_pm = pm; scaled_pm = pm.scaled(self.thumb_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            # Another check before setting pixmap
            if self.thumb_label:
                self.thumb_label.setPixmap(scaled_pm)

class FavoriteItemWidget(QWidget):
    def __init__(self, url: str, meta: Dict[str, str], parent=None):
        super().__init__(parent)
        self.setObjectName("FavoriteItem"); self.url = url; self.meta = meta
        THUMBNAIL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        root = QHBoxLayout(self); root.setContentsMargins(8, 8, 8, 8); root.setSpacing(12)
        self.thumb_label = QLabel(objectName="Thumb", alignment=Qt.AlignmentFlag.AlignCenter); self.thumb_label.setFixedSize(128, 72); root.addWidget(self.thumb_label)

        info_widget = QWidget(); info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0); info_layout.setSpacing(4)

        title_text = self.meta.get("title") or "(제목 확인 중...)"
        self.title_label = QLabel(title_text); self.title_label.setObjectName("Title")
        self.title_label.setWordWrap(True)

        self.url_label = QLabel(self.url); self.url_label.setObjectName("PaneSubtitle")
        self.url_label.setWordWrap(True)

        self.last_check_label = QLabel(f"마지막 확인: {self.meta.get('last_check', '-')}"); self.last_check_label.setObjectName("PaneSubtitle")

        info_layout.addWidget(self.title_label)
        info_layout.addWidget(self.url_label)
        info_layout.addWidget(self.last_check_label)
        info_layout.addStretch(1); root.addWidget(info_widget, 1)

        self._load_or_download_thumbnail()

    def _load_or_download_thumbnail(self):
        try:
            series_id = self.url.strip('/').split('/')[-1]
            if not series_id.startswith('sr'): return
            cache_path = THUMBNAIL_CACHE_DIR / f"{series_id}.jpg"
            if cache_path.exists(): self._set_thumbnail_pixmap(QPixmap(str(cache_path)))
            else:
                thumb_url = f"https://statics.tver.jp/images/content/thumbnail/series/large/{series_id}.jpg"
                self.downloader = ThumbnailDownloader(thumb_url, self)
                self.downloader.finished.connect(lambda r: self._on_thumb_finished(r, cache_path)); self.downloader.start()
        except Exception: pass

    def _on_thumb_finished(self, result: tuple, cache_path: Path):
        try: url, data = result
        except (TypeError, ValueError): return
        # ✅ Check if widget still exists before processing
        if self is None: return
        if data:
            try: cache_path.write_bytes(data)
            except OSError: pass
            pixmap = QPixmap();
            if pixmap.loadFromData(data): self._set_thumbnail_pixmap(pixmap)

    # --- [수정된 부분 시작] ---
    def _set_thumbnail_pixmap(self, pixmap: QPixmap):
        """Safely sets the thumbnail pixmap, checking if the label exists."""
        # ✅ Check if the thumb_label exists before using it
        try:
            if self.thumb_label and pixmap and not pixmap.isNull():
                scaled_pm = pixmap.scaled(self.thumb_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.thumb_label.setPixmap(scaled_pm)
        except RuntimeError:
            # Catch the specific error if the label was deleted between the check and use
            pass
    # --- [수정된 부분 끝] ---

class HistoryItemWidget(QWidget):
    def __init__(self, url: str, meta: Dict[str, str], parent=None):
        super().__init__(parent)
        self.setObjectName("HistoryItem"); self.url = url; self.meta = meta
        THUMBNAIL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 4, 8, 4)
        root.setSpacing(12)
        self.thumb_label = QLabel(objectName="Thumb", alignment=Qt.AlignmentFlag.AlignCenter); self.thumb_label.setFixedSize(128, 72); root.addWidget(self.thumb_label)
        info_widget = QWidget(); info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0); info_layout.setSpacing(4)
        self.title_label = QLabel(self.meta.get("title", "(제목 없음)")); self.title_label.setWordWrap(True)
        self.date_label = QLabel(self.meta.get("date", "")); self.date_label.setObjectName("PaneSubtitle")
        self.url_label = QLabel(self.url); self.url_label.setObjectName("PaneSubtitle")
        info_layout.addWidget(self.title_label); info_layout.addWidget(self.date_label)
        info_layout.addWidget(self.url_label); info_layout.addStretch(1); root.addWidget(info_widget, 1)
        self._load_or_download_thumbnail()

    def _load_or_download_thumbnail(self):
        episode_thumb_url = self.meta.get("thumbnail_url")
        if not episode_thumb_url: return
        try:
            episode_id = self.url.strip('/').split('/')[-1]
            cache_path = THUMBNAIL_CACHE_DIR / f"{episode_id}.jpg"
            if cache_path.exists():
                self._set_thumbnail_pixmap(QPixmap(str(cache_path)))
            else:
                self.downloader = ThumbnailDownloader(episode_thumb_url, self)
                self.downloader.finished.connect(lambda r: self._on_thumb_finished(r, cache_path))
                self.downloader.start()
        except Exception: pass

    def _on_thumb_finished(self, result: tuple, cache_path: Path):
        try: url, data = result
        except (TypeError, ValueError): return
        # ✅ Check if widget still exists before processing
        if self is None: return
        if data:
            try: cache_path.write_bytes(data)
            except OSError: pass
            pixmap = QPixmap()
            if pixmap.loadFromData(data): self._set_thumbnail_pixmap(pixmap)

    def _set_thumbnail_pixmap(self, pixmap: QPixmap):
        """Safely sets the thumbnail pixmap, checking if the label exists."""
        # ✅ Check if the thumb_label exists before using it
        try:
            if self.thumb_label and pixmap and not pixmap.isNull():
                scaled_pm = pixmap.scaled(self.thumb_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.thumb_label.setPixmap(scaled_pm)
        except RuntimeError:
            # Catch the specific error if the label was deleted between the check and use
            pass