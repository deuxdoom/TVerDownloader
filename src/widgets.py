# -*- coding: utf-8 -*-
# 다운로드 아이템 위젯
# - 썸네일: 원본/축소본 분리 저장, 클릭 시 원본 팝업
# - 진행바: 상태별 색(active/done/error), 오른쪽 끝에 상태 아이콘을 "오버레이" 고정
# - 아이콘: base64 PNG 우선, 실패 시 벡터 폴백
# - 썸네일 QThread 참조 유지(크래시 방지)

from __future__ import annotations

import os
import re
import urllib.request
from typing import Optional, Dict

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QSize
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QPainterPath, QGuiApplication
from PyQt6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QProgressBar, QDialog,
    QScrollArea, QSizePolicy
)

# ───────── base64 아이콘(원하면 교체 가능) ─────────
CHECK_ICON_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAABvElEQVRYhe2Wv0sUURTHf3fL"
    "oEJQy1K0hQm2bQ6oQJq2SBSwLw2m1gIG1u2QJQFq1aQ7UQeDg0TFv8Hjv7x0m3Yc9a2lP3Jw"
    "4/3vnvOe93y9j3J8m8wGB5Cz+5E8O3b3tF1oQv0lN3aZV8hY1y3z1uYqS8H2CwA2wK3o8b4M"
    "yQb3Q8r1K0b8c8qE3h1l9tI9vVhV6kYqkR6vB2g9QHcJpQ9B7kRkqvYmQj0H3u7o9jv2y4nC"
    "3v0q0cQ9qV7cFh5m9dCzNwW5Lkqz2sP3q6Q4Cj+0sZ5m8m4j8qD8z8F2k3a2q0f0iJm6b+qR"
    "lY0i9g8m8f0p7WZ2p1j7pV9c8lqU8y2U0m4Yf0I7n3m8r2K8kOkqgGJ8n5QqX5WQkW7m9n8M"
    "nq8b0a3m4qQ8o2l8u1U9C1Z7U2b7m7b6nq3o0V8b1O8m1n8bAQy7Jv0GJtXcLw7h7b9s8b9f"
    "Vb1m0Wg0v2c7f9o4Dgk2kQwqVb0KxE2b4i0QbG6P6pQvBzjEw6y0K7Q/8mY6D8k5O6oZ7KQw"
    "9F2e9CkQv3Yp0Yw6XQy1cfm5QAAAABJRU5ErkJggg=="
)
CROSS_ICON_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAABkElEQVRYhe2Wv0sUQRTHf7dK"
    "KpQmIVpJqkFtyqQ0QbBZYrW0UQmBBH8G2bFKQbZJmQmEq2P8Hjv7z0mHdeVbRr+fM7M3d+7z"
    "fYbD0Qm4QX7wJ0s3bXqk1YI/0kq7aZb8h01w7z1qYqS8H2CwA2wK3o8b4MyQb3Q8r1K0b8c8"
    "qE3h1l9tI9vVhV6kYqkR6vB2g9QHcJpQ9B7kRkqvYmQj0H3u7o9jv2y4nC3v0q0cQ9qV7cFh"
    "5m9dCzNwW5Lkqz2sP3q6Q4Cj+0sZ5m8m4j8qD8z8F2k3a2q0f0iJm6b+qRlY0i9g8m8f0p7W"
    "Z2p1j7pV9c8lqU8y2U0m4Yf0I7n3m8r2K8kOkqgGJ8n5QqX5WQkW7m9n8Mnq8b0a3m4qQ8o2"
    "l8u1U9C1Z7U2b7m7b6nq3o0V8b1O8m1n8bAQy7Jv0GJtXcLw7h7b9s8b9fVb1m0Wg0v2c7f9"
    "o4Dgk2kQwqVb0KxE2b4i0QbG6P6pQvBzjEw6y0K7Q/8mY6D8k5O6oZ7KQw9F2e9CkQv3Yp0Y"
    "w6XQy1cfm5QAAAABJRU5ErkJggg=="
)

