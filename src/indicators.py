"""체크 표시, 라디오 점, 스핀박스 화살표를 그려 임시 PNG로 내보낸다.

앱에 스타일시트가 걸리면 Qt는 QStyleSheetStyle로 넘어가고, 표시기(subcontrol)의
네이티브 그리기를 멈춘다. 그래서 QSS에서 배경만 칠하면 체크 표시가 사라진
녹색 사각형이 되고, 스핀박스 버튼은 화살표 없는 빈 칸이 된다.
모양을 직접 그려 `image:` 로 넣어 주는 것이 유일하게 확실한 방법이다.

QSS의 url()은 파일 경로만 받으므로 프로세스 임시 폴더에 써 두고 경로를 넘긴다.
고해상도 화면을 위해 1x와 @2x를 함께 만든다.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap

BOX = 15
ARROW_W, ARROW_H = 11, 7

_dir: Path | None = None
_cache: Dict[str, Dict[str, str]] = {}


def _out_dir() -> Path:
    global _dir
    if _dir is None:
        _dir = Path(tempfile.mkdtemp(prefix="tverdl_ind_"))
    return _dir


def _canvas(width: int, height: int, scale: int) -> QPixmap:
    pixmap = QPixmap(width * scale, height * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    return pixmap


def _draw_check(scale: int, color: str) -> QPixmap:
    pixmap = _canvas(BOX, BOX, scale)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(2.6 * scale)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    s = scale
    painter.drawPolyline(
        QPointF(3.2 * s, 7.9 * s), QPointF(6.2 * s, 11.0 * s), QPointF(12.0 * s, 4.2 * s)
    )
    painter.end()
    return pixmap


def _draw_dot(scale: int, color: str) -> QPixmap:
    pixmap = _canvas(BOX, BOX, scale)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    r = 3.0 * scale
    center = QPointF(BOX * scale / 2, BOX * scale / 2)
    painter.drawEllipse(center, r, r)
    painter.end()
    return pixmap


def _draw_chevron(scale: int, color: str, up: bool) -> QPixmap:
    pixmap = _canvas(ARROW_W, ARROW_H, scale)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(2.1 * scale)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    s = scale
    left, mid, right = 1.6 * s, ARROW_W * s / 2, (ARROW_W - 1.6) * s
    top, bottom = 1.8 * s, (ARROW_H - 1.8) * s
    if up:
        painter.drawPolyline(QPointF(left, bottom), QPointF(mid, top), QPointF(right, bottom))
    else:
        painter.drawPolyline(QPointF(left, top), QPointF(mid, bottom), QPointF(right, top))
    painter.end()
    return pixmap


def _save(name: str, one_x: QPixmap, two_x: QPixmap) -> str:
    """1x와 @2x를 나란히 저장하고 QSS에 넣을 경로(1x)를 돌려준다."""
    base = _out_dir() / f"{name}.png"
    one_x.save(str(base), "PNG")
    two_x.save(str(_out_dir() / f"{name}@2x.png"), "PNG")
    return base.as_posix()


def indicator_images(theme: str, colors: dict) -> Dict[str, str]:
    """테마별 표시기 이미지를 만들고 QSS용 경로 모음을 돌려준다.

    이미 만든 테마는 다시 그리지 않는다. 그리기에 실패해도 예외를 내지 않고
    빈 경로를 돌려주므로, 그 경우 표시기는 색 채움만으로 상태를 보인다.
    """
    cached = _cache.get(theme)
    if cached is not None:
        return cached

    try:
        on_accent = colors["accent_fg"]
        arrow = colors["text"]
        images = {
            "check": _save(f"check_{theme}", _draw_check(1, on_accent), _draw_check(2, on_accent)),
            "dot": _save(f"dot_{theme}", _draw_dot(1, on_accent), _draw_dot(2, on_accent)),
            "arrow_up": _save(f"up_{theme}", _draw_chevron(1, arrow, True), _draw_chevron(2, arrow, True)),
            "arrow_down": _save(f"down_{theme}", _draw_chevron(1, arrow, False), _draw_chevron(2, arrow, False)),
        }
    except Exception as e:
        print(f"WARNING: 표시기 이미지를 만들지 못했습니다: {e}")
        images = {"check": "", "dot": "", "arrow_up": "", "arrow_down": ""}

    _cache[theme] = images
    return images
