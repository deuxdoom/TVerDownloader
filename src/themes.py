# src/themes.py

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import pyqtSignal, Qt, QPropertyAnimation, QEasingCurve, pyqtProperty, QEvent
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen

class ThemeSwitch(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(60, 28)
        self._checked = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._circle_position = 3
        self.animation = QPropertyAnimation(self, b"circle_position", self)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.setDuration(200)

        self.setChecked(False)  # 초기 상태 설정 (light)

    @pyqtProperty(int)
    def circle_position(self):
        return self._circle_position

    @circle_position.setter
    def circle_position(self, pos):
        self._circle_position = pos
        self.update()

    def setChecked(self, checked):
        if self._checked != checked:  # 상태 변경 시에만 처리
            self._checked = checked
            self.animation.stop()
            end_value = self.width() - self.height() + 3 if checked else 3
            self.animation.setStartValue(self._circle_position)
            self.animation.setEndValue(end_value)
            self.animation.start()
            self.toggled.emit(checked)  # 상태 변경 시 시그널 발송
            self.update_theme('dark' if checked else 'light')  # 테마 동기화
            print(f"setChecked: {checked}, circle_position: {self._circle_position}")  # 디버그 로그

    def isChecked(self):
        return self._checked

    def mouseReleaseEvent(self, event):
        # 클릭 시 토글 상태 변경
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_rect = self.rect()
        bg_color = self._bg_color_on if self._checked else self._bg_color_off
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(bg_rect, 14, 14)

        painter.setBrush(QBrush(self._circle_color))
        painter.drawEllipse(self._circle_position, 3, 22, 22)
        print(f"paintEvent: checked={self._checked}, circle_position={self._circle_position}")  # 디버그 로그

    def update_theme(self, theme):
        if theme == 'dark':
            self._bg_color_off = QColor("#4f5b6e")
            self._bg_color_on = QColor("#62a0ea")
            self._circle_color = QColor("#ffffff")
        else:
            self._bg_color_off = QColor("#cccccc")
            self._bg_color_on = QColor("#0078d4")
            self._circle_color = QColor("#ffffff")
        self.update()