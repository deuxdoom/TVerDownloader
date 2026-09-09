"""exe·창·트레이가 같은 ICO를 읽어 아이콘을 바꿀 때 한 곳만 교체하게 한다.

UI 안에서 쓰는 Fluent 아이콘(SVG)은 src/icons.py, QSS의 image:에 넣을 PNG는
src/indicators.py가 따로 다룬다.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

APP_ICON_PATH = "assets/appicon.ico"


def get_app_icon() -> QIcon:
    """소스 실행과 배포본 모두 같은 리소스 경로를 써 작업 폴더에 영향받지 않는다."""
    from src.utils import get_resource_path

    return QIcon(str(get_resource_path(APP_ICON_PATH)))


TRAY_ICON_SIZES = (16, 20, 24, 30, 32, 36, 40, 48)
"""진행률을 그려 둘 실제 화소 크기들.

트레이 자리는 16~20px이지만 그건 논리 크기다. 150% 배율에서는 24x24, 30x30을 요구한다
(실측). 목록에 없는 크기는 큰 것을 줄여 쓰는데 그러면 채움 경계가 흐려진다.
"""

PROGRESS_TRACK_COLOR = "#6E7681"
"""아직 안 채워진 부분. 받는 동안에는 로고 색 대신 이 색이 선다.

**앱 테마 색을 쓰지 않는다** - 아이콘이 놓이는 곳은 우리 창이 아니라 윈도우 작업
표시줄이고 그 색은 윈도우 테마를 따라간다. 가운데 밝기의 회색이라 양쪽에서 뜬다
(4.14 : 3.55). **흰색은 쓸 수 없다** - 어두운 표시줄에서는 16.29로 가장 선명하지만
밝은 표시줄에서 1.11이라, 0%일 때 아이콘이 통째로 사라지고 채워지는 동안에는 녹색
조각만 떠 있어 모양이 깨져 보인다(실측).
"""

PROGRESS_FILL_COLOR = "#22C55E"
"""채워진 부분. 같은 이유로 고정색이다.

밝은 표시줄 대비 2.05로 약하지만 언제나 회색 바탕 위에 놓이고 둘 사이 대비가 2.02에
색상까지 달라 경계가 드러난다. 브랜드색인 파랑은 회색 바탕과 1.08이라 갈리지 않는다.
"""


_frame_cache: dict = {}


def _frame(size: int):
    """한 크기의 바탕색본·녹색본과 그림이 놓인 세로 구간.

    ICO는 실행 중에 바뀌지 않는데 트레이는 1초마다 아이콘을 새로 만든다. 여덟 크기의
    불투명 화소를 그때마다 훑으면 8,356번을 다시 재게 되어 담아 둔다.
    """
    cached = _frame_cache.get(size)
    if cached is not None:
        return cached

    base = get_app_icon().pixmap(QSize(size, size), 1.0)
    if base.isNull():
        return None

    image = base.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    top = bottom = None
    for y in range(image.height()):
        if any(image.pixelColor(x, y).alpha() > 8 for x in range(image.width())):
            if top is None:
                top = y
            bottom = y
    if top is None:
        return None

    track = _recolor(base, PROGRESS_TRACK_COLOR)
    fill = _recolor(base, PROGRESS_FILL_COLOR)
    _frame_cache[size] = (track, fill, top, bottom + 1)
    return _frame_cache[size]


def _recolor(source: QPixmap, color: str) -> QPixmap:
    """모양만 남기고 한 색으로 칠한다.

    명도를 살려 색상만 바꾸는 방법도 있으나 트레이가 쓰는 16~24px에서는 밝은 면이
    흐려져 경계가 무뎌지고, 값도 5.6배 든다(1.2ms 대 6.8ms, 여덟 크기 기준).
    """
    out = QPixmap(source.size())
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    try:
        painter.drawPixmap(0, 0, source)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(out.rect(), QColor(color))
    finally:
        painter.end()
    return out


def _progress_pixmap(size: int, percent: int) -> QPixmap:
    """한 크기짜리 진행률 아이콘. 아이콘 모양 그대로 아래에서 위로 채운다.

    채움 높이를 그림이 실제로 놓인 구간으로만 재는 것은, ICO에 든 투명 여백까지
    세면 100%인데도 위쪽이 회색으로 남기 때문이다.
    """
    frame = _frame(size)
    if frame is None:
        return QPixmap()
    track, fill, top, bottom = frame

    rows = min(bottom - top, round((bottom - top) * percent / 100))
    canvas = QPixmap(track.size())
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    try:
        painter.drawPixmap(0, 0, track)
        if rows > 0:
            box = QRect(0, bottom - rows, track.width(), rows)
            painter.drawPixmap(box, fill, box)
    finally:
        painter.end()
    return canvas


def app_icon_with_progress(percent: Optional[int]) -> QIcon:
    """진행률만큼 녹색으로 채운 앱 아이콘. percent가 None이면 원래 아이콘.

    고리를 두르지 않는 것은 그러면 안쪽 그림을 절반 크기로 줄여야 해, 받기 시작하는
    순간 트레이 아이콘이 작아지기 때문이다. 그리다 실패하면 원래 아이콘으로 물러선다 -
    트레이가 비면 앱을 다시 부를 방법이 사라진다.
    """
    if percent is None:
        return get_app_icon()
    try:
        bounded = max(0, min(100, int(percent)))
        icon = QIcon()
        for size in TRAY_ICON_SIZES:
            pixmap = _progress_pixmap(size, bounded)
            if pixmap.isNull():
                return get_app_icon()
            icon.addPixmap(pixmap)
        return icon
    except Exception as e:
        print(f"WARNING: 트레이 진행률을 그리지 못했습니다: {e}")
        return get_app_icon()
