"""widgets.py 밖에서도 쓰는 공용 Qt 부품. 앱 전역·창 조립·컨트롤러가 가져다 쓴다.

상당수는 QSS만으로 안 되는 자리를 코드로 메운 것이라 시각 규칙과 한 벌로 움직인다 -
`qss.py`가 `RoundedMenu`·`NoFocusDelegate`·`apply_combo_popup_shape`를 이름으로 가리킨다.
`GridListWidget`만 성격이 달라, 2열 그리드의 열 수를 직접 세는 배치 위젯이다.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSize, QEvent
from PyQt6.QtWidgets import (
    QWidget, QMenu, QListWidget, QListView, QTabBar,
    QStyledItemDelegate, QStyle,
)


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
