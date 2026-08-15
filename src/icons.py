"""Fluent UI System Icons를 테마 색에 맞춰 QIcon으로 만들어 준다.

원본 SVG는 fill="#212121"을 하드코딩하고 있어서, 이 값을 런타임에 테마 색으로
치환한 뒤 렌더한다. 앱 아이콘(PNG)을 다루는 src/appicon.py와는 별개 모듈이다.

SVG 원문은 src/icons_data.py에 임베드돼 있다. 아이콘을 갈아끼우려면
assets/icons/에 파일을 넣고 `python tools/gen_icons.py`를 다시 돌린다.
"""
from __future__ import annotations

from typing import Dict, Tuple

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

from src.icons_data import ICON_SVG

FLUENT_FILL = "#212121"
DEFAULT_SIZE = 18

_cache: Dict[Tuple[str, str, int, float], QIcon] = {}


def _device_pixel_ratio() -> float:
    app = QApplication.instance()
    if app is None:
        return 1.0
    screen = app.primaryScreen()
    return screen.devicePixelRatio() if screen is not None else 1.0


def recolor_svg(svg: str, color: str) -> str:
    """SVG의 fill 값을 테마 색으로 치환한다."""
    return svg.replace(f'fill="{FLUENT_FILL}"', f'fill="{color}"')


def get_icon(name: str, color: str, size: int = DEFAULT_SIZE) -> QIcon:
    """이름과 색으로 QIcon을 만든다.

    모르는 이름이면 빈 QIcon을 돌려준다. 오타 하나로 앱이 죽지는 않고,
    해당 버튼만 아이콘 없이 보인다.
    """
    dpr = _device_pixel_ratio()
    key = (name, color, size, dpr)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    svg = ICON_SVG.get(name)
    if svg is None:
        return QIcon()

    pixmap = QPixmap(max(1, round(size * dpr)), max(1, round(size * dpr)))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)

    renderer = QSvgRenderer(QByteArray(recolor_svg(svg, color).encode("utf-8")))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()

    icon = QIcon(pixmap)
    _cache[key] = icon
    return icon
