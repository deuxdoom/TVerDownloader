# src/widgets.py
# FIX: Add checks in _set_thumbnail_pixmap for FavoriteItemWidget
#      and HistoryItemWidget to prevent RuntimeError when label is deleted.

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
from PyQt6.QtGui import QPixmap, QImage, QAction, QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QProgressBar, QDialog,
    QScrollArea, QSizePolicy, QMenu, QFileDialog, QToolButton
)

from src.icons import get_icon
from src.qss import blend, palette
from src.utils import ERROR_STATUSES

THUMBNAIL_CACHE_DIR = Path("thumbnails")

# 목록(기록·즐겨찾기)용 썸네일 크기. 다운로드 카드와 같은 16:9다.
LIST_THUMB_W, LIST_THUMB_H = 128, 72


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

# 실행 중인 썸네일 스레드를 붙잡아 둔다. 위젯이 사라져도 스레드는 스스로 끝나야 한다.
_running_thumb_threads: set = set()
# 대기 중인 요청. 기록 목록은 최대 100개를 표시하고 다운로드가 끝날 때마다 통째로
# 다시 그리므로, 제한이 없으면 스레드가 수백 개까지 쌓인다.
_pending_thumbs: deque = deque()
MAX_CONCURRENT_THUMBS = 6


class ThumbnailDownloader(QThread):
    # QThread에는 이미 finished 시그널이 있다. 같은 이름을 쓰면 Qt가 스레드 종료를
    # 알리는 신호를 가려 버려 정리 로직이 동작하지 않는다.
    loaded = pyqtSignal(object)

    def __init__(self, url: str):
        # 부모를 두지 않는다. 위젯을 부모로 삼으면 목록을 갱신할 때 실행 중인
        # 스레드가 함께 삭제돼 "Destroyed while thread is still running"으로 죽는다.
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
        # 위젯 생성 시점(메인 스레드)에 처음 만들어진다.
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
        # 대기하는 사이 위젯이 사라졌으면 건너뛴다. 삭제된 객체를 부르면 죽는다.
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
THUMB_W, THUMB_H = 160, 90   # 16:9 고정
THUMB_RADIUS = 4


