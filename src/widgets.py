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
from src.utils import ERROR_STATUSES, FINISHED_STATUSES, NO_AUDIO_STATUS, item_percent

THUMBNAIL_CACHE_DIR = Path("thumbnails")

LIST_THUMB_W, LIST_THUMB_H = 128, 72


def apply_menu_shape(menu: QMenu):
    """메뉴를 '모서리가 둥글고 테두리만 있는' 모양으로 만드는 창 힌트 세 가지.

    `RoundedMenu`가 쓰는 것과 같은 것을 이미 만들어진 메뉴에도 걸 수 있게 떼어
    두었다. 입력칸 우클릭 메뉴는 Qt 안쪽에서 만들어져 우리가 클래스를 고를 수
    없는데, 그 메뉴만 그림자가 지고 모양이 달랐다(`MenuShapeGuard`).

    두 곳이 같은 함수를 부르게 해 둔 이유는, 한쪽만 고치면 우리 메뉴와 Qt 메뉴가
    조금씩 달라 보이기 때문이다. 무엇을 왜 거는지는 `RoundedMenu` 설명에 있다.
    """
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    menu.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    menu.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)


class RoundedMenu(QMenu):
    """모서리가 둥글고 테두리만 있는 메뉴.

    세 가지를 함께 걸어야 한다. 하나라도 빠지면 눈에 보이는 결과가 달라진다.

    1. `WA_TranslucentBackground` — QSS의 border-radius만으로는 둥글어지지 않는다.
       메뉴는 자기 창을 가진 팝업이라 모서리 바깥을 창 배경이 채우고, 둥근 테두리만
       그 위에 얹혀 네 귀퉁이가 각진 채로 남는다.
    2. `FramelessWindowHint` — **이것이 빠지면 모서리 바깥이 까맣게 찍힌다.**
       투명 속성만 켜도 Qt는 창을 알파로 합성하지 않아, 둥근 모양 바깥이 검게 남는다.
       화면을 직접 찍어 재 보면 모서리 밝기가 0이다(붙이면 226).
    3. `NoDropShadowWindowHint` — 그림자를 끈다. 테두리만 있는 쪽이 깔끔하다.

    예전 주석은 1번만으로 충분하고 2번을 붙이면 그림자가 사라진다고 적어 두었으나
    잘못된 관찰이다. 그때 '그림자가 남았다'고 본 어두운 가장자리는 실은 이 검은
    모서리였다. 그림자를 실제로 없애는 것은 3번뿐이다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        apply_menu_shape(self)
        self.setProperty("checkmarks", True)
        self.aboutToShow.connect(self._sync_checkmark_space)

    def _sync_checkmark_space(self):
        """체크 표시를 쓰지 않는 메뉴는 글자 앞자리를 비워 두지 않는다.

        메뉴 항목의 왼쪽 여백은 체크 표시가 들어갈 자리다. 체크할 것이 하나도 없는
        메뉴에서는 그 자리가 그냥 빈칸으로 남아 글이 오른쪽으로 밀려 보인다.

        기본값은 '자리 없음'이고 필요할 때만 넓힌다(QSS의 `QMenu[checkmarks="true"]`).
        그래야 Qt가 직접 만드는 입력칸 우클릭 메뉴처럼 우리 손을 거치지 않는
        메뉴도 빈칸 없이 나온다. 그쪽에도 체크 항목은 없다.

        판단을 항목을 넣을 때가 아니라 열기 직전에 하는 이유는, 항목을 만든 뒤에
        checkable을 켜는 경우가 있어서다. 그때는 넣는 시점에 물어봐야 답이 없다.
        """
        checkmarks = any(action.isCheckable() for action in self.actions())
        if self.property("checkmarks") == checkmarks:
            return
        self.setProperty("checkmarks", checkmarks)
        self.style().unpolish(self)
        self.style().polish(self)


class ElidedLabel(QLabel):
    """폭이 모자라면 말줄임표로 줄여 보여 주는 라벨.

    QLabel은 줄바꿈을 끄면 글자를 그냥 잘라 내서 문장이 어중간하게 끊긴다.
    2열 카드처럼 폭이 바뀌는 자리에서는 매번 폭에 맞춰 다시 줄여야 한다.
    """

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
    """행에 그려지는 초점 사각형을 지운다.

    행을 고르면(정확히는 그 행이 current가 될 때) 스타일이 행 상자를 그대로 두르는
    각진 선을 그린다. 카드는 모서리가 둥글어서 그 선이 카드 밖으로 삐져나오고,
    네 귀퉁이에 사각 자국이 남는다. 고르기 전에는 멀쩡하다가 고른 뒤에만 나타난다.

    **QSS로는 지워지지 않는다.** `::item`에 `outline: none`을 넣어도 그대로 그려지고,
    행 배경색을 투명으로 바꿔도 마찬가지다 — 그리는 것이 배경이 아니라 초점
    사각형이라서다. 실측하면 카드 우상단 대각선에서 목록 배경(242,244,247)이어야 할
    자리가 (213,214,219)로 바뀌고, 이 델리게이트를 끼우면 되돌아온다.

    포커스 정책을 끄는 방법도 있지만 그러면 목록에서 방향키와 Del이 듣지 않는다.
    그리는 순간에만 상태 비트를 떼는 편이 잃는 것이 없다.
    """

    def paint(self, painter, option, index):
        option.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, option, index)


class GridListWidget(QListWidget):
    """항목을 가로로 흘려 여러 열로 감싸는 목록.

    한 열로 세우면 카드 오른쪽이 비어 도는 자리에 쓴다. 폭이 좁아 한 칸이
    min_item_width보다 작아지면 열을 하나씩 줄여 결국 1열로 되돌아간다.
    """

    LAYOUT_SLACK = 2
    """칸 폭 합계가 뷰포트와 딱 맞아떨어지면 Qt가 마지막 칸을 다음 줄로 넘긴다.
    2px만 남겨도 열이 유지되고, 그만큼 오른쪽에 남는 자리도 최소가 된다."""

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
        """한 칸의 폭.

        세로 스크롤바를 늘 띄워 두므로 뷰포트 폭이 항목 수에 따라 변하지 않는다.
        예전처럼 '숨었을 때도 스크롤바 자리를 빼두는' 보정이 필요 없고, 그 자리가
        오른쪽에만 빈 공간으로 남아 좌우 여백이 달라 보이던 문제도 사라진다.
        """
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
    """목록이 비었을 때 그 위에 겹쳐 보이는 안내. 아이콘 하나와 글 두 줄.

    빈 목록은 아무 말도 하지 않는다. 처음 켠 사람에게는 고장 난 것인지 아직
    할 일이 남은 것인지 구별할 단서가 없어서, 세 탭 모두 무엇을 하면 되는지
    한 줄로 알려 준다.

    **목록 안에 항목으로 넣지 않고 뷰포트 위에 겹친다.** 항목으로 넣으면 그것도
    한 줄이라 선택되고 우클릭 메뉴가 뜨고 개수에 잡힌다. 지울 때를 놓치면 카드와
    나란히 남기도 한다. 겹쳐 두면 목록은 비어 있는 그대로다.

    **마우스는 통과시킨다**(`WA_TransparentForMouseEvents`). 뷰포트를 통째로
    덮으므로, 그러지 않으면 빈 목록에서 우클릭이 막히고 창으로 끌어다 놓는
    주소도 이 위젯이 가로챈다.

    보일지 말지는 목록 모델이 알려 주는 대로 따라간다. 항목을 넣고 빼는 곳이
    창 쪽 여러 군데라, 그때마다 갱신을 부르게 하면 언젠가 한 곳을 빠뜨린다.
    """

    ICON_SIZE = 44
    MARGIN = 24
    TEXT_MAX_WIDTH = 320
    """설명 줄의 최대 폭. 창을 넓히면 한 줄이 끝없이 길어져 읽는 눈이 되돌아온다.
    목록이 이보다 좁으면(최소 폭 창의 다운로드 칸) 그 폭에 맞춰 줄인다."""

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

        이 위젯은 자기가 만들지 않은 목록의 모델 신호와 뷰포트 이벤트에 매달려
        있다. 창을 닫으면 그 목록이 먼저 헐리는데 그 와중에도 행이 사라졌다는
        신호는 나오므로, 이미 없어진 쪽을 만지면 RuntimeError가 난다. 슬롯 안에서
        난 예외는 PyQt가 잡지 못하고 그대로 프로세스를 끝낸다.

        `destroyed`만으로는 늦는 경우가 있어 sip 쪽도 함께 본다.
        """
        return (not self._dead and not sip.isdeleted(self)
                and not sip.isdeleted(self._list))

    def apply_theme(self, theme: str):
        """아이콘을 지금 테마의 흐린 글자색으로 다시 그린다.

        글자는 QSS가 맡지만 아이콘 색은 SVG를 그릴 때 정해지므로, 테마가 바뀌면
        여기서 새로 만들어야 한다.
        """
        icon = get_icon(self._icon_name, palette(theme)["text_dim"], self.ICON_SIZE)
        self.icon_label.setPixmap(icon.pixmap(QSize(self.ICON_SIZE, self.ICON_SIZE),
                                              self.devicePixelRatioF()))

    def set_filtered(self, filtered: bool):
        """검색 때문에 빈 것인지 알려 준다.

        기록·즐겨찾기는 검색할 때 목록을 새로 채우므로, 걸리는 것이 없으면 항목
        수가 0이 된다. 그대로 두면 기록이 500개 있는 사람에게 '아직 받은 것이
        없다'고 말하게 된다.
        """
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

        QLabel은 wordWrap을 켜도 sizeHint가 한 줄 높이로 나온다. 가로 가운데
        정렬까지 걸면 레이아웃이 그 값을 그대로 써서, 두 줄로 접힌 글이 한 줄
        높이 상자에 겹쳐 그려진다(실측: 필요 64px에 받은 것은 16px, 폭도
        320이 아니라 160으로 접혔다). 폭을 고정하고 그 폭에서 필요한 높이를
        heightForWidth로 구해 넣어야 두 줄이 온전히 보인다.
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
        """뷰포트가 커지고 줄어드는 대로 따라간다.

        보이는 동안만 따라가게 두면 안 된다. 다른 탭에 있는 목록은 그 탭을 고르기
        전까지 숨어 있고, 배치는 그동안에도 돈다. 그 사이의 크기 변화를 흘려보내면
        탭을 처음 열었을 때 안내가 엉뚱한 자리에 놓인 채로 나타난다.
        """
        if (event.type() == QEvent.Type.Resize and self._usable()
                and obj is self._list.viewport()):
            self._fit()
        return False

    def showEvent(self, event):
        """탭이 열리며 처음 보일 때 자리를 다시 맞춘다.

        숨어 있는 동안 뷰포트가 제 크기를 받지 못했을 수 있다. 그때는 Resize도
        오지 않아 eventFilter만으로는 늦는다.
        """
        self._fit()
        super().showEvent(event)


