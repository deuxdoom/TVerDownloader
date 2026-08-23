from __future__ import annotations
import os
import urllib.request
from typing import Optional, Dict
from pathlib import Path

from collections import deque

from PyQt6 import sip
from PyQt6.QtCore import (
    QObject, Qt, QThread, pyqtSignal, QSize, QTimer, QRectF, QEvent,
    QPropertyAnimation, QEasingCurve, pyqtProperty,
)
from PyQt6.QtGui import QPixmap, QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QProgressBar, QDialog,
    QScrollArea, QMenu, QToolButton, QListWidget, QListView,
    QSizePolicy, QStyledItemDelegate, QStyle
)

from src.icons import get_icon
from src.qss import blend, palette
from src.utils import (ERROR_STATUSES, FINISHED_STATUSES, NO_AUDIO_STATUS,
                       format_duration, item_percent)

THUMBNAIL_CACHE_DIR = Path("thumbnails")

LIST_THUMB_W, LIST_THUMB_H = 128, 72


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


class ElidedLabel(QLabel):
    """폭이 모자라면 말줄임표로 줄여 보여 주는 라벨. QLabel은 문장을 그냥 잘라 낸다."""

    def __init__(self, text: str = "", mode=Qt.TextElideMode.ElideRight, parent=None):
        super().__init__(parent)
        self._full_text = text
        self._mode = mode
        self.setWordWrap(False)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self._apply_elide()

    def setText(self, text: str):
        self._full_text = text
        self._apply_elide()

    def full_text(self) -> str:
        return self._full_text

    def _apply_elide(self):
        width = max(0, self.width())
        if width <= 0:
            super().setText(self._full_text)
            return
        super().setText(self.fontMetrics().elidedText(self._full_text, self._mode, width))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_elide()


class NoFocusDelegate(QStyledItemDelegate):
    """행이 current가 될 때 스타일이 그리는 초점 사각형을 지운다.

    카드가 둥글어 그 각진 선이 네 귀퉁이에 자국으로 남는다. QSS로는 지워지지 않고
    (`outline: none`도 소용없다), 포커스 정책을 끄면 목록에서 방향키와 Del이 죽는다.
    """

    def paint(self, painter, option, index):
        option.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, option, index)


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


