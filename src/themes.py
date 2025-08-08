# 파일명: src/themes.py
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import pyqtSignal, Qt, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QPainter, QColor, QBrush

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

        self._bg_color_off = QColor("#cccccc")
        self._bg_color_on  = QColor("#0078d4")
        self._circle_color = QColor("#ffffff")

        self.setChecked(False)  # 초기(light)

    @pyqtProperty(int)
    def circle_position(self):
        return self._circle_position

    @circle_position.setter
    def circle_position(self, pos):
        self._circle_position = pos
        self.update()

    def setChecked(self, checked):
        if self._checked != checked:
            self._checked = checked
            self.animation.stop()
            end_value = self.width() - self.height() + 3 if checked else 3
            self.animation.setStartValue(self._circle_position)
            self.animation.setEndValue(end_value)
            self.animation.start()
            self.toggled.emit(checked)
            self.update_theme('dark' if checked else 'light')

    def isChecked(self):
        return self._checked

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)  # 토글
        event.accept()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg_rect = self.rect()
        bg_color = self._bg_color_on if self._checked else self._bg_color_off
        p.setBrush(QBrush(bg_color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(bg_rect, 14, 14)
        p.setBrush(QBrush(self._circle_color))
        p.drawEllipse(self._circle_position, 3, 22, 22)

    def update_theme(self, theme):
        if theme == 'dark':
            self._bg_color_off = QColor("#4f5b6e")
            self._bg_color_on  = QColor("#62a0ea")
            self._circle_color = QColor("#ffffff")
        else:
            self._bg_color_off = QColor("#cccccc")
            self._bg_color_on  = QColor("#0078d4")
            self._circle_color = QColor("#ffffff")
        self.update()