class BroadcastStrip(QWidget):
    """카드 왼쪽 가장자리의 4px 세로 색 띠 (UI_REDESIGN.md 3항).

    EPG에서 채널을 구분하는 색 바와 같은 형태이며, 여기서는 상태를 나타낸다.
    진행 중일 때만 은은한 밝기 변화 애니메이션이 돈다. 화면에서 움직이는 요소는
    이것 하나뿐이라, 뭔가 돌아가고 있다는 신호가 한눈에 들어온다.
    """

    PULSE_MS = 1600
    PULSE_LIGHTEN = 35   # 최대 밝기 상승폭(%). 색상은 두고 밝기만 건드린다.

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(STRIP_WIDTH)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._color = QColor("#DDE3EA")
        self._glow = 0.0
        # 애니메이션을 이 위젯의 자식으로 둔다. 카드가 삭제되면 Qt가 함께 정리한다.
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
        # 이 속성이 없으면 QSS의 background/border/border-radius가 무시돼
        # 카드가 투명해지고, 선택 시 행 전체가 원색으로 덮인다.
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
        root.setContentsMargins(0, 0, 12, 0)   # 스트립은 카드 왼쪽 끝에 붙어야 한다
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

        # 진행률이 튀지 않도록 값 자체를 보간한다.
        self._progress_anim = QPropertyAnimation(self.progress, b"value", self)
        self._progress_anim.setDuration(self.PROGRESS_ANIM_MS)
        self._progress_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.play_btn.clicked.connect(self._emit_play)
        self.folder_btn.clicked.connect(self._emit_open_folder)
        self._set_actions_visible(False)
        self.apply_theme(theme)

    # ── 구성 ──────────────────────────────────────────────────────────────
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
        # 선택된 행은 강조 배경 위에 놓이므로 흐린 색으로는 읽히지 않는다.
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

    # ── 편성 스트립 ───────────────────────────────────────────────────────
    def _strip_muted(self, ctx_key: str) -> str:
        return blend(self._colors[ctx_key], self._colors["surface"], 0.55)

    def _refresh_strip(self):
        """상태를 스트립 색으로 옮긴다. 진행 중일 때만 애니메이션이 돈다."""
        if self.status in ERROR_STATUSES:
            self.strip.set_state(QColor(self._colors["danger"]), False)
        elif self.status == "완료":
            # 색 계열은 유지한 채 채도만 낮춘다. 다른 색으로 바꾸면 진행 중이던
            # 항목이 끝나는 순간 띠 색이 튀어 보인다.
            self.strip.set_state(QColor(self._strip_muted("ctx_download")), False)
        elif self.status == "대기":
            self.strip.set_state(QColor(self._colors["border"]), False)
        else:
            # 진행 중은 진행률 바와 같은 색을 쓴다. accent를 쓰면 선택 하이라이트에
            # 묻혀 스트립도 진행률 바도 보이지 않는다.
            self.strip.set_state(QColor(self._colors["ctx_download"]), True)

    # ── 액션 버튼 ─────────────────────────────────────────────────────────
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
        if self.status == "완료" and self._has_file():
            self.play_requested.emit(self.final_filepath)
        super().mouseDoubleClickEvent(event)

    def _on_thumb_clicked(self, event):
        if self._orig_thumb_pm and not self._orig_thumb_pm.isNull():
            ImagePreviewDialog(self._orig_thumb_pm, self).exec()

    # ── 진행률 ────────────────────────────────────────────────────────────
    def _animate_progress(self, target: int):
        target = max(0, min(100, int(target)))
        self._progress_anim.stop()
        current = self.progress.value()
        if target == current:
            return
        if target < current:
            # 재시도로 되감기는 경우는 즉시 반영한다. 거꾸로 흐르는 막대는 오해를 부른다.
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
            elif self.status in ERROR_STATUSES:
                state_prop = "error"
            if self.progress.property("state") != state_prop:
                self.progress.setProperty("state", state_prop)
                self.progress.style().unpolish(self.progress)
                self.progress.style().polish(self.progress)

            # 완료 시 재생/폴더 열기를 상시 노출한다. 예전에는 더블클릭뿐이라
            # 재생이 된다는 사실 자체를 알 방법이 없었다.
            self._set_actions_visible(self.status == "완료" and self._has_file())
            self._refresh_strip()
        self.update()

    # ── 정리 ──────────────────────────────────────────────────────────────
    def cleanup(self):
        """목록에서 제거되기 전에 애니메이션과 콜백을 확실히 끊는다."""
        self.strip.stop_pulse()
        self._progress_anim.stop()
        downloader = self._thumb_downloader
        self._thumb_downloader = None
        # 스레드가 이미 끝났으면 deleteLater로 C++ 객체가 사라진 뒤다.
        # 남은 파이썬 껍데기를 건드리면 RuntimeError로 프로세스가 죽는다.
        if downloader is None or sip.isdeleted(downloader):
            return
        try:
            downloader.loaded.disconnect(self._on_thumb_finished)
        except (TypeError, RuntimeError):
            pass   # 이미 끊겼거나 그 사이 삭제됐다

    # ── 썸네일 ────────────────────────────────────────────────────────────
    def _start_thumb_download(self, url: str):
        # 이전 스레드를 terminate()로 죽이지 않는다. SSL 처리 도중 강제 종료하면
        # 프로세스가 통째로 날아간다. 뒤늦게 온 결과는 아래 URL 비교로 걸러진다.
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
            pass   # 위젯이 이미 삭제된 경우

class FavoriteItemWidget(QWidget):
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

        self.url_label = QLabel(self.url); self.url_label.setObjectName("PaneSubtitle")
        self.url_label.setWordWrap(True)

        self.last_check_label = QLabel(f"마지막 확인: {self.meta.get('last_check', '-')}"); self.last_check_label.setObjectName("PaneSubtitle")

        info_layout.addWidget(self.title_label)
        info_layout.addWidget(self.url_label)
        info_layout.addWidget(self.last_check_label)
        info_layout.addStretch(1); body.addLayout(info_layout, 1)
        root.addLayout(body, 1)

        self.apply_theme(theme)
        self._load_or_download_thumbnail()

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

    # --- [수정된 부분 시작] ---
    def _set_thumbnail_pixmap(self, pixmap: QPixmap):
        """썸네일을 안전하게 넣는다. 라벨이 이미 삭제됐을 수 있다."""
        try:
            if self.thumb_label and pixmap and not pixmap.isNull():
                self.thumb_label.setPixmap(rounded_thumbnail(
                    pixmap, LIST_THUMB_W, LIST_THUMB_H, self.devicePixelRatioF()))
        except RuntimeError:
            pass
    # --- [수정된 부분 끝] ---

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