from __future__ import annotations
import os
from pathlib import Path
from typing import Optional, Dict

from PyQt6 import sip
from PyQt6.QtCore import (
    Qt, pyqtSignal, QSize, QTimer, QRectF, QEvent,
    QPropertyAnimation, QEasingCurve, pyqtProperty,
)
from PyQt6.QtGui import QPixmap, QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QProgressBar, QDialog,
    QScrollArea, QToolButton, QListWidget, QSizePolicy
)

from src.icons import get_icon
from src.i18n import t
from src.qss import blend, palette
from src.thumbnails import (THUMBNAIL_CACHE_DIR, ThumbnailDownloader,
                            cached_thumbnail, discard_thumbnail_requests,
                            rounded_thumbnail, start_thumbnail_download,
                            write_thumbnail_cache)
from src.utils import (ERROR_STATUSES, FINISHED_STATUSES, NO_AUDIO_STATUS,
                       format_duration, item_percent,
                       STATUS_QUEUED, STATUS_DOWNLOADING,
                       STATUS_CONVERTING, STATUS_DONE)

LIST_THUMB_W, LIST_THUMB_H = 128, 72


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


def set_selected_style(widgets, selected: bool):
    """선택 상태를 QSS가 읽을 수 있는 동적 속성으로 옮기고 다시 칠하게 한다."""
    value = "true" if selected else "false"
    for widget in widgets:
        if widget.property("selected") == value:
            continue
        widget.setProperty("selected", value)
        widget.style().unpolish(widget)
        widget.style().polish(widget)


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
        self.setWindowTitle(t("card.preview_title")); self.setMinimumSize(640, 360); self.setModal(True)
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


class HoverTintButton(QToolButton):
    """마우스를 올리면 아이콘이 강조색으로 바뀌어, 누를 수 있다는 것을 눈으로 보여준다.

    QSS의 :hover는 배경만 바꿀 수 있다 - 아이콘은 SVG를 이미 고정된 색으로 칠해
    QIcon으로 굳혀 둔 것이라, 색을 바꾸려면 enter/leave에서 다시 그려야 한다.
    """

    def __init__(self, icon_name: str, tooltip: str, parent=None):
        super().__init__(parent, objectName="CardActionButton", toolTip=tooltip)
        self.setFixedSize(28, 28)
        self.setIconSize(QSize(16, 16))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._icon_name = icon_name
        self._base_color = "#000000"
        self._hover_color = "#000000"

    def set_colors(self, base_color: str, hover_color: str):
        self._base_color = base_color
        self._hover_color = hover_color
        self.setIcon(get_icon(self._icon_name, base_color, 16))

    def enterEvent(self, event):
        super().enterEvent(event)
        self.setIcon(get_icon(self._icon_name, self._hover_color, 16))

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.setIcon(get_icon(self._icon_name, self._base_color, 16))


def _status_label(status: str) -> str:
    """상태 코드를 지금 언어의 표시 문구로 바꾼다. 상태 코드 자체가 lang/*.ini의
    [status] 섹션 키(queued, done, no_audio 등)와 그대로 맞아떨어진다."""
    return t(f"status.{status}")


