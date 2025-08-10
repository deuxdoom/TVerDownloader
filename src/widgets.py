# src/widgets.py
# 수정:
# - update_progress: 상태 표시 텍스트를 '비디오/오디오 다운로드 중...'에서 '비디오/오디오 다운 중...'으로 축약

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

        # 원본 고해상도 이미지를 저장
        self._original_pixmap = pixmap

        # 레이아웃 설정
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.image_label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.image_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.addWidget(self.scroll_area)

        # 이미지 라벨 클릭 시 창 닫기
        self.image_label.mousePressEvent = self._handle_mouse_press

    def showEvent(self, event):
        """다이얼로그가 처음 표시될 때 이미지 크기를 맞춥니다."""
        super().showEvent(event)
        QTimer.singleShot(0, self._update_scaled_pixmap)

    def resizeEvent(self, event):
        """다이얼로그 크기가 변경될 때마다 이미지 크기를 다시 맞춥니다."""
        super().resizeEvent(event)
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self):
        """창 크기에 맞춰 원본 이미지를 리사이즈하여 표시합니다."""
        if not self._original_pixmap or self._original_pixmap.isNull():
            return
        
        target_size = self.scroll_area.viewport().size()
        scaled_pixmap = self._original_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_label.setPixmap(scaled_pixmap)

    def _handle_mouse_press(self, event):
        """마우스 클릭 이벤트를 처리하여 좌클릭과 우클릭을 구분합니다."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.accept()  # 좌클릭 시 창 닫기
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.pos())  # 우클릭 시 컨텍스트 메뉴 표시

    def _show_context_menu(self, position):
        """이미지 저장 옵션이 포함된 컨텍스트 메뉴를 생성하고 표시합니다."""
        menu = QMenu(self)
        save_action = QAction("이미지 저장", self)
        save_action.triggered.connect(self._save_image)
        menu.addAction(save_action)
        
        # 위젯의 로컬 좌표를 화면의 글로벌 좌표로 변환하여 메뉴 위치 지정
        global_position = self.image_label.mapToGlobal(position)
        menu.exec(global_position)

    def _save_image(self):
        """파일 대화상자를 열어 원본 이미지를 저장합니다."""
        if not self._original_pixmap or self._original_pixmap.isNull():
            return
            
        # 파일 저장 대화상자 호출
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "이미지 저장",
            "thumbnail.png", # 기본 파일명
            "Image Files (*.png *.jpg *.jpeg)" # 파일 필터
        )
        
        # 사용자가 경로를 선택한 경우에만 저장
        if file_path:
            self._original_pixmap.save(file_path)


# ───────── 아이템 위젯 ─────────
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

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(12)
        
        self.thumb_label = QLabel(objectName="Thumb", alignment=Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setFixedSize(180, 102)
        self.thumb_label.mousePressEvent = self._on_thumb_clicked
        root.addWidget(self.thumb_label)

        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(6)
        
        self.title_label = QLabel("제목 로딩 중…", objectName="Title", wordWrap=True)
        self.status_label = QLabel("대기", objectName="Status")
        
        self.progress = QProgressBar(self)
        self.progress.setObjectName("Progress")
        self.progress.setTextVisible(False)
        self.progress.setMinimumHeight(16)

        center_layout.addWidget(self.title_label)
        center_layout.addWidget(self.status_label)
        center_layout.addWidget(self.progress)
        root.addWidget(center_widget, 1)

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
        
        if component == "비디오":
            progress_value = int(percent / 2)
        elif component == "오디오":
            progress_value = 50 + int(percent / 2)
        else:
            progress_value = self.progress.value()

        self.progress.setValue(progress_value)

        if "status" in payload:
            self.status = payload["status"]
            status_text = self.status
            
            if self.status == "다운로드 중":
                speed = payload.get('speed', '')
                eta = payload.get('eta', '')
                comp_text = f"{component} " if component else ""
                speed_eta_text = f"... {speed} (남은 시간: {eta})" if speed and eta else "..."
                # "다운로드 중"을 "다운 중"으로 수정
                status_text = f"{comp_text}다운 중{speed_eta_text}"

            self.status_label.setText(status_text)

            state_prop = "active"
            if self.status == "완료":
                state_prop = "done"
                self.progress.setValue(100)
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
        try:
            url, data = result
        except (TypeError, ValueError):
            return
        if url != self._thumb_url or not data:
            return
        
        pm = QPixmap()
        if pm.loadFromData(data):
            self._orig_thumb_pm = pm
            scaled_pm = pm.scaled(
                self.thumb_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.thumb_label.setPixmap(scaled_pm)