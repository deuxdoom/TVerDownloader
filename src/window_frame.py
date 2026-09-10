"""제목 표시줄 없이 뜨는 창의 껍데기 - 둥근 모서리, 오른쪽 아래로 지는 그림자, 크기 조절 띠.

창은 `WindowShell`(투명, 그림자를 그린다) 안에 `WindowSurface`(불투명, 둥근 배경)를 담는
두 겹이다. 그림자를 그릴 자리가 필요해 겉이 한 겹 더 있는 것이고, 그 여백만큼 창이 실제
내용보다 크다(`extra_size`).

**그림자는 테마를 따르지 않는다.** 그림자가 지는 곳은 우리 창이 아니라 뒤에 있는 남의
창과 바탕 화면이라, 앱이 어두운지 밝은지는 아무 상관이 없다. 트레이 아이콘 진행률에서
배운 것과 같은 자리다.
"""

from ctypes import wintypes

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPixmap
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout,
                             QWidget)

from src.qss import WINDOW_RADIUS

SHADOW_BLUR = 10
SHADOW_OFFSET = 3
"""그림자의 퍼짐과 치우침. 오른쪽 아래로만 SHADOW_OFFSET만큼 밀어 45도로 진다.

퍼짐이 치우침보다 커서 왼쪽·위에도 옅게 남는다 - 아래로만 그리면 창이 떠 있는 것이
아니라 아래에 띠를 하나 붙인 것처럼 보인다.
"""

SHADOW_LAYER_ALPHA = 5
"""겹쳐 칠하는 한 겹의 알파. SHADOW_BLUR겹이 쌓여 가장 진한 자리가 0.18이 된다.

한 겹씩 쌓아 번짐을 흉내 낸다 - QGraphicsDropShadowEffect는 창 전체를 픽스맵으로 다시
그린 뒤 흐리게 만들어, 목록이 든 창에서는 값이 너무 크다.
"""

SHADOW_MARGINS = (SHADOW_BLUR - SHADOW_OFFSET, SHADOW_BLUR - SHADOW_OFFSET,
                  SHADOW_BLUR + SHADOW_OFFSET, SHADOW_BLUR + SHADOW_OFFSET)
"""(왼쪽, 위, 오른쪽, 아래) 그림자가 차지하는 여백."""

GRIP_THICKNESS = 6
GRIP_CORNER = 14
"""크기 조절 띠의 두께와 모서리 조각의 한 변.

**띠는 투명한 그림자 여백이 아니라 불투명한 표면 안쪽에 둔다.** 완전히 투명한 픽셀은
클릭이 그대로 통과해 창에 닿지 않는다(실측: 여백을 누르면 뒤에 있던 창이 받았다).
"""


def extra_size() -> tuple[int, int]:
    """그림자 여백 때문에 창이 내용보다 커지는 (가로, 세로) 크기."""
    left, top, right, bottom = SHADOW_MARGINS
    return left + right, top + bottom


def make_frameless(window):
    """제목 표시줄을 떼고 배경을 투명하게 만든다. 창을 세우기 전에 부른다.

    투명 배경이 함께 있어야 그림자 여백이 뒤를 비춘다 - 프레임만 떼면 그 여백이 창
    배경색 사각형으로 남아 둥근 모서리가 사라진다.
    """
    window.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)


SC_MAXIMIZE = 0xF030
SC_RESTORE = 0xF120
WM_SYSCOMMAND = 0x0112
"""창을 최대화·복원하라는 윈도우의 지시. 화면 위쪽에 끌어다 붙이거나 Win+↑를 누르면 온다."""