class ThumbnailCard(QWidget):
    """썸네일 한 장을 받아 카드에 얹는 일만 맡는 기반. 세 카드가 이 부분만 똑같았다.

    받아 온 주소를 걸어 둔 주소와 견주는 검사도 여기 둔다 - 셋 중 하나만 그것을
    갖고 있으면 어느 카드가 어긋날 수 있는지 고칠 때마다 다시 따져 봐야 한다.
    카드마다 다른 것은 그림 크기와 모서리, 그리고 원본을 남길지 여부뿐이다.
    """

    THUMB_SIZE = (LIST_THUMB_W, LIST_THUMB_H)
    THUMB_CORNER = 4

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url
        self._thumb_url: Optional[str] = None
        self._cache_path: Optional[Path] = None
        self._thumb_downloader: Optional[ThumbnailDownloader] = None

    def load_thumbnail(self, url: str, cache_key: str = ""):
        """캐시에 있으면 그것을 얹고, 없으면 받아 온다. 주소를 걸어 두는 곳도 여기다.

        주소가 비어도 걸어 둔 것은 지운다 - 남겨 두면 앞선 요청이 뒤늦게 돌아왔을 때
        이미 갈아탄 카드에 옛 그림이 붙는다.
        """
        self._thumb_url = url or None
        if not url:
            return
        if cache_key:
            self._cache_path = THUMBNAIL_CACHE_DIR / f"{cache_key}.jpg"
            cached = cached_thumbnail(self._cache_path)
            if cached is not None:
                self._apply_thumbnail(cached)
                return
        self._thumb_downloader = start_thumbnail_download(url, self._on_thumb_finished)

    def _url_tail(self) -> str:
        """주소 끝 토막. 캐시 이름과 시리즈 판별이 이것으로 갈린다.

        주소가 문자열이 아닌 경우를 여기서만 막는다 - 예전에 두 카드가 이 자리를 통째로
        `except Exception`으로 감쌌는데, 실측으로 훑어보니 실제로 나던 것이 그 하나였다.
        """
        if not isinstance(self.url, str):
            return ""
        return self.url.strip('/').split('/')[-1]

    def cleanup(self):
        """목록에서 빠지기 전에 썸네일 요청과 콜백을 끊는다. 지워진 라벨을 건드리면 앱이 죽는다."""
        discard_thumbnail_requests(self)
        downloader = self._thumb_downloader
        self._thumb_downloader = None
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
        try:
            url, data = result
        except (TypeError, ValueError):
            return
        if url != self._thumb_url or not data:
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            return
        write_thumbnail_cache(self._cache_path, data)
        self._apply_thumbnail(pixmap)

    def _apply_thumbnail(self, pixmap: QPixmap):
        """모서리를 둥글려 라벨에 얹는다. 라벨이 이미 헐렸을 수 있다."""
        if pixmap is None or pixmap.isNull():
            return
        width, height = self.THUMB_SIZE
        try:
            self.thumb_label.setPixmap(rounded_thumbnail(
                pixmap, width, height, self.devicePixelRatioF(), self.THUMB_CORNER))
        except RuntimeError:
            pass


class DownloadItemWidget(ThumbnailCard):
    play_requested = pyqtSignal(str)
    open_folder_requested = pyqtSignal(str)

    PROGRESS_ANIM_MS = 240
    THUMB_SIZE = (THUMB_W, THUMB_H)
    THUMB_CORNER = THUMB_RADIUS

    def __init__(self, url: str, theme: str = "light", parent=None):
        super().__init__(url, parent)
        self.setObjectName("DownloadItem")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.status: str = STATUS_QUEUED
        self.final_filepath: Optional[str] = None
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

        self.title_label = QLabel(t("card.title_loading"), objectName="Title", wordWrap=True)

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
        self.status_label = QLabel(_status_label(STATUS_QUEUED), objectName="Status")
        self.duration_label = QLabel("", objectName="Duration")
        self.duration_label.hide()
        self.play_btn = self._make_action_button("play", t("card.play_tooltip"))
        self.folder_btn = self._make_action_button("folder_open", t("card.folder_open_tooltip"))
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

    def _make_action_button(self, icon_name: str, tooltip: str) -> HoverTintButton:
        return HoverTintButton(icon_name, tooltip, self)

    def apply_theme(self, theme: str):
        """테마 전환 시 스트립 색과 액션 아이콘을 다시 칠한다."""
        self._colors = palette(theme)
        self._paint_action_icons()
        self._refresh_strip()

    def _paint_action_icons(self):
        """평소엔 본문 색, 마우스를 올리면 재생은 초록·폴더는 노랑으로 바뀐다.

        누를 수 있는 두 아이콘의 성격이 달라(하나는 재생, 하나는 탐색기 열기) 강조색도
        갈랐다 - 정보 창 왼쪽 단추 셋과 같은 hover_* 토큰을 그대로 쓴다.
        """
        color = self._colors["text" if self._selected else "text_dim"]
        self.play_btn.set_colors(color, self._colors["hover_green"])
        self.folder_btn.set_colors(color, self._colors["hover_yellow"])

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
        elif self.status == STATUS_DONE:
            self.strip.set_state(QColor(self._strip_muted("ctx_download")), False)
        elif self.status == STATUS_QUEUED:
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
        self.status = STATUS_QUEUED
        self.final_filepath = None
        self._progress_anim.stop()
        self.progress.setValue(0)
        self.percent_label.setText("0%")
        if self.progress.property("state") != "active":
            self.progress.setProperty("state", "active")
            self.progress.style().unpolish(self.progress)
            self.progress.style().polish(self.progress)
        self.status_label.setText(_status_label(STATUS_QUEUED))
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
            self.load_thumbnail(payload["thumbnail"] or "")
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
            if self.status == STATUS_DOWNLOADING:
                speed = payload.get("speed", "")
                eta = payload.get("eta", "")
                detail = (t("status.downloading_detail", speed=speed, eta=eta)
                          if speed and eta else t("status.downloading_ellipsis"))
                status_text = (t("status.downloading_with_component", component=component, detail=detail)
                               if component else t("status.downloading", detail=detail))
            elif self.status == STATUS_CONVERTING:
                status_text = t("status.converting", codec=payload.get("codec", ""))
            else:
                status_text = _status_label(self.status)
            self.status_label.setText(status_text)

            state_prop = "active"
            if self.status == STATUS_DONE:
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
        super().cleanup()

    def _apply_thumbnail(self, pixmap: QPixmap):
        """원본을 따로 든다. 눌러 크게 볼 때와 저장할 때 쓰는 것이 축소본이 아니라 이 그림이다."""
        self._orig_thumb_pm = pixmap
        super()._apply_thumbnail(pixmap)