# ───────── 썸네일 다운로더 ─────────
class ThumbnailDownloader(QThread):
    finished = pyqtSignal(object)  # (url: str, data: bytes|None)

    def __init__(self, url: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            with urllib.request.urlopen(self.url, timeout=10) as r:
                data = r.read()
        except Exception:
            data = None
        self.finished.emit((self.url, data))


# ───────── 썸네일 팝업 ─────────
class ImagePreviewDialog(QDialog):
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle("썸네일 미리보기")
        self.resize(980, 620)
        self.setModal(True)

        area = QScrollArea(self); area.setWidgetResizable(True)
        container = QWidget()
        v = QVBoxLayout(container); v.setContentsMargins(0, 0, 0, 0)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setPixmap(pixmap)
        v.addWidget(self.image_label)

        area.setWidget(container)
        layout = QVBoxLayout(self); layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(area)

    def set_pixmap(self, pm: QPixmap):
        self.image_label.setPixmap(pm)


# ───────── 아이콘 유틸 ─────────
def _pixmap_from_b64(b64: str, target_px: int) -> QPixmap:
    """base64 → QPixmap. 실패 시 null 반환. 고DPI 스케일 고려."""
    try:
        if not b64:
            return QPixmap()
        s = b64.strip(); rem = len(s) % 4
        if rem: s += "=" * (4 - rem)
        import base64 as _b64
        raw = _b64.b64decode(s, validate=False)
        img = QImage.fromData(raw, "PNG")
        if img.isNull():
            return QPixmap()
        pm = QPixmap.fromImage(img)
        ratio = QGuiApplication.primaryScreen().devicePixelRatio() if QGuiApplication.primaryScreen() else 1.0
        size = int(target_px * ratio)
        pm = pm.scaled(QSize(size, size), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        pm.setDevicePixelRatio(ratio)
        return pm
    except Exception:
        return QPixmap()

def _draw_check(size: int = 20, color: str = "#22C55E") -> QPixmap:
    pm = QPixmap(size, size); pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color)); pen.setWidthF(max(2.0, size * 0.12))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap); pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    path = QPainterPath(); path.moveTo(size*0.20, size*0.55); path.lineTo(size*0.45, size*0.80); path.lineTo(size*0.82, size*0.25)
    p.drawPath(path); p.end(); return pm

def _draw_cross(size: int = 20, color: str = "#EF4444") -> QPixmap:
    pm = QPixmap(size, size); pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color)); pen.setWidthF(max(2.0, size * 0.12))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap); pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawLine(int(size*0.25), int(size*0.25), int(size*0.75), int(size*0.75))
    p.drawLine(int(size*0.75), int(size*0.25), int(size*0.25), int(size*0.75))
    p.end(); return pm


