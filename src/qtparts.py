"""widgets.py 밖에서도 쓰는 공용 Qt 부품. 앱 전역·창 조립·컨트롤러가 가져다 쓴다.

상당수는 QSS만으로 안 되는 자리를 코드로 메운 것이라 시각 규칙과 한 벌로 움직인다 -
`qss.py`가 `RoundedMenu`·`NoFocusDelegate`·`apply_combo_popup_shape`를 이름으로 가리킨다.
`GridListWidget`만 성격이 달라, 2열 그리드의 열 수를 직접 세는 배치 위젯이다.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSize, QRect, QEvent, QObject
from PyQt6.QtGui import QPainter, QPalette
from PyQt6.QtWidgets import (
    QWidget, QMenu, QListWidget, QListView, QTabBar,
    QAbstractItemView, QStyledItemDelegate, QStyle, QLayout, QSpacerItem, QSizePolicy,
    QCheckBox, QStyleOptionButton,
)


class WrappingCheckBox(QCheckBox):
    """체크 동작과 접근성은 Qt에 맡기고 긴 번역문에 필요한 높이만 늘린다."""

    TEXT_MIN_WIDTH = 160
    """긴 문구 하나가 설정 페이지의 최소 폭을 통째로 늘리지 않게 한다."""
    TEXT_LAYOUT_HEIGHT = 10000
    """줄바꿈 높이를 잴 때 현재 위젯 높이 때문에 마지막 줄이 잘리지 않게 한다."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        policy = self.sizePolicy()
        policy.setHorizontalPolicy(QSizePolicy.Policy.Preferred)
        policy.setVerticalPolicy(QSizePolicy.Policy.Minimum)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def _content_rect(self, width):
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.rect = QRect(0, 0, width, self.height())
        return self.style().subElementRect(QStyle.SubElement.SE_CheckBoxContents, option, self)

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        return QSize(min(hint.width(), self.TEXT_MIN_WIDTH), hint.height())

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        rect = self._content_rect(width)
        height = self.fontMetrics().boundingRect(
            QRect(0, 0, max(1, rect.width()), self.TEXT_LAYOUT_HEIGHT),
            Qt.TextFlag.TextWordWrap, self.text()).height()
        return max(super().sizeHint().height(), height)

    def paintEvent(self, event):
        option = QStyleOptionButton()
        self.initStyleOption(option)
        content = self._content_rect(self.width())
        option.text = ""
        painter = QPainter(self)
        self.style().drawControl(QStyle.ControlElement.CE_CheckBox, option, painter, self)
        group = QPalette.ColorGroup.Active if self.isEnabled() else QPalette.ColorGroup.Disabled
        painter.setPen(self.palette().color(group, QPalette.ColorRole.WindowText))
        painter.drawText(content, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                         | Qt.TextFlag.TextWordWrap, self.text())

    def hitButton(self, pos):
        return self.rect().contains(pos)