class FavoriteItemWidget(ThumbnailCard):
    """즐겨찾기 시리즈 카드. 2열이라 폭이 절반이고, 제목·URL을 줄여 높이를 붙든다."""

    CARD_HEIGHT = 112
    TITLE_LINES = 2
    TITLE_PADDING = 4
    THUMB_URL = "https://statics.tver.jp/images/content/thumbnail/series/large/{series_id}.jpg"

    def __init__(self, url: str, meta: Dict[str, str], theme: str = "light", parent=None):
        super().__init__(url, parent)
        self.setObjectName("FavoriteItem"); self.meta = meta
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._colors = palette(theme)
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 12, 0); root.setSpacing(0)
        self.strip = BroadcastStrip(self)
        root.addWidget(self.strip)
        body = QHBoxLayout(); body.setContentsMargins(12, 10, 0, 10); body.setSpacing(12)
        self.thumb_label = QLabel(objectName="Thumb", alignment=Qt.AlignmentFlag.AlignCenter); self.thumb_label.setFixedSize(LIST_THUMB_W, LIST_THUMB_H); body.addWidget(self.thumb_label)

        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0); info_layout.setSpacing(4)

        title_text = self.meta.get("title") or t("card.title_checking")
        self.title_label = QLabel(title_text); self.title_label.setObjectName("Title")
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.title_label.setFixedHeight(
            self.title_label.fontMetrics().lineSpacing() * self.TITLE_LINES
            + self.TITLE_PADDING)

        self.url_label = ElidedLabel(self.url); self.url_label.setObjectName("PaneSubtitle")

        self.last_check_label = QLabel(t("card.last_check", date=self.meta.get('last_check') or '-')); self.last_check_label.setObjectName("PaneSubtitle")

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
        """시리즈 표지는 주소를 따로 받지 않고 시리즈 id에서 규칙으로 만든다."""
        series_id = self._url_tail()
        if not series_id.startswith('sr'):
            return
        self.load_thumbnail(self.THUMB_URL.format(series_id=series_id), series_id)


class HistoryItemWidget(ThumbnailCard):
    def __init__(self, url: str, meta: Dict[str, str], theme: str = "light", parent=None):
        super().__init__(url, parent)
        self.setObjectName("HistoryItem"); self.meta = meta
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
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
        self.title_label = QLabel(self.meta.get("title") or t("card.title_missing"), objectName="Title"); self.title_label.setWordWrap(True)
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
        """회차 표지 주소는 기록에 적혀 있다. 캐시 이름은 회차 id로 짓는다."""
        self.load_thumbnail(self.meta.get("thumbnail_url") or "", self._url_tail())
