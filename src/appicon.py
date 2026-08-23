"""exe / 창 / 트레이에 쓰는 앱 아이콘(PNG)을 QIcon으로 만들어 준다. 진행률 고리도 여기서 그린다.

UI 안에서 쓰는 Fluent 아이콘(SVG)은 src/icons.py, QSS의 image:에 넣을 PNG는
src/indicators.py가 따로 다룬다.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

APP_ICON_B64 = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAACXBIWXMAAAHYAAAB2AH6XKZyAAAAGXRFWHRTb2Z0d2FyZQB3d3cuaW5rc2NhcGUub3Jnm+48GgAABU1JREFUeJztmltsFFUYx39ndroXWyhpbROBKNHSpIVEvJAGqY1yixLDkyQENPrkAzEiD8aoPJgo0RAbAiKC8uItgsFEY4IBagURqqQihhaDNiRYbq6lpKWwtznz+VDbbstuO7vMTrt1f8lJZmfOnvN9/3O+b86cGShQoECBAgUK/F9Rmf6hZvmJBmXIC4LUA5XZtOEyAoQFjvgUW9q/efDHTP6cgfGiqpe1NAqyPkMDPUWExo6DD70ESpzUdyzAPY98t0HgjexN8xBRr549vOgtJ1UdCTCjbt9M0+RPIHhLhnlHxMas6jy67OJYFU1HzenoSm3njfMAIeBJYOtYFR0JYJYWNwTKplFUUgxqvHPeGIhg3YgQ7+ldggMBRvVmzuvhkqKosQORNeOf7LPikBJZ8+umirShkNarBes7Q31G6HugLiemecdF0yfz04mQNgR6dPBN0XnvPMB0K6E+ApamuphyBsx68eo0f1xfBgK5tMxLlCHzz2yraB15PuUMMCJ6kYaAYUAgCIYpEz73jUQEbEsRi4Jtg7J5AnAmQCgk86aWQUnpxE/6oyOIwPUe6O5Sc1PVuMm9JVvC9YjarxS35d5A7xBNHJ8sblpXOexZYZgAj22+NMtS5i9AmafWeYZcQZn3N60r+2vgjJF82VLmRoQyBCZnUeWi9cZknwdnwJK3u0vFr8OAPwNJ85FYNEHF0ZcrrkFSErRN615ETXbnAQLBIpkHHIEkAcSWijxP+Y4RZVQMHA/NAJThbAsh/xGxfQPH5vAL7ncWMBVPLQjRUB2gOKD4/ZLFnuMR2i4k3O/MKUkTfUgADeJyBPhNxeZVpdROH+rm4dl+6mf7aT4dY8fh64R7bXc7dYBK6nLQMo3TXTTnrJgXpOYOH5Jiai2q8bNwdhF7W6N80hIhEvcu/pIlz2kIPHCXmdL5Afw+WF0XZGmtnw9/uMGBtjieyJA004cWQrpfADfLlIByVO/2EoNXlpewdfUUqipN1+0YWdBDAuQ0BPoXYM4bnTvT5INnp3CgLc7OQxGu9OUmP6QNAbfnn4iMGgLpWDaniIZqk90/x/isJUZCu2xY2ruAu90gdnYCAARMeGZhgMW1RbzzbYST5yyXretn2MNQrmMvmzJjmkHjqmIWVrmXG5IZygHa/c0PIfsZkIwCnl8a4mjHNWwX0oKdah0A7t8GM02Co1E5FaaXGnR2u5sYkwRIvWC5FW4lB6RsTxTiwnJVqaHIz2kI2NJf3OByj3C+23ZllnoXAlneBkeibdi6P4bOwbJgwgtw/qpN474EJ8+5571KtQ7Q2v23fyKSdRKMxoXdP2k+P6aJW+6OjGcPQ9m0KQJNpzTvN1tc7cuBQeDdfoAtZBQCpzqFbfst/ric2z2ClPsBgOtr4d4bNiLGmPW6eoVdhzQHT7mT5TMhp0+DrWdt6qrSCxCz4Mvjmk+PaCJxd/seDdurEPi6VXi0VqidObxhEWhut9nZpAn3ejzkMCwL5jQJxhLCuo8tnq43aKgxKAnC6QvCnmOats5xcPw/kocjpyEAEIsLu5o1u5r12JU9ImUIKI3tdghMVAyRwdFIejGi/8EeO2NPBkQZ4YHjQQGMBCe0jyj58zFktsSsoP5t4MfgkLdvr+wTYe947wDluiDsObOp/80wjLgLGOLboNGPA+VeDIX3SJclxobkMzelveq13fWC/RWTTgTpEmWs6HivvCX5bMq8f/dz3XcaPnsjsJL8/1QuCnyBqV7reLf8/MiLo38quzZckhDuE/FViiKvbhFKsLWt/g6Z1sn27ZV9421PgQIFChSYiPwLkzSS+s+cDxUAAAAASUVORK5CYII="
)


def _base_pixmap() -> QPixmap:
    """원본 앱 아이콘 픽스맵. 데이터가 깨졌으면 빈 픽스맵."""
    payload = APP_ICON_B64.split(",", 1)[-1]
    pixmap = QPixmap()
    if pixmap.loadFromData(QByteArray.fromBase64(payload.encode())):
        return pixmap
    return QPixmap()


def get_app_icon() -> QIcon:
    """앱 아이콘을 돌려준다. 데이터가 깨졌으면 빈 QIcon으로 물러선다."""
    pixmap = _base_pixmap()
    return QIcon(pixmap) if not pixmap.isNull() else QIcon()


TRAY_ICON_SIZES = (16, 20, 24, 30, 32, 36, 40, 48)
"""고리를 그려 둘 실제 화소 크기들.