class EmptyStateOverlay(QWidget):
    """목록이 비었을 때 뷰포트 위에 겹쳐 보이는 안내. 아이콘 하나와 글 두 줄.

    항목으로 넣으면 그것도 한 줄이라 선택되고 우클릭 메뉴가 뜨고 개수에 잡힌다.
    마우스는 통과시킨다 - 안 그러면 빈 목록에서 우클릭과 드롭을 이 위젯이 가로챈다.
    """

    ICON_SIZE = 44
    MARGIN = 24
    TEXT_MAX_WIDTH = 320
    """설명 줄의 최대 폭. 창을 넓히면 한 줄이 끝없이 길어져 읽는 눈이 되돌아온다."""

    def __init__(self, list_widget: QListWidget, icon_name: str,
                 title: str, description: str,
                 filtered_title: str = "", filtered_description: str = "",
                 theme: str = "light"):
        super().__init__(list_widget.viewport())
        self._list = list_widget
        self._icon_name = icon_name
        self._filtered = False
        self._messages = {
            False: (title, description),
            True: (filtered_title or title, filtered_description or description),
        }
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(self.MARGIN, self.MARGIN, self.MARGIN, self.MARGIN)
        layout.setSpacing(10)
        center = Qt.AlignmentFlag.AlignHCenter

        self.icon_label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.title_label = QLabel(title, objectName="EmptyStateTitle",
                                  alignment=Qt.AlignmentFlag.AlignCenter)
        self.description_label = QLabel(description, objectName="EmptyStateText",
                                        alignment=Qt.AlignmentFlag.AlignCenter,
                                        wordWrap=True)

        layout.addStretch(1)
        layout.addWidget(self.icon_label, 0, center)
        layout.addWidget(self.title_label, 0, center)
        layout.addWidget(self.description_label, 0, center)
        layout.addStretch(1)

        self._dead = False
        list_widget.destroyed.connect(self._on_list_destroyed)
        list_widget.viewport().installEventFilter(self)
        model = list_widget.model()
        for signal in (model.rowsInserted, model.rowsRemoved, model.modelReset):
            signal.connect(self.refresh)

        self.apply_theme(theme)
        self.refresh()

    def _on_list_destroyed(self, *_):
        self._dead = True

    def _usable(self) -> bool:
        """기대던 목록이 아직 살아 있는지.

        창을 닫으면 목록이 먼저 헐리는데 행이 사라졌다는 신호는 그 와중에도 나온다.
        없어진 쪽을 만지면 RuntimeError가 나고, 슬롯 안의 예외는 PyQt가 잡지 못한다.
        """
        return (not self._dead and not sip.isdeleted(self)
                and not sip.isdeleted(self._list))

    def apply_theme(self, theme: str):
        """아이콘을 지금 테마의 흐린 글자색으로 다시 그린다. 색은 SVG를 그릴 때 정해진다."""
        icon = get_icon(self._icon_name, palette(theme)["text_dim"], self.ICON_SIZE)
        self.icon_label.setPixmap(icon.pixmap(QSize(self.ICON_SIZE, self.ICON_SIZE),
                                              self.devicePixelRatioF()))

    def set_filtered(self, filtered: bool):
        """검색으로 걸러져 빈 것인지 알려 준다. 기록·즐겨찾기는 검색 때 목록을 새로 채운다."""
        if self._filtered == filtered:
            return
        self._filtered = filtered
        title, description = self._messages[filtered]
        self.title_label.setText(title)
        self.description_label.setText(description)
        self._fit()

    def refresh(self, *_):
        if not self._usable():
            return
        visible = self._list.count() == 0
        if visible:
            self._fit()
            self.raise_()
        self.setVisible(visible)

    def _fit(self):
        """목록 크기에 맞춰 자리를 잡고, 접히는 설명 줄의 높이를 직접 먹인다.

        QLabel은 wordWrap을 켜도 sizeHint가 한 줄 높이라, 가운데 정렬까지 걸면 두 줄이
        겹쳐 그려진다(실측: 필요 64px에 받은 것 16px). heightForWidth로 구해 넣는다.
        """
        if not self._usable():
            return
        rect = self._list.viewport().rect()
        self.setGeometry(rect)
        width = min(self.TEXT_MAX_WIDTH, max(1, rect.width() - 2 * self.MARGIN))
        self.description_label.setFixedWidth(width)
        self.description_label.setMinimumHeight(
            self.description_label.heightForWidth(width))

    def eventFilter(self, obj, event):
        """뷰포트 크기를 따라간다. 다른 탭의 목록은 숨어 있는 동안에도 배치가 돈다."""
        if (event.type() == QEvent.Type.Resize and self._usable()
                and obj is self._list.viewport()):
            self._fit()
        return False

    def showEvent(self, event):
        """탭이 열리며 처음 보일 때 자리를 다시 맞춘다. 숨은 동안에는 Resize가 오지 않는다."""
        self._fit()
        super().showEvent(event)


def rounded_thumbnail(pixmap: QPixmap, width: int, height: int,
                      dpr: float = 1.0, radius: int = 4) -> QPixmap:
    """가운데를 잘라 지정 크기를 꽉 채우고 모서리를 둥글린다. KeepAspectRatio는 위아래가 남는다."""
    dpr = dpr or 1.0
    dev_w, dev_h = round(width * dpr), round(height * dpr)
    scaled = pixmap.scaled(dev_w, dev_h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                           Qt.TransformationMode.SmoothTransformation)
    out = QPixmap(dev_w, dev_h)
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, width, height), radius, radius)
    painter.setClipPath(path)
    source = QRectF((scaled.width() - dev_w) / 2, (scaled.height() - dev_h) / 2, dev_w, dev_h)
    painter.drawPixmap(QRectF(0, 0, width, height), scaled, source)
    painter.end()
    return out


def set_selected_style(widgets, selected: bool):
    """선택 상태를 QSS가 읽을 수 있는 동적 속성으로 옮기고 다시 칠하게 한다."""
    value = "true" if selected else "false"
    for widget in widgets:
        if widget.property("selected") == value:
            continue
        widget.setProperty("selected", value)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

_running_thumb_threads: set = set()
_pending_thumbs: deque = deque()
MAX_CONCURRENT_THUMBS = 6