# ───────── 아이템 위젯 ─────────
class DownloadItemWidget(QWidget):
    play_requested = pyqtSignal(str)  # filepath

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.status: str = "대기"
        self.final_filepath: Optional[str] = None
        self._last_seen_output: Optional[str] = None
        self._thumb_url: Optional[str] = None
        self._thumb_threads: Dict[str, ThumbnailDownloader] = {}
        self._orig_thumb_pm: Optional[QPixmap] = None  # 팝업용 원본

        # 레이아웃
        self.setObjectName("DownloadItem")
        root = QHBoxLayout(self); root.setContentsMargins(12, 10, 12, 10); root.setSpacing(12)

        # 썸네일
        self.thumb_label = QLabel(); self.thumb_label.setFixedSize(180, 102)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setObjectName("Thumb")
        self.thumb_label.setPixmap(QPixmap(180, 102))
        self.thumb_label.mousePressEvent = self._on_thumb_clicked  # type: ignore
        root.addWidget(self.thumb_label, 0, Qt.AlignmentFlag.AlignVCenter)

        # 본문(센터)
        center_widget = QWidget(); center = QVBoxLayout(center_widget)
        center.setContentsMargins(0,0,0,0); center.setSpacing(6)

        self.title_label = QLabel("제목 로딩 중…"); self.title_label.setObjectName("Title"); self.title_label.setWordWrap(True)

        # 상태 라인(텍스트만)
        info_row = QHBoxLayout(); info_row.setContentsMargins(0,0,0,0); info_row.setSpacing(8)
        self.status_label = QLabel("대기"); self.status_label.setObjectName("Status")
        info_row.addWidget(self.status_label); info_row.addStretch(1)

        # 진행바 컨테이너(오버레이용)
        self.progress_container = QWidget()
        pc_layout = QVBoxLayout(self.progress_container); pc_layout.setContentsMargins(0,0,0,0); pc_layout.setSpacing(0)

        self.progress = QProgressBar(); self.progress.setRange(0,100); self.progress.setValue(0)
        self.progress.setTextVisible(False); self.progress.setObjectName("Progress")
        self.progress.setProperty("state", "active"); self.progress.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.progress.setMinimumHeight(14)
        pc_layout.addWidget(self.progress)

        # 상태 아이콘(오버레이: 진행바 오른쪽 끝)
        self.status_icon = QLabel(self.progress_container)
        self.status_icon.setFixedSize(20, 20); self.status_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.status_icon.hide()

        # 조립
        center.addWidget(self.title_label)
        center.addLayout(info_row)
        center.addWidget(self.progress_container)
        root.addWidget(center_widget, 1, Qt.AlignmentFlag.AlignVCenter)

    # 진행바 리사이즈 시 아이콘 위치 갱신
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place_status_icon()

    def _place_status_icon(self):
        if not self.status_icon.isVisible():
            return
        r = self.progress.geometry()  # progress_container 좌표계
        x = r.right() - self.status_icon.width() - 6
        y = int(r.center().y() - self.status_icon.height() / 2)
        self.status_icon.move(x, y)

    # ---------- 더블클릭: 완료 파일 재생 ----------
    def mouseDoubleClickEvent(self, e):
        if self.final_filepath and os.path.isfile(self.final_filepath) and (self.status_label.text() == "완료" or self.status == "완료"):
            self.play_requested.emit(self.final_filepath)

    # ---------- 썸네일 클릭: 팝업 ----------
    def _on_thumb_clicked(self, ev):
        pm = self._orig_thumb_pm or self.thumb_label.pixmap()
        if pm:
            ImagePreviewDialog(pm, self).exec()

    # ---------- 아이콘/상태 ----------
    def _show_icon(self, kind: Optional[str]):
        """kind: 'check' | 'cross' | None"""
        if not kind:
            self.status_icon.hide()
            return
        px = self.status_icon.height()
        if kind == "check":
            pm = _pixmap_from_b64(CHECK_ICON_B64, px)
            if pm.isNull(): pm = _draw_check(px)
        else:
            pm = _pixmap_from_b64(CROSS_ICON_B64, px)
            if pm.isNull(): pm = _draw_cross(px)
        self.status_icon.setPixmap(pm)
        self.status_icon.show()
        self._place_status_icon()

    # ---------- 진행 업데이트 ----------
    def update_progress(self, payload: dict):
        title = payload.get("title")
        if title: self.title_label.setText(title)

        thumb = payload.get("thumbnail")
        if thumb and thumb != self._thumb_url:
            self._thumb_url = thumb
            self._start_thumb_download(thumb)

        log = payload.get("log") or ""
        if log:
            m = re.search(r"Destination:\s+(.*)$", log)
            if m: self._last_seen_output = m.group(1).strip().strip('"')
            m2 = re.search(r'Merging formats.*?"(.+?)"', log, re.IGNORECASE)
            if m2: self._last_seen_output = m2.group(1).strip()

        if "percent" in payload:
            try:
                v = max(0, min(100, float(payload["percent"])))
                self.progress.setValue(int(v))
            except Exception:
                pass
        if "progress" in payload:
            try:
                self.progress.setValue(int(payload["progress"]))
            except Exception:
                pass

        if "status" in payload:
            self.status = str(payload["status"]); self.status_label.setText(self.status)
            if self.status == "완료":
                if not self.final_filepath and self._last_seen_output: self.final_filepath = self._last_seen_output
                self.progress.setValue(100)
                self.progress.setProperty("state", "done"); self._repolish(self.progress)
                self._show_icon("check")
            elif self.status in ("오류", "취소", "중단", "실패"):
                self.progress.setProperty("state", "error"); self._repolish(self.progress)
                self._show_icon("cross")
            else:
                self.progress.setProperty("state", "active"); self._repolish(self.progress)
                self._show_icon(None)

    @staticmethod
    def _repolish(w: QWidget):
        s = w.style()
        try:
            s.unpolish(w); s.polish(w)
        except Exception:
            pass
        w.update()

    # ---------- 썸네일 다운로드 ----------
    def _start_thumb_download(self, url: str):
        if url in self._thumb_threads:
            th = self._thumb_threads[url]
            if th.isRunning(): return

        th = ThumbnailDownloader(url, parent=self); self._thumb_threads[url] = th

        def _on_finished(payload_obj: object):
            try:
                u, data = payload_obj
            except Exception:
                u, data = url, None

            t = self._thumb_threads.pop(u, None)
            if t is not None: t.deleteLater()

            if u != self._thumb_url or not data: return
            img = QImage.fromData(data)
            if img.isNull(): return

            self._orig_thumb_pm = QPixmap.fromImage(img)  # 원본 저장
            pm_small = self._orig_thumb_pm.scaled(
                self.thumb_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.thumb_label.setPixmap(pm_small)

        th.finished.connect(_on_finished)
        th.start()
