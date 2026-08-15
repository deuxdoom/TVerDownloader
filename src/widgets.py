from __future__ import annotations
import os
import urllib.request
from typing import Optional, Dict
from pathlib import Path

from collections import deque

from PyQt6 import sip
from PyQt6.QtCore import (
    QObject, Qt, QThread, pyqtSignal, QSize, QTimer, QRectF,
    QPropertyAnimation, QEasingCurve, pyqtProperty,
)
from PyQt6.QtGui import QPixmap, QAction, QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QProgressBar, QDialog,
    QScrollArea, QMenu, QFileDialog, QToolButton, QListWidget, QListView,
    QSizePolicy
)

from src.icons import get_icon
from src.qss import blend, palette
from src.utils import ERROR_STATUSES, FINISHED_STATUSES, NO_AUDIO_STATUS

THUMBNAIL_CACHE_DIR = Path("thumbnails")

LIST_THUMB_W, LIST_THUMB_H = 128, 72


class RoundedMenu(QMenu):
    """모서리가 둥글게 보이는 메뉴.

    QSS의 border-radius만으로는 둥글어지지 않는다. 메뉴는 자기 창을 가진 팝업이라
    모서리 바깥을 창 배경색이 그대로 채우고, 둥근 테두리만 그 위에 얹혀 네 귀퉁이가
    각진 채로 남는다. 창 배경을 투명으로 만들어야 QSS가 그린 모양이 곧 창 모양이 된다.

    창 종류(FramelessWindowHint)는 건드리지 않는다. NoDropShadowWindowHint까지 붙이면
    모서리는 둥글어지지만 Windows가 그려 주던 그림자가 사라져 메뉴가 배경에 붙어
    보인다. 투명 배경만 켜면 그림자는 그대로 남는다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)


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
        for thread in list(_running_thumb_threads):
            if thread.isFinished():
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
        elif event.button() == Qt.MouseButton.RightButton: self._show_context_menu(event.pos())
    def _show_context_menu(self, position):
        menu = QMenu(self); save_action = QAction("이미지 저장", self)
        save_action.triggered.connect(self._save_image); menu.addAction(save_action)
        global_position = self.image_label.mapToGlobal(position); menu.exec(global_position)
    def _save_image(self):
        if not self._original_pixmap or self._original_pixmap.isNull(): return
        file_path, _ = QFileDialog.getSaveFileName(self, "이미지 저장", "thumbnail.png", "Image Files (*.png *.jpg *.jpeg)")
        if file_path: self._original_pixmap.save(file_path)

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
        percent = payload.get("percent", self.progress.value())
        if component == "비디오":
            progress_value = int(percent / 2)
        elif component == "오디오":
            progress_value = 50 + int(percent / 2)
        else:
            progress_value = self.progress.value()
        self._animate_progress(progress_value)

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