트레이 자리는 16~20px이지만 그건 논리 크기다. 150% 배율에서는 24x24, 30x30을 요구한다
(실측). 목록에 없는 크기는 큰 것을 줄여 쓰는데 두께 2px짜리 고리는 그러면 흐려진다.
"""

RING_WIDTH_RATIO = 0.13
"""고리 두께 / 아이콘 한 변. 16px에서 2px, 24px에서 3px쯤 된다.

16px에서 1px이면 흐려져 사라지고 4px이면 안쪽 그림이 남지 않는다.
"""

RING_MIN_WIDTH = 2.0
"""가장 작은 크기에서도 이 두께는 지킨다. 1px 선은 안티앨리어싱에 묻힌다."""

ICON_SCALE = 0.52
"""고리 안에 넣을 앱 아이콘의 너비 비율.

고리는 원인데 아이콘은 가로로 긴 사각형(60:50)이라 귀퉁이가 먼저 나간다. 눈으로 고르지
않고 칠해진 화소의 최대 반지름을 크기마다 재서 정했다 - 0.58은 20px에서 틈이 0.29px뿐이고
0.52라야 여덟 크기 모두 1.6px 넘게 벌어진다.
"""

RING_TRACK_COLOR = "#6E7681"
"""아직 안 채워진 부분.

**앱 테마 색을 쓰지 않는다** - 고리가 놓이는 곳은 우리 창이 아니라 윈도우 작업 표시줄이고
그 색은 윈도우 테마를 따라간다. 가운데 밝기의 회색이라 양쪽에서 뜬다(4.14 : 3.55).
"""

RING_FILL_COLOR = "#22C55E"
"""채워진 부분. 같은 이유로 고정색이다.

밝은 표시줄 대비 2.05로 약하지만 언제나 회색 바탕선 위에 놓이고 둘 사이 대비가 2.02에
색상까지 달라 경계가 드러난다. 브랜드색인 청록은 밝은 표시줄에서 바탕선과 구별되지 않았다.
"""


def _draw_ring(pixmap: QPixmap, percent: int) -> None:
    """픽스맵 둘레에 진행률만큼 고리를 그린다. 12시에서 시계 방향."""
    size = pixmap.width()
    width = max(RING_MIN_WIDTH, size * RING_WIDTH_RATIO)
    inset = width / 2
    box = QRectF(inset, inset, size - width, size - width)

    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen()
        pen.setWidthF(width)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)

        pen.setColor(QColor(RING_TRACK_COLOR))
        painter.setPen(pen)
        painter.drawEllipse(box)

        if percent > 0:
            pen.setColor(QColor(RING_FILL_COLOR))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawArc(box, 90 * 16, -int(360 * 16 * percent / 100))
    finally:
        painter.end()


_content_cache: Optional[QPixmap] = None


def _content_pixmap() -> QPixmap:
    """앱 아이콘에서 투명한 여백을 걷어낸 그림.

    원본 PNG는 64x64 캔버스에 60x50짜리 그림이 들어 있고 위 여백 8px에 아래 6px이라
    **1px 아래로 치우쳐 있다.** 캔버스 기준으로 가운데를 맞추면 그 치우침이 그대로 남아
    고리 안에서 아래쪽만 좁아 보인다. 한 번 재서 들고 있는다.
    """
    global _content_cache
    if _content_cache is not None:
        return _content_cache
    base = _base_pixmap()
    image = base.toImage()
    left, top = image.width(), image.height()
    right = bottom = -1
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > 8:
                left = min(left, x); right = max(right, x)
                top = min(top, y); bottom = max(bottom, y)
    if right < 0:
        _content_cache = base
    else:
        _content_cache = base.copy(left, top, right - left + 1, bottom - top + 1)
    return _content_cache


def _progress_pixmap(source: QPixmap, size: int, percent: int) -> QPixmap:
    """한 크기짜리 진행률 아이콘. 고리 안쪽에 앱 아이콘을 얹는다."""
    canvas = QPixmap(size, size)
    canvas.fill(Qt.GlobalColor.transparent)

    inner = max(1, int(size * ICON_SCALE))
    scaled = source.scaled(inner, inner, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    painter = QPainter(canvas)
    try:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(round((size - scaled.width()) / 2),
                           round((size - scaled.height()) / 2), scaled)
    finally:
        painter.end()

    _draw_ring(canvas, percent)
    return canvas


def app_icon_with_progress(percent: Optional[int]) -> QIcon:
    """진행률 고리를 두른 앱 아이콘. percent가 None이면 원래 아이콘.

    그리다 실패하면 원래 아이콘으로 물러선다 - 트레이가 비면 앱을 다시 부를 방법이 사라진다.
    """
    if percent is None:
        return get_app_icon()
    try:
        source = _content_pixmap()
        if source.isNull():
            return QIcon()
        bounded = max(0, min(100, int(percent)))
        icon = QIcon()
        for size in TRAY_ICON_SIZES:
            icon.addPixmap(_progress_pixmap(source, size, bounded))
        return icon
    except Exception as e:
        print(f"WARNING: 트레이 진행률 고리를 그리지 못했습니다: {e}")
        return get_app_icon()