class ThumbnailDownloader(QThread):
    loaded = pyqtSignal(object)

    def __init__(self, url: str):
        super().__init__(None)
        self.url = url

    def run(self):
        try:
            with urllib.request.urlopen(self.url, timeout=10) as r:
                data = r.read()
        except Exception:
            data = None
        self.loaded.emit((self.url, data))


class _ThumbCoordinator(QObject):
    """썸네일 스레드의 종료를 메인 스레드에서 받아 다음 요청을 시작한다.

    QThread.finished는 워커 스레드에서 난다. 메인 스레드에 사는 QObject를 수신자로
    두어야 Qt가 큐 연결로 바꿔, 워커 스레드에서 새 QThread를 만드는 일이 없다.
    """

    def on_thread_finished(self):
        """이미 지워진 스레드를 먼저 걷어낸다.

        finished에 걸린 deleteLater와 순서 보장이 없어 C++ 객체가 먼저 파괴될 수 있다.
        isFinished()가 내는 RuntimeError는 슬롯 안의 예외라 PyQt6가 못 잡고 앱이 죽는다.
        """
        for thread in list(_running_thumb_threads):
            if sip.isdeleted(thread) or thread.isFinished():
                _running_thumb_threads.discard(thread)
        _pump_thumb_queue()


_coordinator: "Optional[_ThumbCoordinator]" = None


def _get_coordinator() -> "_ThumbCoordinator":
    global _coordinator
    if _coordinator is None:
        _coordinator = _ThumbCoordinator()
    return _coordinator


def _spawn_thumb_thread(url: str, on_loaded) -> ThumbnailDownloader:
    thread = ThumbnailDownloader(url)
    thread.loaded.connect(on_loaded)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(_get_coordinator().on_thread_finished)
    _running_thumb_threads.add(thread)
    thread.start()
    return thread


def _pump_thumb_queue():
    """자리가 나는 대로 대기 중인 요청을 시작한다."""
    while _pending_thumbs and len(_running_thumb_threads) < MAX_CONCURRENT_THUMBS:
        url, on_loaded = _pending_thumbs.popleft()
        receiver = getattr(on_loaded, "__self__", None)
        if receiver is not None and sip.isdeleted(receiver):
            continue
        _spawn_thumb_thread(url, on_loaded)


def start_thumbnail_download(url: str, on_loaded):
    """썸네일 요청을 넣는다. 동시 실행 수를 넘으면 대기열에 쌓인다.

    on_loaded는 QObject의 바운드 메서드여야 한다 - 람다는 수신자가 사라져도 연결이
    끊기지 않아 삭제된 위젯을 건드리며 죽는다. 주소가 비면 스레드를 쓰지 않는다.
    """
    if not url or not isinstance(url, str):
        return None
    if len(_running_thumb_threads) < MAX_CONCURRENT_THUMBS:
        return _spawn_thumb_thread(url, on_loaded)
    _pending_thumbs.append((url, on_loaded))
    return None


def cached_thumbnail(path: Path) -> Optional[QPixmap]:
    """캐시에 둔 그림을 읽는다. 그림으로 읽히지 않으면 그 파일을 지우고 None을 준다.

    깨진 파일을 두면 '파일이 있다'는 이유로 다시 받지 않아 그 카드만 영영 빈칸으로
    남는다. 읽어 보고 지우면 이미 그런 파일을 들고 있는 사람도 다음에 켤 때 낫는다.
    """
    if not path.exists():
        return None
    pixmap = QPixmap(str(path))
    if not pixmap.isNull():
        return pixmap
    try:
        path.unlink()
    except OSError:
        pass
    return None


def discard_thumbnail_requests(receiver) -> int:
    """이 카드가 걸어 둔 '아직 시작 전' 썸네일 요청을 대기열에서 뺀다.

    _pump_thumb_queue의 걸러 내기는 deleteLater가 처리된 뒤에야 참이 되어, 목록을
    새로 그리는 그 순간에는 늦다. 되돌려주는 수는 검사용이다.
    """
    if receiver is None:
        return 0
    remaining = [pair for pair in _pending_thumbs
                 if getattr(pair[1], "__self__", None) is not receiver]
    dropped = len(_pending_thumbs) - len(remaining)
    if dropped:
        _pending_thumbs.clear()
        _pending_thumbs.extend(remaining)
    return dropped


