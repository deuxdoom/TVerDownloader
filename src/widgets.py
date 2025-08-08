# src/widgets.py

import os
import requests
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QProgressBar, QPushButton, QDialog
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont, QPixmap, QPainter, QColor, QBrush

class ThumbnailDialog(QDialog):
    """썸네일 확대를 위한 다이얼로그"""
    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle("썸네일 확대")
        self.setModal(True)
        layout = QVBoxLayout(self)
        self.image_label = QLabel()
        scaled_pixmap = pixmap.scaled(400, 225, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image_label)
        self.setFixedSize(scaled_pixmap.width() + 20, scaled_pixmap.height() + 20)

    def mousePressEvent(self, event):
        """이미지 클릭 시 다이얼로그 닫기 (X 버튼과 동일 효과)"""
        self.close()
        event.accept()

class DownloadItemWidget(QWidget):
    stop_requested = pyqtSignal(str)
    play_requested = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url
        self.status = '대기 중'
        self.final_filepath = None
        self.thumbnail_pixmap = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(128, 72)
        self.thumbnail_label.setStyleSheet("background-color: #2c313c; border-radius: 4px;")
        self.thumbnail_label.mousePressEvent = self.show_thumbnail_dialog
        layout.addWidget(self.thumbnail_label)
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        self.title_label = QLabel("정보 분석 중...")
        self.title_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.status_label = QLabel(url)
        self.status_label.setFont(QFont("Segoe UI", 9))
        progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("")
        self.status_icon_label = QLabel()
        self.status_icon_label.setFixedSize(22, 22)
        self.status_icon_label.hide()
        self.stop_button = QPushButton("×")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setFixedSize(22, 22)
        self.stop_button.setToolTip("현재 다운로드를 중단합니다.")
        self.stop_button.hide()
        progress_layout.addWidget(self.progress_bar, 1)
        progress_layout.addWidget(self.status_icon_label)
        progress_layout.addWidget(self.stop_button)
        info_layout.addWidget(self.title_label)
        info_layout.addWidget(self.status_label)
        info_layout.addLayout(progress_layout)
        layout.addLayout(info_layout, 1)
        layout.addStretch()
        self.thumbnail_thread = ThumbnailDownloader(None)
        self.stop_button.clicked.connect(lambda: self.stop_requested.emit(self.url))
        self.setMouseTracking(True)

    def mouseDoubleClickEvent(self, event):
        """더블 클릭 시 완료된 파일 재생"""
        if self.status == '완료' and self.final_filepath and os.path.exists(self.final_filepath):
            self.play_requested.emit(self.final_filepath)
        event.accept()

    def show_thumbnail_dialog(self, event):
        """썸네일 클릭 시 확대 다이얼로그 표시"""
        if self.thumbnail_pixmap:
            dialog = ThumbnailDialog(self.thumbnail_pixmap, self)
            dialog.exec()
        event.accept()

    def update_progress(self, data):
        self.status = data.get('status', self.status)
        if 'title' in data:
            self.title_label.setText(data['title'])
        if 'thumbnail_url' in data and data['thumbnail_url']:
            self.thumbnail_thread = ThumbnailDownloader(data['thumbnail_url'])
            self.thumbnail_thread.finished.connect(self.set_thumbnail)
            self.thumbnail_thread.start()
        if 'final_filepath' in data:
            self.final_filepath = data['final_filepath']
        status_text = data.get('status', '')
        if '다운로드 중' in status_text or '후처리 중' in status_text:
            self.stop_button.show()
            self.status_icon_label.hide()
            self.progress_bar.show()
            self.progress_bar.setStyleSheet("")
            percent = data.get('percent', self.progress_bar.value())
            speed = data.get('speed', '')
            eta = data.get('eta', '')
            self.progress_bar.setValue(int(percent))
            self.status_label.setText(f"{status_text} | {speed} | 남은 시간: {eta}")
        else:
            self.stop_button.hide()
            self.progress_bar.show()
            if status_text == '완료':
                self.progress_bar.setValue(100)
                self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #4caf50; }")
                self.status_icon_label.setText("✔")
                self.status_icon_label.setStyleSheet("color: #4caf50; font-size: 18px;")
                self.status_icon_label.show()
                self.status_label.setText("완료")
            elif status_text == '오류':
                self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #e57373; }")
                self.status_icon_label.setText("✖")
                self.status_icon_label.setStyleSheet("color: #e57373; font-size: 18px;")
                self.status_icon_label.show()
                self.status_label.setText("오류")

    def set_thumbnail(self, image_data):
        if image_data:
            pixmap = QPixmap()
            pixmap.loadFromData(image_data)
            self.thumbnail_pixmap = pixmap.scaled(128, 72, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            rounded = QPixmap(self.thumbnail_pixmap.size())
            rounded.fill(QColor("transparent"))
            painter = QPainter(rounded)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            brush = QBrush(self.thumbnail_pixmap)
            painter.setBrush(brush)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(self.thumbnail_pixmap.rect(), 4, 4)
            painter.end()
            self.thumbnail_label.setPixmap(rounded)

class ThumbnailDownloader(QThread):
    finished = pyqtSignal(bytes)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        if not self.url:
            self.finished.emit(None)
            return
        try:
            response = requests.get(self.url, timeout=10)
            response.raise_for_status()
            self.finished.emit(response.content)
        except:
            self.finished.emit(None)