"""Fluent UI System Icons를 테마 색에 맞춰 QIcon으로 만들어 준다.

원본 SVG가 fill="#212121"을 하드코딩하고 있어 런타임에 테마 색으로 치환한 뒤 렌더한다.
SVG 원문은 src/icons_data.py에 임베드돼 있고, 갈아끼우려면 tools/gen_icons.py를 다시 돌린다.
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
_hover_cache: Dict[Tuple[str, str, str, int, float], QIcon] = {}


def _device_pixel_ratio() -> float:
    app = QApplication.instance()
    if app is None:
        return 1.0
    screen = app.primaryScreen()
    return screen.devicePixelRatio() if screen is not None else 1.0


def recolor_svg(svg: str, color: str) -> str:
    """SVG의 fill과 stroke 값을 테마 색으로 치환한다.

    Fluent 아이콘은 모두 면(fill)으로 그려져 있지만, 우리가 직접 그린 것 중에는 획(stroke)이
    편한 모양이 있다(전원 아이콘의 열린 고리). 둘 다 같은 색 값을 쓰므로 한 번에 바꾼다.
    """
    return (svg.replace(f'fill="{FLUENT_FILL}"', f'fill="{color}"')
               .replace(f'stroke="{FLUENT_FILL}"', f'stroke="{color}"'))


_tint_cache: Dict[Tuple[int, str], QIcon] = {}


def is_monochrome_white(icon: QIcon) -> bool:
    """아이콘이 흰색 단색인지 본다.

    Qt가 딸려 보내는 편집 아이콘(:/icons)이 그렇다. 색이 든 아이콘까지 덮어칠하지
    않으려고 실제로 흰색뿐인 것만 골라낸다.
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

    Qt가 내부 자원으로 들고 있어 원본 SVG에 손댈 수 없는 아이콘에 쓴다. 가진 크기를 모두
    옮겨 담는다 - 하나만 만들면 다른 크기를 요구받을 때 Qt가 늘려 쓰면서 흐려진다.
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


def render_pixmap(name: str, color: str, size: int = DEFAULT_SIZE) -> QPixmap | None:
    """SVG 하나를 그 색으로 그린 픽스맵. 모르는 이름이면 None."""
    svg = ICON_SVG.get(name)
    if svg is None:
        return None

    dpr = _device_pixel_ratio()
    pixmap = QPixmap(max(1, round(size * dpr)), max(1, round(size * dpr)))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)

    renderer = QSvgRenderer(QByteArray(recolor_svg(svg, color).encode("utf-8")))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


def get_icon(name: str, color: str, size: int = DEFAULT_SIZE) -> QIcon:
    """이름과 색으로 QIcon을 만든다. 모르는 이름이면 빈 QIcon(그 버튼만 아이콘이 없다)."""
    key = (name, color, size, _device_pixel_ratio())
    cached = _cache.get(key)
    if cached is not None:
        return cached

    pixmap = render_pixmap(name, color, size)
    if pixmap is None:
        return QIcon()

    icon = QIcon(pixmap)
    _cache[key] = icon
    return icon


def get_hover_icon(name: str, color: str, hover_color: str,
                   size: int = DEFAULT_SIZE) -> QIcon:
    """평소 색과 커서를 올렸을 때 색을 함께 담은 아이콘.

    QToolButton은 커서가 올라간 동안 QIcon.Mode.Active 그림을 쓴다. 배경이 확 바뀌는
    단추(닫기)에서 글리프 색을 enter/leave로 직접 다시 칠하지 않아도 되게 한다.
    """
    key = (name, color, hover_color, size, _device_pixel_ratio())
    cached = _hover_cache.get(key)
    if cached is not None:
        return cached

    base = render_pixmap(name, color, size)
    active = render_pixmap(name, hover_color, size)
    if base is None or active is None:
        return QIcon()

    icon = QIcon(base)
    icon.addPixmap(active, QIcon.Mode.Active)
    _hover_cache[key] = icon
    return icon