def clear_item_widgets(view: QListWidget):
    """목록을 비운다. 걸어 둔 카드에게 먼저 거둘 기회를 준다.

    clear()는 카드를 deleteLater로 미뤄, 그때까지 그 카드의 썸네일 요청이 지금 보이는
    것과 구별되지 않는다. 사라진 영상은 403이 올 때까지 여섯 자리 중 하나를 붙잡는다.
    """
    for row in range(view.count()):
        cleanup = getattr(view.itemWidget(view.item(row)), "cleanup", None)
        if callable(cleanup):
            cleanup()
    view.clear()


class ImagePreviewDialog(QDialog):
    """썸네일을 크게 보여 주는 창. 보기만 한다 - 저장은 목록 우클릭 메뉴가 맡는다."""

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

STRIP_WIDTH = 4
THUMB_W, THUMB_H = 160, 90
THUMB_RADIUS = 4


class BroadcastStrip(QWidget):
    """카드 왼쪽 가장자리의 4px 세로 상태 색 띠. 진행 중일 때만 밝기 변화가 돈다."""

    PULSE_MS = 1600
    PULSE_LIGHTEN = 35

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(STRIP_WIDTH)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._color = QColor("#DDE3EA")
        self._glow = 0.0
        self._anim = QPropertyAnimation(self, b"glow", self)
        self._anim.setDuration(self.PULSE_MS)
        self._anim.setStartValue(0.0)
        self._anim.setKeyValueAt(0.5, 1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.setLoopCount(-1)

    def get_glow(self) -> float:
        return self._glow

    def set_glow(self, value: float):
        self._glow = value
        self.update()

    glow = pyqtProperty(float, fget=get_glow, fset=set_glow)

    def set_state(self, color: QColor, pulsing: bool):
        self._color = QColor(color)
        if pulsing:
            if self._anim.state() != QPropertyAnimation.State.Running:
                self._anim.start()
        else:
            self.stop_pulse()
        self.update()

    def stop_pulse(self):
        """애니메이션을 멈추고 밝기를 원래대로 되돌린다."""
        if self._anim.state() != QPropertyAnimation.State.Stopped:
            self._anim.stop()
        self._glow = 0.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(self._color)
        if self._glow:
            color = color.lighter(100 + int(self.PULSE_LIGHTEN * self._glow))
        path = QPainterPath()
        radius = STRIP_WIDTH / 2
        path.addRoundedRect(QRectF(self.rect()), radius, radius)
        painter.fillPath(path, color)
        painter.end()


class DownloadItemWidget(QWidget):
    play_requested = pyqtSignal(str)
    open_folder_requested = pyqtSignal(str)

    PROGRESS_ANIM_MS = 240

    def __init__(self, url: str, theme: str = "light", parent=None):
        super().__init__(parent)
        self.setObjectName("DownloadItem")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.url = url
        self.status: str = "대기"
        self.final_filepath: Optional[str] = None
        self._thumb_url: Optional[str] = None
        self._thumb_downloader: Optional[ThumbnailDownloader] = None
        self._orig_thumb_pm: Optional[QPixmap] = None
        self._colors = palette(theme)
        self._selected = False

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 12, 0)
        root.setSpacing(0)

        self.strip = BroadcastStrip(self)
        root.addWidget(self.strip)

        body = QHBoxLayout()
        body.setContentsMargins(12, 10, 0, 10)
        body.setSpacing(12)

        self.thumb_label = QLabel(objectName="Thumb", alignment=Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setFixedSize(THUMB_W, THUMB_H)
        self.thumb_label.mousePressEvent = self._on_thumb_clicked
        body.addWidget(self.thumb_label)

        center = QVBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(6)

        self.title_label = QLabel("제목 로딩 중…", objectName="Title", wordWrap=True)

        progress_row = QHBoxLayout()
        progress_row.setContentsMargins(0, 0, 0, 0)
        progress_row.setSpacing(8)
        self.progress = QProgressBar(objectName="Progress", textVisible=False)
        self.percent_label = QLabel("0%", objectName="Status")
        self.percent_label.setMinimumWidth(38)
        self.percent_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.percent_label)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(4)
        self.status_label = QLabel("대기", objectName="Status")
        self.duration_label = QLabel("", objectName="Duration")
        self.duration_label.hide()
        self.play_btn = self._make_action_button("play", "재생")
        self.folder_btn = self._make_action_button("folder_open", "폴더 열기")
        meta_row.addWidget(self.status_label)
        meta_row.addStretch(1)
        meta_row.addWidget(self.duration_label)
        meta_row.addWidget(self.play_btn)
        meta_row.addWidget(self.folder_btn)

        center.addStretch(1)
        center.addWidget(self.title_label)
        center.addLayout(progress_row)
        center.addLayout(meta_row)
        center.addStretch(1)
        body.addLayout(center, 1)
        root.addLayout(body, 1)

        self._progress_anim = QPropertyAnimation(self.progress, b"value", self)
        self._progress_anim.setDuration(self.PROGRESS_ANIM_MS)
        self._progress_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.play_btn.clicked.connect(self._emit_play)
        self.folder_btn.clicked.connect(self._emit_open_folder)
        self._set_actions_visible(False)
        self.apply_theme(theme)

    def _make_action_button(self, icon_name: str, tooltip: str) -> QToolButton:
        btn = QToolButton(objectName="CardActionButton", toolTip=tooltip)
        btn.setFixedSize(28, 28)
        btn.setIconSize(QSize(16, 16))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("icon_name", icon_name)
        return btn

    def apply_theme(self, theme: str):
        """테마 전환 시 스트립 색과 액션 아이콘을 다시 칠한다."""
        self._colors = palette(theme)
        self._paint_action_icons()
        self._refresh_strip()

    def _paint_action_icons(self):
        color = self._colors["text" if self._selected else "text_dim"]
        for btn in (self.play_btn, self.folder_btn):
            btn.setIcon(get_icon(btn.property("icon_name"), color, 16))

    def set_selected(self, selected: bool):
        """목록에서 선택되면 흐린 글자와 아이콘을 본문 색으로 올린다."""
        if self._selected == selected:
            return
        self._selected = selected
        set_selected_style((self, self.title_label, self.status_label,
                            self.percent_label, self.duration_label), selected)
        self._paint_action_icons()

    def _strip_muted(self, ctx_key: str) -> str:
        return blend(self._colors[ctx_key], self._colors["surface"], 0.55)

    def _refresh_strip(self):
        """상태를 스트립 색으로 옮긴다. 음성 없음은 파일이 남았으므로 빨강이 아니라 경고색이다."""
        if self.status == NO_AUDIO_STATUS:
            self.strip.set_state(QColor(self._colors["warn"]), False)
        elif self.status in ERROR_STATUSES:
            self.strip.set_state(QColor(self._colors["danger"]), False)
        elif self.status == "완료":
            self.strip.set_state(QColor(self._strip_muted("ctx_download")), False)
        elif self.status == "대기":
            self.strip.set_state(QColor(self._colors["border"]), False)
        else:
            self.strip.set_state(QColor(self._colors["ctx_download"]), True)

    def _set_actions_visible(self, visible: bool):
        self.play_btn.setVisible(visible)
        self.folder_btn.setVisible(visible)

    def _has_file(self) -> bool:
        return bool(self.final_filepath) and os.path.isfile(self.final_filepath)

    def _emit_play(self):
        if self._has_file():
            self.play_requested.emit(self.final_filepath)

    def _emit_open_folder(self):
        if self._has_file():
            self.open_folder_requested.emit(self.final_filepath)

    def mouseDoubleClickEvent(self, event):
        if self.status in FINISHED_STATUSES and self._has_file():
            self.play_requested.emit(self.final_filepath)
        super().mouseDoubleClickEvent(event)

    def thumbnail_pixmap(self) -> Optional[QPixmap]:
        """저장에 쓸 원본 썸네일. 카드가 그리는 것은 모서리를 둥글린 축소본이라 따로 내준다."""
        if self._orig_thumb_pm is None or self._orig_thumb_pm.isNull():
            return None
        return self._orig_thumb_pm

    def _on_thumb_clicked(self, event):
        if self._orig_thumb_pm and not self._orig_thumb_pm.isNull():
            ImagePreviewDialog(self._orig_thumb_pm, self).exec()

    def _animate_progress(self, target: int):
        target = max(0, min(100, int(target)))
        self._progress_anim.stop()
        current = self.progress.value()
        if target == current:
            return
        if target < current:
            self.progress.setValue(target)
        else:
            self._progress_anim.setStartValue(current)
            self._progress_anim.setEndValue(target)
            self._progress_anim.start()
        self.percent_label.setText(f"{target}%")

    def reset_for_retry(self):
        self.status = "대기"
        self.final_filepath = None
        self._progress_anim.stop()
        self.progress.setValue(0)
        self.percent_label.setText("0%")
        if self.progress.property("state") != "active":
            self.progress.setProperty("state", "active")
            self.progress.style().unpolish(self.progress)
            self.progress.style().polish(self.progress)
        self.status_label.setText("대기")
        self._set_actions_visible(False)
        self._refresh_strip()

    def set_duration(self, seconds):
        """재생 시간을 재생·폴더 단추 왼쪽에 얹는다. 모르면 라벨째 숨긴다.

        빈 라벨을 남겨 두면 그 폭만큼 단추가 안쪽으로 밀려, 길이를 아는 카드와 모르는
        카드에서 단추 자리가 어긋난다.
        """
        text = format_duration(seconds)
        self.duration_label.setText(text)
        self.duration_label.setVisible(bool(text))

    def update_progress(self, payload: dict):
        if "thumbnail" in payload and payload["thumbnail"] != self._thumb_url:
            self._thumb_url = payload["thumbnail"]
            self._start_thumb_download(self._thumb_url)
        if payload.get("title"):
            self.title_label.setText(payload["title"])
        if "duration" in payload:
            self.set_duration(payload["duration"])
        if "final_filepath" in payload:
            self.final_filepath = payload["final_filepath"]

        component = payload.get("component")
        self._animate_progress(item_percent(payload.get("percent"),
                                            self.progress.value()))

        if "status" in payload:
            self.status = payload["status"]
            status_text = self.status
            if self.status == "다운로드 중":
                speed = payload.get("speed", "")
                eta = payload.get("eta", "")
                comp_text = f"{component} " if component else ""
                speed_eta_text = f"... {speed} (남은 시간: {eta})" if speed and eta else "..."
                status_text = f"{comp_text}다운 중{speed_eta_text}"
            self.status_label.setText(status_text)

            state_prop = "active"
            if self.status == "완료":
                state_prop = "done"
                self._animate_progress(100)
            elif self.status == NO_AUDIO_STATUS:
                state_prop = "warn"
                self._animate_progress(100)
            elif self.status in ERROR_STATUSES:
                state_prop = "error"
            if self.progress.property("state") != state_prop:
                self.progress.setProperty("state", state_prop)
                self.progress.style().unpolish(self.progress)
                self.progress.style().polish(self.progress)

            self._set_actions_visible(self.status in FINISHED_STATUSES and self._has_file())
            self._refresh_strip()
        self.update()

    def cleanup(self):
        """목록에서 제거되기 전에 애니메이션과 콜백을 확실히 끊는다."""
        self.strip.stop_pulse()
        self._progress_anim.stop()
        discard_thumbnail_requests(self)
        downloader = self._thumb_downloader
        self._thumb_downloader = None
        if downloader is None or sip.isdeleted(downloader):
            return
        try:
            downloader.loaded.disconnect(self._on_thumb_finished)
        except (TypeError, RuntimeError):
            pass

    def _start_thumb_download(self, url: str):
        self._thumb_downloader = start_thumbnail_download(url, self._on_thumb_finished)

    def _rounded_thumb(self, pixmap: QPixmap) -> QPixmap:
        return rounded_thumbnail(pixmap, THUMB_W, THUMB_H, self.devicePixelRatioF(), THUMB_RADIUS)

    def _on_thumb_finished(self, result: tuple):
        try:
            url, data = result
        except (TypeError, ValueError):
            return
        if url != self._thumb_url or not data:
            return
        pm = QPixmap()
        if not pm.loadFromData(data):
            return
        self._orig_thumb_pm = pm
        try:
            self.thumb_label.setPixmap(self._rounded_thumb(pm))
        except RuntimeError:
            pass

