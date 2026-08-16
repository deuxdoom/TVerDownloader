"""Fluent UI System Icons를 테마 색에 맞춰 QIcon으로 만들어 준다.

원본 SVG는 fill="#212121"을 하드코딩하고 있어서, 이 값을 런타임에 테마 색으로
치환한 뒤 렌더한다. 앱 아이콘(PNG)을 다루는 src/appicon.py와는 별개 모듈이다.

SVG 원문은 src/icons_data.py에 임베드돼 있다. 아이콘을 갈아끼우려면
assets/icons/에 파일을 넣고 `python tools/gen_icons.py`를 다시 돌린다.
"""
from __future__ import annotations

from typing import Dict, Tuple

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
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


_tint_cache: Dict[Tuple[int, str], QIcon] = {}


def is_monochrome_white(icon: QIcon) -> bool:
    """아이콘이 흰색 단색인지 본다.

    Qt가 딸려 보내는 편집 아이콘(:/icons)이 그렇다. 어두운 배경을 전제로 만들어져
    라이트 테마에서는 배경에 묻힌다. 색이 든 아이콘까지 덮어칠하지 않으려고,
    실제로 흰색뿐인 것만 골라낸다.
    """
    sizes = icon.availableSizes()
    if not sizes:
        return False
    image = icon.pixmap(sizes[0]).toImage()
    found = False
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() < 200:
                continue
            found = True
            if color.red() < 240 or color.green() < 240 or color.blue() < 240:
                return False
    return found


def tint_icon(icon: QIcon, color: str) -> QIcon:
    """단색 아이콘의 색만 바꾼다. 모양(알파)은 그대로 둔다.

    SVG를 다시 그리는 get_icon과 달리 이미 만들어진 QIcon을 받는다. Qt가 내부
    자원으로 들고 있어 원본 SVG에 손댈 수 없는 아이콘을 테마 색으로 맞출 때 쓴다.

    가진 크기를 모두 옮겨 담는다. 하나만 만들어 두면 다른 크기를 요구받을 때
    Qt가 늘려 쓰면서 흐려진다.
    """
    key = (icon.cacheKey(), color)
    cached = _tint_cache.get(key)
    if cached is not None:
        return cached

    tinted = QIcon()
    for size in icon.availableSizes():
        source = icon.pixmap(size)
        canvas = QPixmap(source.size())
        canvas.setDevicePixelRatio(source.devicePixelRatio())
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        try:
            painter.drawPixmap(0, 0, source)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(canvas.rect(), QColor(color))
        finally:
            painter.end()
        tinted.addPixmap(canvas)

    _tint_cache[key] = tinted
    return tinted


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