class FlowLayout(QLayout):
    """번역문이 길어져도 조작을 숨기지 않고 필요한 높이를 부모 배치에 전달한다."""

    def __init__(self, parent=None, spacing=8):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)
        self.invalidate()

    def addStretch(self):
        self.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation.Horizontal

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), False)

    def minimumSize(self):
        result = QSize()
        for item in self._items:
            if not item.isEmpty():
                result = result.expandedTo(item.minimumSize())
        return result

    def sizeHint(self):
        return self.minimumSize()

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, True)

    def _arrange(self, rect, apply):
        rows, row, used = [], [], 0
        for item in self._items:
            if item.spacerItem() is not None:
                if row:
                    row.append((item, QSize()))
                continue
            if item.isEmpty():
                continue
            hint = item.sizeHint().expandedTo(item.minimumSize())
            gap = self.spacing() if any(size.width() for _, size in row) else 0
            if row and used + gap + hint.width() > rect.width():
                rows.append(row)
                row, used, gap = [], 0, 0
            row.append((item, hint))
            used += gap + hint.width()
        if row:
            rows.append(row)
        y = rect.y()
        for row in rows:
            while row and row[-1][0].spacerItem() is not None:
                row.pop()
            if not row:
                continue
            widgets = [(item, size) for item, size in row if item.spacerItem() is None]
            height = max(size.height() for _, size in widgets)
            used = sum(size.width() for _, size in widgets) + self.spacing() * (len(widgets) - 1)
            stretches = len(row) - len(widgets)
            extra = max(0, rect.width() - used) // stretches if stretches else 0
            x, placed = rect.x(), False
            for item, size in row:
                if item.spacerItem() is not None:
                    x += extra
                    continue
                if placed:
                    x += self.spacing()
                if apply:
                    item.setGeometry(QRect(x, y + (height - size.height()) // 2, size.width(), size.height()))
                x += size.width()
                placed = True
            y += height + self.spacing()
        return max(0, y - rect.y() - self.spacing())


def apply_popup_shape(popup: QWidget):
    """제 창을 가진 팝업(메뉴·콤보 펼침 목록)을 모서리가 둥근 테두리 모양으로 만든다.

    셋을 함께 걸어야 한다 - Frameless가 빠지면 Qt가 알파로 합성하지 않아 모서리
    바깥이 검게 찍힌다(실측 밝기 0). 통째로 덮지 않는 것은 Popup 비트를 지키려는 것.
    """
    popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    popup.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    popup.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)


COMBO_POPUP_OBJECT = "ComboPopup"
"""콤보박스 펼침 목록을 감싸는 창에 붙이는 이름. 앱 전역 QSS로는 이 창을 가리킬 수 없다."""


def apply_combo_popup_shape(combo) -> None:
    """콤보 펼침 창을 메뉴와 같은 모양으로 만든다. 메뉴와 달리 창 힌트만으로는 안 된다.

    앱 전역 QSS가 이 창(QComboBoxPrivateContainer)에 닿지 않아 흰 사각형이 남는다.
    스타일시트를 이 창에 직접, 이름으로 좁혀 걸어야 안쪽 목록을 건드리지 않고 투명해진다.
    """
    container = combo.view().window()
    if container.objectName() == COMBO_POPUP_OBJECT:
        return
    container.setObjectName(COMBO_POPUP_OBJECT)
    apply_popup_shape(container)
    container.setStyleSheet(f"#{COMBO_POPUP_OBJECT} {{ background: transparent; }}")


def flatten_combo_popup_margins(container) -> None:
    """펼침 창이 안쪽 목록보다 위아래로 커지지 않게 여백을 없앤다.

    Qt가 배치 위아래에 넣는 6px짜리 빈 칸으로 첫 항목일 때만 콤보박스가 비친다.
    부르는 시점은 Show다 - Polish에서도 LayoutRequest에서도 창이 뜰 때 다시 6이었다.
    """
    layout = container.layout()
    if layout is None:
        return
    for index in range(layout.count()):
        spacer = layout.itemAt(index).spacerItem()
        if spacer is not None:
            spacer.changeSize(0, 0)
    layout.invalidate()


class RoundedMenu(QMenu):
    """모서리가 둥글고 테두리만 있는 메뉴.

    거는 것은 `apply_popup_shape`의 창 힌트 셋이다. 메뉴는 앱 전역 QSS가 그대로 닿아서
    콤보 펼침 목록과 달리 창에 직접 스타일시트를 걸 필요가 없다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        apply_popup_shape(self)
        self.setProperty("checkmarks", True)
        self.aboutToShow.connect(self._sync_checkmark_space)

    def _sync_checkmark_space(self):
        """체크 표시를 쓰지 않는 메뉴는 글자 앞자리(체크 자리)를 비워 두지 않는다.

        기본값을 '자리 없음'으로 두어야 Qt가 직접 만드는 입력칸 우클릭 메뉴도 빈칸 없이
        나온다. 열기 직전에 보는 것은 항목을 만든 뒤에 checkable을 켜는 경우가 있어서다.
        """
        checkmarks = any(action.isCheckable() for action in self.actions())
        if self.property("checkmarks") == checkmarks:
            return
        self.setProperty("checkmarks", checkmarks)
        self.style().unpolish(self)
        self.style().polish(self)


class NoFocusDelegate(QStyledItemDelegate):
    """행이 current가 될 때 스타일이 그리는 초점 사각형을 지운다.

    카드가 둥글어 그 각진 선이 네 귀퉁이에 자국으로 남는다. QSS로는 지워지지 않고
    (`outline: none`도 소용없다), 포커스 정책을 끄면 목록에서 방향키와 Del이 죽는다.
    """

    def paint(self, painter, option, index):
        option.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, option, index)


WHEEL_VIEWPORT_RATIO = 0.35
"""휠을 한 칸 굴렸을 때 목록이 움직이는 양. 뷰포트 높이에 대한 비율이다.

**윈도우의 휠 줄 수 설정을 일부러 따르지 않는다.** Qt 기본값(`ScrollPerItem`)에서 한
줄은 카드 한 장이라, 5줄로 둔 화면에서는 한 칸에 520px이 지나간다 - 뷰포트 476px보다
많아 굴리는 순간 이전 화면이 통째로 사라지고 그 사이 항목은 눈에 닿지도 않는다.
"""


class _SmoothWheelFilter(QObject):
    """휠 한 칸의 이동량을 뷰포트 높이에서 정한다. 목록이 아니라 viewport에 걸어야 한다."""

    def __init__(self, view: QAbstractItemView, ratio: float):
        super().__init__(view.viewport())
        self._view = view
        self._ratio = ratio

    def eventFilter(self, obj, event):
        """터치패드와 수식키 조합은 건드리지 않는다 - 이미 픽셀 단위로 오거나 확대를 뜻한다."""
        if event.type() != QEvent.Type.Wheel: return False
        if not event.pixelDelta().isNull(): return False
        if event.modifiers() != Qt.KeyboardModifier.NoModifier: return False
        steps = event.angleDelta().y() / 120.0
        if not steps: return False
        bar = self._view.verticalScrollBar()
        bar.setValue(bar.value() - round(steps * self._view.viewport().height() * self._ratio))
        return True


def apply_smooth_wheel(view: QAbstractItemView, ratio: float = WHEEL_VIEWPORT_RATIO):
    """목록을 픽셀 단위로 굴리고 휠 한 칸의 이동량을 지금 창 크기에서 정한다.

    **스크롤 모드만 바꾸면 거의 그대로다**(실측 109% → 100%). Qt가 이동 단위를 카드
    높이로 다시 잡아서, 한 칸이 몇 픽셀인지까지 우리가 정해야 값이 달라진다.
    """
    view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    view.viewport().installEventFilter(_SmoothWheelFilter(view, ratio))


class HoverTabBar(QTabBar):
    """탭 위에 있을 때만 손가락 커서로 바꾼다.

    탭바 위젯에 setCursor를 걸면 탭이 없는 자리까지 손가락이 떠서 누를 것이 있는
    것처럼 보인다 - `setExpanding(False)`라 탭은 왼쪽에만 서고, 실측하면 폭 1088px
    가운데 767px이 그 빈 자리다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pointing = False

    def event(self, e):
        kind = e.type()
        if kind in (QEvent.Type.HoverMove, QEvent.Type.HoverEnter):
            self._sync_cursor(self.tabAt(e.position().toPoint()) >= 0)
        elif kind == QEvent.Type.HoverLeave:
            self._sync_cursor(False)
        return super().event(e)

    def _sync_cursor(self, on_tab: bool):
        """달라질 때만 손댄다. HoverMove는 마우스를 움직이는 내내 들어온다."""
        if on_tab == self._pointing:
            return
        self._pointing = on_tab
        if on_tab:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()


class GridListWidget(QListWidget):
    """항목을 가로로 흘려 여러 열로 감싸는 목록. 한 칸이 min_item_width보다 좁아지면 열을 줄인다."""

    LAYOUT_SLACK = 2
    """칸 폭 합계가 뷰포트와 딱 맞아떨어지면 Qt가 마지막 칸을 다음 줄로 넘긴다. 2px면 유지된다."""

    def __init__(self, columns: int = 2, min_item_width: int = 300, parent=None):
        super().__init__(parent)
        self._columns = max(1, columns)
        self._min_item_width = min_item_width
        self._item_height = 0
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

    def set_item_height(self, height: int):
        self._item_height = height

    def column_width(self) -> int:
        """한 칸의 폭. 세로 스크롤바를 늘 띄워 두어 뷰포트 폭이 항목 수에 따라 변하지 않는다."""
        width = self.viewport().width() - self.LAYOUT_SLACK
        gap = 2 * self.spacing()
        columns = self._columns
        while columns > 1 and width // columns - gap < self._min_item_width:
            columns -= 1
        return max(self._min_item_width, width // columns - gap)

    def relayout(self):
        width = self.column_width()
        for index in range(self.count()):
            item = self.item(index)
            height = self._item_height or item.sizeHint().height()
            if item.sizeHint().width() != width or item.sizeHint().height() != height:
                item.setSizeHint(QSize(width, height))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.relayout()