class FavoriteItemWidget(QWidget):
    """즐겨찾기 시리즈 카드. 2열이라 폭이 절반이고, 제목·URL을 줄여 높이를 붙든다."""

    CARD_HEIGHT = 112
    TITLE_LINES = 2
    TITLE_PADDING = 4

    def __init__(self, url: str, meta: Dict[str, str], theme: str = "light", parent=None):
        super().__init__(parent)
        self.setObjectName("FavoriteItem"); self.url = url; self.meta = meta
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        THUMBNAIL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._colors = palette(theme)
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 12, 0); root.setSpacing(0)
        self.strip = BroadcastStrip(self)
        root.addWidget(self.strip)
        body = QHBoxLayout(); body.setContentsMargins(12, 10, 0, 10); body.setSpacing(12)
        self.thumb_label = QLabel(objectName="Thumb", alignment=Qt.AlignmentFlag.AlignCenter); self.thumb_label.setFixedSize(LIST_THUMB_W, LIST_THUMB_H); body.addWidget(self.thumb_label)

        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0); info_layout.setSpacing(4)

        title_text = self.meta.get("title") or "(제목 확인 중...)"
        self.title_label = QLabel(title_text); self.title_label.setObjectName("Title")
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.title_label.setFixedHeight(
            self.title_label.fontMetrics().lineSpacing() * self.TITLE_LINES
            + self.TITLE_PADDING)

        self.url_label = ElidedLabel(self.url); self.url_label.setObjectName("PaneSubtitle")

        self.last_check_label = QLabel(f"마지막 확인: {self.meta.get('last_check') or '-'}"); self.last_check_label.setObjectName("PaneSubtitle")

        info_layout.addWidget(self.title_label)
        info_layout.addWidget(self.url_label)
        info_layout.addWidget(self.last_check_label)
        info_layout.addStretch(1); body.addLayout(info_layout, 1)
        root.addLayout(body, 1)

        self.apply_theme(theme)
        self._load_or_download_thumbnail()

    def sizeHint(self) -> QSize:
        return QSize(super().sizeHint().width(), self.CARD_HEIGHT)

    def apply_theme(self, theme: str):
        self._colors = palette(theme)
        self.strip.set_state(QColor(self._colors["ctx_favorites"]), False)

    def set_selected(self, selected: bool):
        set_selected_style((self, self.title_label, self.url_label, self.last_check_label), selected)

    def _load_or_download_thumbnail(self):
        try:
            series_id = self.url.strip('/').split('/')[-1]
            if not series_id.startswith('sr'): return
            self._cache_path = THUMBNAIL_CACHE_DIR / f"{series_id}.jpg"
            cached = cached_thumbnail(self._cache_path)
            if cached is not None:
                self._set_thumbnail_pixmap(cached)
            else:
                thumb_url = f"https://statics.tver.jp/images/content/thumbnail/series/large/{series_id}.jpg"
                self.downloader = start_thumbnail_download(thumb_url, self._on_thumb_finished)
        except Exception: pass

    def cleanup(self):
        """목록에서 빠지기 전에 썸네일 요청과 콜백을 끊는다. 지워진 라벨을 건드리면 앱이 죽는다."""
        discard_thumbnail_requests(self)
        downloader = getattr(self, "downloader", None)
        self.downloader = None
        if downloader is None or sip.isdeleted(downloader):
            return
        try:
            downloader.loaded.disconnect(self._on_thumb_finished)
        except (TypeError, RuntimeError):
            pass

    def _on_thumb_finished(self, result: tuple):
        """받아 온 것을 그림으로 읽어 보고, 읽히는 것만 캐시에 남긴다.

        사라진 영상 자리에 오류 쪽지가 200으로 오는 일이 있다(VPN 중간 페이지도 그렇다).
        그대로 적어 두면 파일이 있다는 이유로 다시 받지 않아 빈 카드가 굳는다.
        """
        try: url, data = result
        except (TypeError, ValueError): return
        if not data: return
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            return
        try: self._cache_path.write_bytes(data)
        except (OSError, AttributeError): pass
        self._set_thumbnail_pixmap(pixmap)

    def _set_thumbnail_pixmap(self, pixmap: QPixmap):
        """썸네일을 안전하게 넣는다. 라벨이 이미 삭제됐을 수 있다."""
        try:
            if self.thumb_label and pixmap and not pixmap.isNull():
                self.thumb_label.setPixmap(rounded_thumbnail(
                    pixmap, LIST_THUMB_W, LIST_THUMB_H, self.devicePixelRatioF()))
        except RuntimeError:
            pass