class WindowFrame:
    """제목 표시줄 없는 창의 최대화를 우리가 맡는다. 되돌릴 크기도 여기서 쥔다.

    **Qt의 showMaximized를 쓰지 않는다.** 프레임 없는 창은 화면 전체로 넓히도록
    Qt가 일부러 그렇게 만들어 두어(QTBUG-8361) **작업 표시줄까지 덮는다**. 상태도
    WindowMaximized가 아니라 WindowFullScreen으로 잡혀(실측) `isMaximized()`가
    거짓으로 남고, 그 값에 기대면 모서리와 단추가 영영 안 바뀐다.

    작업 영역에 맞춰 우리가 직접 넓히면 두 문제가 함께 없어진다.
    """

    def __init__(self, window, on_changed=None):
        self.window = window
        self.on_changed = on_changed
        self._normal_geometry = None

    def is_maximized(self) -> bool:
        """되돌릴 크기를 들고 있으면 최대화 상태다."""
        return self._normal_geometry is not None

    def maximize(self):
        if self.is_maximized():
            return
        screen = self.window.screen()
        if screen is None:
            return
        self._normal_geometry = self.window.geometry()
        self.window.setGeometry(screen.availableGeometry())
        self._notify()

    def restore(self):
        if not self.is_maximized():
            return
        geometry, self._normal_geometry = self._normal_geometry, None
        self.window.setGeometry(geometry)
        self._notify()

    def toggle(self):
        self.restore() if self.is_maximized() else self.maximize()

    def restore_under_cursor(self, cursor: QPoint, grab_y: int):
        """최대화된 창을 되돌리면서 커서가 잡고 있던 자리를 유지한다.

        그냥 되돌리면 창이 원래 있던 자리로 가 버려, 화면 오른쪽 끝을 잡고 있었는데 창은
        왼쪽에서 따라오는 모양이 된다. 잡은 지점의 가로 비율을 그대로 옮긴다.
        """
        if not self.is_maximized():
            return
        ratio = (cursor.x() - self.window.x()) / max(1, self.window.width())
        self.restore()
        self.window.move(int(cursor.x() - ratio * self.window.width()),
                         cursor.y() - grab_y)

    def _notify(self):
        if self.on_changed is not None:
            self.on_changed(self.is_maximized())


def handle_system_command(frame: WindowFrame | None, message) -> bool:
    """윈도우가 보낸 최대화·복원 지시를 우리 쪽 최대화로 바꿔치기한다.

    화면 위쪽에 끌어다 붙이는 스냅과 Win+↑가 이 길로 온다. 가로채지 않으면 그때만 Qt의
    최대화가 돌아 작업 표시줄을 덮고, 우리 모서리·단추는 평소 모양으로 남는다.

    **WM_GETMINMAXINFO로는 막을 수 없다** - 그 메시지는 Qt가 자기 안에서 처리해 버려
    nativeEvent에도 앱 전역 네이티브 필터에도 오지 않는다(실측: 가로챈 횟수 0).
    """
    if frame is None:
        return False
    msg = wintypes.MSG.from_address(int(message))
    if msg.message != WM_SYSCOMMAND:
        return False
    command = msg.wParam & 0xFFF0
    if command == SC_MAXIMIZE:
        frame.maximize()
        return True
    if command == SC_RESTORE and frame.is_maximized():
        frame.restore()
        return True
    return False


class _EdgeGrip(QWidget):
    """가장자리에서 누르면 창 크기 조절을 시작하는 투명한 띠.

    끄는 일은 `startSystemResize`가 윈도우에 넘긴다 - 우리가 좌표를 따라가며 크기를
    고치면 화면 밖으로 나가는 것이나 다중 모니터 배율을 전부 다시 다뤄야 한다.
    """

    def __init__(self, parent: QWidget, edges, cursor):
        super().__init__(parent)
        self._edges = edges
        self.setCursor(cursor)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        handle = self.window().windowHandle()
        if handle is not None:
            handle.startSystemResize(self._edges)


class DragBar(QFrame):
    """누른 채 끌면 창이 따라오는 줄. 제목 표시줄을 없앤 자리를 대신한다.

    **누르자마자가 아니라 실제로 움직인 뒤에 창을 넘긴다**(DRAG_THRESHOLD). 누름과 동시에
    `startSystemMove`를 부르면 윈도우가 그 자리에서 자기 이동 루프를 도는데, 그동안 두 번째
    누름이 우리에게 오지 않아 더블클릭으로 최대화하는 길이 막힌다.
    """

    DRAG_THRESHOLD = 5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.frame: WindowFrame | None = None
        """최대화를 맡은 쪽. 창을 세운 뒤 UI가 끼워 넣는다."""
        self._press_global = None
        self._press_local = QPoint()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self._press_global = event.globalPosition().toPoint()
        self._press_local = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self._press_global is None:
            return
        now = event.globalPosition().toPoint()
        if (now - self._press_global).manhattanLength() < self.DRAG_THRESHOLD:
            return
        self._press_global = None
        window = self.window()
        if self.frame is not None and self.frame.is_maximized():
            self.frame.restore_under_cursor(
                now, self._press_local.y() + self.mapTo(window, QPoint(0, 0)).y())
        handle = window.windowHandle()
        if handle is not None:
            handle.startSystemMove()

    def mouseReleaseEvent(self, event):
        self._press_global = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = None
            if self.frame is not None:
                self.frame.toggle()


