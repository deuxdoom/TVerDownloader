# 파일명: src/themes.py
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import pyqtSignal, Qt, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QPainter, QColor, QBrush

from src.qss import build_qss  # 전역 QSS 적용용


class ThemeSwitch(QWidget):
    toggled = pyqtSignal(bool)  # True=dark, False=light

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(60, 28)
        self._checked = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._circle_position = 3
        self.animation = QPropertyAnimation(self, b"circle_position", self)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.setDuration(200)

        # 스위치 자체 색 (앱 전체 테마와는 별개로 내부에서만 사용)
        self._bg_color_off = QColor("#cccccc")
        self._bg_color_on  = QColor("#0078d4")
        self._circle_color = QColor("#ffffff")

        # 초기 상태: light
        self.setChecked(False)
        self._update_switch_colors("light")

    @pyqtProperty(int)
    def circle_position(self):
        return self._circle_position

    @circle_position.setter
    def circle_position(self, pos):
        self._circle_position = pos
        self.update()

    def setChecked(self, checked: bool):
        if self._checked != checked:
            self._checked = checked
            self.animation.stop()
            end_value = self.width() - self.height() + 3 if checked else 3
            self.animation.setStartValue(self._circle_position)
            self.animation.setEndValue(end_value)
            self.animation.start()

            # 스위치 자체 색만 갱신(실제 앱 QSS 적용은 apply_theme에서)
            self._update_switch_colors('dark' if checked else 'light')

            self.toggled.emit(checked)
            self.update()

    def isChecked(self) -> bool:
        return self._checked

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)  # ← Python은 'not'
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

    def _update_switch_colors(self, theme: str):
        """스위치 컴포넌트 자체의 색만 변경."""
        if theme == 'dark':
            self._bg_color_off = QColor("#4f5b6e")
            self._bg_color_on  = QColor("#62a0ea")
            self._circle_color = QColor("#ffffff")
        else:
            self._bg_color_off = QColor("#cccccc")
            self._bg_color_on  = QColor("#0078d4")
            self._circle_color = QColor("#ffffff")
        self.update()

    # ← 호환용 public 메서드 (메인에서 호출)
    def update_theme(self, theme: str):
        """외부에서 테마 문자열(light/dark)을 넘기면 스위치 색만 동기화."""
        self._update_switch_colors(theme)

    def current_theme(self) -> str:
        return 'dark' if self._checked else 'light'


# 앱 전역에 QSS 적용(누적 방지: 초기화 후 재적용)
def apply_theme(app: QApplication, theme: str):
    app.setStyleSheet("")      # 이전 QSS 제거
    app.setStyle("Fusion")     # 플랫폼 차이 최소화(선택)
    qss = build_qss(theme)     # src/qss.py
    app.setStyleSheet(qss)