class HistoryItemWidget(QWidget):
    def __init__(self, url: str, meta: Dict[str, str], theme: str = "light", parent=None):
        super().__init__(parent)
        self.setObjectName("HistoryItem"); self.url = url; self.meta = meta
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        THUMBNAIL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._colors = palette(theme)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 12, 0)
        root.setSpacing(0)
        self.strip = BroadcastStrip(self)
        root.addWidget(self.strip)
        body = QHBoxLayout(); body.setContentsMargins(12, 10, 0, 10); body.setSpacing(12)
        self.thumb_label = QLabel(objectName="Thumb", alignment=Qt.AlignmentFlag.AlignCenter); self.thumb_label.setFixedSize(LIST_THUMB_W, LIST_THUMB_H); body.addWidget(self.thumb_label)
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0); info_layout.setSpacing(4)
        self.title_label = QLabel(self.meta.get("title", "(제목 없음)"), objectName="Title"); self.title_label.setWordWrap(True)
        self.date_label = QLabel(self.meta.get("date", "")); self.date_label.setObjectName("PaneSubtitle")
        self.url_label = QLabel(self.url); self.url_label.setObjectName("PaneSubtitle")
        info_layout.addWidget(self.title_label); info_layout.addWidget(self.date_label)
        info_layout.addWidget(self.url_label); info_layout.addStretch(1); body.addLayout(info_layout, 1)
        root.addLayout(body, 1)
        self.apply_theme(theme)
        self._load_or_download_thumbnail()

    def apply_theme(self, theme: str):
        self._colors = palette(theme)
        self.strip.set_state(QColor(self._colors["ctx_history"]), False)

    def set_selected(self, selected: bool):
        set_selected_style((self, self.title_label, self.date_label, self.url_label), selected)

    def _load_or_download_thumbnail(self):
        episode_thumb_url = self.meta.get("thumbnail_url")
        if not episode_thumb_url: return
        try:
            episode_id = self.url.strip('/').split('/')[-1]
            self._cache_path = THUMBNAIL_CACHE_DIR / f"{episode_id}.jpg"
            cached = cached_thumbnail(self._cache_path)
            if cached is not None:
                self._set_thumbnail_pixmap(cached)
            else:
                self.downloader = start_thumbnail_download(episode_thumb_url, self._on_thumb_finished)
        except Exception: pass

    def cleanup(self):
        """목록에서 빠지기 전에 썸네일 요청과 콜백을 끊는다. 지워진 라벨을 건드리면 앱이 죽는다."""
        discard_thumbnail_requests(self)
        downloader = getattr(self, "downloader", None)
        self.downloader = None
        if downloader is None or sip.isdeleted(downloader):
            return
        try:
            downloader.loaded.disconnect(self._on_thumb_finished)
        except (TypeError, RuntimeError):
            pass

    def _on_thumb_finished(self, result: tuple):
        """받아 온 것을 그림으로 읽어 보고, 읽히는 것만 캐시에 남긴다.

        사라진 영상 자리에 오류 쪽지가 200으로 오는 일이 있다(VPN 중간 페이지도 그렇다).
        그대로 적어 두면 파일이 있다는 이유로 다시 받지 않아 빈 카드가 굳는다.
        """
        try: url, data = result
        except (TypeError, ValueError): return
        if not data: return
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            return
        try: self._cache_path.write_bytes(data)
        except (OSError, AttributeError): pass
        self._set_thumbnail_pixmap(pixmap)

    def _set_thumbnail_pixmap(self, pixmap: QPixmap):
        """썸네일을 안전하게 넣는다. 라벨이 이미 삭제됐을 수 있다."""
        try:
            if self.thumb_label and pixmap and not pixmap.isNull():
                self.thumb_label.setPixmap(rounded_thumbnail(
                    pixmap, LIST_THUMB_W, LIST_THUMB_H, self.devicePixelRatioF()))
        except RuntimeError:
            pass