def rounded_thumbnail(pixmap: QPixmap, width: int, height: int,
                      dpr: float = 1.0, radius: int = 4) -> QPixmap:
    """지정한 크기를 꽉 채우도록 가운데를 잘라내고 모서리를 둥글린다.

    KeepAspectRatio로 맞추면 원본 비율이 다를 때 위아래가 남아 세로가 짧아 보인다.
    KeepAspectRatioByExpanding으로 채운 뒤 잘라야 어떤 원본이든 같은 비율로 보인다.
    """
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

    QThread.finished는 워커 스레드에서 발생한다. 모듈 함수에 그대로 연결하면
    워커 스레드에서 새 QThread를 만들게 된다. 메인 스레드에 사는 QObject를
    수신자로 두면 Qt가 큐 연결로 바꿔 메인 스레드에서 처리한다.
    """

    def on_thread_finished(self):
        """이미 지워진 스레드를 먼저 걷어낸다.

        finished에는 큐 연결이 둘 걸려 있고 deleteLater가 먼저다. 둘 사이에
        순서 보장이 없어, 이 슬롯의 호출이 아직 큐에 남아 있는 동안 C++ 객체가
        먼저 파괴될 수 있다. 그러면 목록에는 껍데기만 남아 isFinished()가
        RuntimeError를 낸다. 슬롯 안에서 난 예외는 PyQt6가 잡지 못해 앱이
        그대로 죽는다.

        sender()만 지우지 않고 전체를 훑는 것은 그대로 둔다. 지워진 항목은
        어느 호출에서 발견하든 목록에서 빠져야 하고, 여기가 유일한 청소처다.
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

    on_loaded는 반드시 QObject의 바운드 메서드여야 한다. 람다를 넘기면 수신자가
    사라져도 Qt가 연결을 끊지 못해, 삭제된 위젯을 건드리며 죽는다.
    """
    if len(_running_thumb_threads) < MAX_CONCURRENT_THUMBS:
        return _spawn_thumb_thread(url, on_loaded)
    _pending_thumbs.append((url, on_loaded))
    return None

class ImagePreviewDialog(QDialog):
    """썸네일을 크게 보여 주는 창. 보기만 한다.

    예전에는 여기서 우클릭해 이미지를 저장할 수 있었다. 그 기능은 목록 우클릭
    메뉴로 옮겼다 — 파일에 관한 일(재생·위치 열기·썸네일 저장)이 한자리에 모여야
    어디서 무엇을 할 수 있는지 외우지 않아도 된다. 이 창은 크게 보는 일만 맡는다.
    """

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
    """카드 왼쪽 가장자리의 4px 세로 색 띠 (UI_REDESIGN.md 3항).

    EPG에서 채널을 구분하는 색 바와 같은 형태이며, 여기서는 상태를 나타낸다.
    진행 중일 때만 은은한 밝기 변화 애니메이션이 돈다. 화면에서 움직이는 요소는
    이것 하나뿐이라, 뭔가 돌아가고 있다는 신호가 한눈에 들어온다.
    """

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
        self.play_btn = self._make_action_button("play", "재생")
        self.folder_btn = self._make_action_button("folder_open", "폴더 열기")
        meta_row.addWidget(self.status_label)
        meta_row.addStretch(1)
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
        set_selected_style((self, self.title_label, self.status_label, self.percent_label), selected)
        self._paint_action_icons()

    def _strip_muted(self, ctx_key: str) -> str:
        return blend(self._colors[ctx_key], self._colors["surface"], 0.55)

    def _refresh_strip(self):
        """상태를 스트립 색으로 옮긴다. 진행 중일 때만 애니메이션이 돈다.

        음성 없음은 실패와 구분한다. 파일은 손에 남았지만 그대로 쓸 수 없는
        상태라, 빨강 대신 경고색으로 '받긴 받았는데 문제가 있다'를 알린다.
        """
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
        """받아 둔 원본 썸네일. 아직 없으면 None.

        카드가 화면에 그리는 것은 모서리를 둥글린 축소본이라, 저장에 쓸 원본을
        따로 내준다.
        """
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

    def update_progress(self, payload: dict):
        if "thumbnail" in payload and payload["thumbnail"] != self._thumb_url:
            self._thumb_url = payload["thumbnail"]
            self._start_thumb_download(self._thumb_url)
        if payload.get("title"):
            self.title_label.setText(payload["title"])
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
    """즐겨찾기 시리즈 카드.

    2열로 깔리므로 폭이 목록 절반이다. 제목은 두 줄까지 접고 URL은 줄여서,
    어떤 폭에서도 카드 높이가 CARD_HEIGHT로 일정하게 유지된다.
    """

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
            cache_path = THUMBNAIL_CACHE_DIR / f"{series_id}.jpg"
            if cache_path.exists(): self._set_thumbnail_pixmap(QPixmap(str(cache_path)))
            else:
                thumb_url = f"https://statics.tver.jp/images/content/thumbnail/series/large/{series_id}.jpg"
                self._cache_path = cache_path
                self.downloader = start_thumbnail_download(thumb_url, self._on_thumb_finished)
        except Exception: pass

    def _on_thumb_finished(self, result: tuple):
        try: url, data = result
        except (TypeError, ValueError): return
        if not data: return
        try: self._cache_path.write_bytes(data)
        except (OSError, AttributeError): pass
        pixmap = QPixmap()
        if pixmap.loadFromData(data): self._set_thumbnail_pixmap(pixmap)

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
            cache_path = THUMBNAIL_CACHE_DIR / f"{episode_id}.jpg"
            if cache_path.exists():
                self._set_thumbnail_pixmap(QPixmap(str(cache_path)))
            else:
                self._cache_path = cache_path
                self.downloader = start_thumbnail_download(episode_thumb_url, self._on_thumb_finished)
        except Exception: pass

    def _on_thumb_finished(self, result: tuple):
        try: url, data = result
        except (TypeError, ValueError): return
        if not data: return
        try: self._cache_path.write_bytes(data)
        except (OSError, AttributeError): pass
        pixmap = QPixmap()
        if pixmap.loadFromData(data): self._set_thumbnail_pixmap(pixmap)

    def _set_thumbnail_pixmap(self, pixmap: QPixmap):
        """썸네일을 안전하게 넣는다. 라벨이 이미 삭제됐을 수 있다."""
        try:
            if self.thumb_label and pixmap and not pixmap.isNull():
                self.thumb_label.setPixmap(rounded_thumbnail(
                    pixmap, LIST_THUMB_W, LIST_THUMB_H, self.devicePixelRatioF()))
        except RuntimeError:
            pass