class ShadowShell(QWidget):
    """창 맨 바깥. 안쪽 표면을 여백만큼 안으로 들여놓고 그 여백에 그림자를 그린다."""

    SHADOW_COLOR = QColor(0, 0, 0)

    def __init__(self, resizable: bool = True):
        super().__init__()
        self.setObjectName("WindowShell")
        self._shadow = QPixmap()
        self._maximized = False
        self.surface = QFrame(objectName="WindowSurface")
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.addWidget(self.surface)
        self._apply_margins()
        self._grips = self._make_grips() if resizable else []
        """크기가 고정된 창에는 띠를 두지 않는다 - 끌 수 없는데 커서만 바뀌면 고장으로 읽힌다."""

    def _make_grips(self) -> list:
        cursors = Qt.CursorShape
        edges = Qt.Edge
        spec = (
            (edges.TopEdge, cursors.SizeVerCursor),
            (edges.BottomEdge, cursors.SizeVerCursor),
            (edges.LeftEdge, cursors.SizeHorCursor),
            (edges.RightEdge, cursors.SizeHorCursor),
            (edges.TopEdge | edges.LeftEdge, cursors.SizeFDiagCursor),
            (edges.TopEdge | edges.RightEdge, cursors.SizeBDiagCursor),
            (edges.BottomEdge | edges.LeftEdge, cursors.SizeBDiagCursor),
            (edges.BottomEdge | edges.RightEdge, cursors.SizeFDiagCursor),
        )
        return [_EdgeGrip(self, edge, cursor) for edge, cursor in spec]

    def _apply_margins(self):
        left, top, right, bottom = (0, 0, 0, 0) if self._maximized else SHADOW_MARGINS
        self.layout().setContentsMargins(left, top, right, bottom)

    def set_maximized(self, maximized: bool):
        """최대화되면 그림자와 여백을 걷는다. 화면에 꽉 찬 창 둘레에 그림자가 남을 자리가 없다."""
        if maximized == self._maximized:
            return
        self._maximized = maximized
        self._apply_margins()
        self._shadow = QPixmap()
        for grip in self._grips:
            grip.setVisible(not maximized)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._shadow = QPixmap()
        self._place_grips()

    def _place_grips(self):
        """띠를 표면 가장자리 **안쪽**에 붙인다. 여백 쪽은 클릭이 통과해 쓸 수 없다."""
        if self._maximized:
            return
        rect = self.surface.geometry()
        thick, corner = GRIP_THICKNESS, GRIP_CORNER
        inner_w = max(0, rect.width() - 2 * corner)
        inner_h = max(0, rect.height() - 2 * corner)
        places = (
            QRect(rect.x() + corner, rect.y(), inner_w, thick),
            QRect(rect.x() + corner, rect.bottom() - thick + 1, inner_w, thick),
            QRect(rect.x(), rect.y() + corner, thick, inner_h),
            QRect(rect.right() - thick + 1, rect.y() + corner, thick, inner_h),
            QRect(rect.x(), rect.y(), corner, corner),
            QRect(rect.right() - corner + 1, rect.y(), corner, corner),
            QRect(rect.x(), rect.bottom() - corner + 1, corner, corner),
            QRect(rect.right() - corner + 1, rect.bottom() - corner + 1, corner, corner),
        )
        for grip, place in zip(self._grips, places):
            grip.setGeometry(place)
            grip.raise_()

    def paintEvent(self, event):
        """그림자를 **덮어쓰기로** 그린다(CompositionMode_Source).

        기본값(SourceOver)으로 그리면 다시 그릴 때마다 알파가 그 위에 쌓인다 - 창을 몇 번
        건드리는 것만으로 옅던 그림자가 진한 테두리가 됐다(실측: 18%로 그린 것이 59%까지).
        투명한 자리를 투명으로 되돌려 놓는 일도 이 모드가 함께 한다.
        """
        if self._maximized:
            return
        if self._shadow.isNull():
            self._shadow = self._build_shadow()
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawPixmap(0, 0, self._shadow)

    def _build_shadow(self) -> QPixmap:
        """그림자를 한 장으로 그려 둔다. 창 크기가 바뀔 때만 다시 만든다."""
        ratio = self.devicePixelRatioF() or 1.0
        pixmap = QPixmap(int(self.width() * ratio), int(self.height() * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        color = QColor(self.SHADOW_COLOR)
        color.setAlpha(SHADOW_LAYER_ALPHA)
        painter.setBrush(color)
        inner = self.surface.geometry().translated(SHADOW_OFFSET, SHADOW_OFFSET)
        for step in range(SHADOW_BLUR, 0, -1):
            painter.drawRoundedRect(inner.adjusted(-step, -step, step, step),
                                    WINDOW_RADIUS + step, WINDOW_RADIUS + step)
        painter.end()
        return pixmap


DIALOG_TITLE_HEIGHT = 36
DIALOG_BUTTON_SIZE = 26
DIALOG_ICON_SIZE = 16
"""대화상자 제목 줄의 높이와 닫기 단추 크기.

메인 창 헤더(46px)보다 낮게 둔다 - 대화상자는 본문이 짧아 같은 높이로 두면 제목 줄이
창의 절반을 차지한다.
"""


class _DialogTitleBar(DragBar):
    """대화상자 맨 위 줄. 제목과 닫기 단추를 두고, 끌면 창이 따라온다."""

    def __init__(self, dialog, title: str, theme: str,
                 icon_name: str = "", color_key: str = "accent"):
        super().__init__(objectName="DialogTitleBar")
        from src.i18n import t
        from src.icons import get_hover_icon, get_icon
        from src.qss import SIDE_MARGIN, palette

        colors = palette(theme)
        self.setFixedHeight(DIALOG_TITLE_HEIGHT)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SIDE_MARGIN, 0, 6, 0)
        layout.setSpacing(8)

        self.icon_label = QLabel(objectName="DialogTitleIcon")
        if icon_name:
            icon = get_icon(icon_name, colors.get(color_key, colors["accent"]),
                            DIALOG_ICON_SIZE)
            self.icon_label.setPixmap(icon.pixmap(QSize(DIALOG_ICON_SIZE, DIALOG_ICON_SIZE)))
            layout.addWidget(self.icon_label)

        self.title_label = QLabel(title, objectName="DialogTitle")
        layout.addWidget(self.title_label)
        layout.addStretch(1)

        self.close_button = QToolButton(objectName="IconButton", toolTip=t("common.close"))
        self.close_button.setFixedSize(DIALOG_BUTTON_SIZE, DIALOG_BUTTON_SIZE)
        self.close_button.setIconSize(QSize(DIALOG_ICON_SIZE, DIALOG_ICON_SIZE))
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setProperty("window_close", "true")
        self.close_button.setIcon(get_hover_icon("cancel", colors["text"],
                                                 colors["danger_fg"], DIALOG_ICON_SIZE))
        self.close_button.clicked.connect(dialog.reject)
        layout.addWidget(self.close_button)


def _move_inside(window, center: QPoint, area: QRect):
    """창 가운데를 center에 맞추되 작업 영역 밖으로 나가지 않게 자른다."""
    frame = window.frameGeometry()
    frame.moveCenter(center)
    x = min(max(frame.x(), area.x()), max(area.x(), area.right() - frame.width() + 1))
    y = min(max(frame.y(), area.y()), max(area.y(), area.bottom() - frame.height() + 1))
    window.move(x, y)


def center_on_screen(window):
    """작업 표시줄을 뺀 영역 안에서 가운데로 옮긴다. 마우스가 있는 화면을 고른다."""
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    if screen is None:
        return
    area = screen.availableGeometry()
    _move_inside(window, area.center(), area)


def center_dialog(dialog):
    """대화상자를 부모 창 가운데에 놓는다. 부모가 트레이에 내려가 있으면 화면 가운데다.

    **Qt에 맡기면 어긋난다.** 프레임 두께를 (10, 40)으로 가정하고 그만큼 왼쪽 위로 미는데
    (실측: 크기가 확정된 대화상자 셋이 모두 정확히 그만큼 어긋났다) 제목 표시줄을 뗀 창에는
    뺄 프레임이 없다. 최소화된 부모로는 그 계산이 아예 되지 않아 왼쪽 위 구석에 붙는다.
    """
    parent = dialog.parentWidget()
    parent = parent.window() if parent is not None else None
    if parent is None or not parent.isVisible() or parent.isMinimized():
        center_on_screen(dialog)
        return
    screen = parent.screen() or QGuiApplication.primaryScreen()
    if screen is None:
        return
    _move_inside(dialog, parent.geometry().center(), screen.availableGeometry())


class _DialogPlacer(QObject):
    """창이 뜰 때 부모 가운데로 놓는 앱 필터.

    Show를 보는 것은 그 시점이 Qt가 제 계산으로 자리를 잡기 직전이라서다 - 여기서
    `move()`를 부르면 WA_Moved가 서서 그 계산을 건너뛴다.
    """

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show:
            center_dialog(obj)
        return False


WIDGET_SIZE_MAX = 16777215
"""Qt가 '제한 없음'으로 쓰는 크기. 이 값은 우리가 더하지 않는다."""


def _grow_for_chrome(dialog):
    """제목 줄과 그림자 여백만큼 창 크기를 키운다.

    대화상자가 정해 둔 크기는 **내용이 들어갈 자리**를 뜻한다. 그대로 두면 그 안에서
    제목 줄과 여백이 자리를 빼앗아 내용이 눌린다 - 설정 창 일반 탭에서 라디오 단추가
    서로 겹쳐 그려졌다(실측).
    """
    extra_w, extra_h = extra_size()
    extra_h += DIALOG_TITLE_HEIGHT

    def grown(value: int, extra: int) -> int:
        if value in (0, WIDGET_SIZE_MAX):
            return value
        return min(WIDGET_SIZE_MAX, value + extra)

    minimum, maximum = dialog.minimumSize(), dialog.maximumSize()
    dialog.setMinimumSize(grown(minimum.width(), extra_w), grown(minimum.height(), extra_h))
    dialog.setMaximumSize(grown(maximum.width(), extra_w), grown(maximum.height(), extra_h))
    dialog.resize(dialog.width() + extra_w, dialog.height() + extra_h)


def apply_dialog_frame(dialog, theme: str = "light", *, title: str = "",
                       resizable: bool = True, icon_name: str = "",
                       color_key: str = "accent"):
    """대화상자를 메인 창과 같은 모양으로 감싼다 - 제목 줄 · 둥근 모서리 · 그림자.

    **대화상자를 다 구성한 뒤에 부른다.** 이미 깔린 레이아웃을 표면 안으로 옮기는 방식이라
    먼저 부르면 옮길 것이 없다. QMessageBox처럼 자기 격자를 계속 다시 짜는 창도 그대로
    동작한다(실측: 옮긴 뒤 setText로 문구를 바꿔도 표면 안에서 다시 배치됐다).

    **닫기 단추는 `reject()`를 부른다.** QMessageBox에서는 그것이 Esc 단추를 누른 것과
    같은 길이라, 지금까지 제목 표시줄의 X가 하던 일이 그대로 이어진다.
    """
    inner = dialog.layout()
    make_frameless(dialog)
    dialog.setProperty("framed", "true")
    _grow_for_chrome(dialog)

    shell = ShadowShell(resizable=resizable)
    body = QWidget(objectName="DialogBody")
    if inner is not None:
        body.setLayout(inner)

    surface_layout = QVBoxLayout(shell.surface)
    surface_layout.setContentsMargins(0, 0, 0, 0)
    surface_layout.setSpacing(0)
    bar = _DialogTitleBar(dialog, title or dialog.windowTitle(), theme,
                          icon_name, color_key)
    surface_layout.addWidget(bar)
    surface_layout.addWidget(body, 1)

    outer = QVBoxLayout(dialog)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    outer.addWidget(shell)

    dialog.dialog_placer = _DialogPlacer(dialog)
    dialog.installEventFilter(dialog.dialog_placer)

    dialog.window_shell = shell
    dialog.title_bar = bar
    dialog.dialog_body = body
    """본문 상자. 원래 레이아웃이 이 안으로 옮겨져 있어, 그 레이아웃을 직접 손보던
    쪽(QMessageBox의 단추 정렬)은 `dialog.layout()`이 아니라 여기를 봐야 한다."""
    return shell
