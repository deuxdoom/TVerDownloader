"""exe / 창 / 트레이에 쓰는 앱 아이콘(PNG)을 QIcon으로 만들어 준다.

UI 안에서 쓰는 Fluent 아이콘(SVG)은 src/icons.py가 따로 다룬다.

진행률 고리도 여기서 그린다. 그리는 방식은 indicators.py와 같은 QPainter지만
쓰임이 달라 자리를 나눴다 — 그쪽은 QSS의 image:에 넣을 PNG 파일을 뽑는 곳이고,
여기는 앱 아이콘을 바탕에 깔고 그 위에 덧그린 QIcon을 돌려주는 곳이다.
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

트레이 아이콘 자리는 16~20px이지만 그건 **논리** 크기다. Qt는 화면 배율을 곱한
실제 화소를 달라고 한다 — 150%에서 16px 자리에 24x24를, 20px 자리에 30x30을
요구한다(이 기계에서 재 봤다). 목록에 없는 크기는 가장 가까운 큰 것을 줄여
쓰는데, 두께가 2px뿐인 고리는 그렇게 줄이면 흐려진다.

그래서 16과 20에 흔한 배율(100·125·150·200%)을 곱한 값을 미리 다 그려 둔다.
하나가 몇 킬로바이트짜리 그림이라 여덟 개를 그려도 1초에 한 번 하는 일로는 싸다.
"""

RING_WIDTH_RATIO = 0.13
"""고리 두께 / 아이콘 한 변. 16px에서 2px, 24px에서 3px쯤 된다.

16px에서 1px이면 흐려져 사라지고 4px이면 안쪽 그림이 남지 않는다. 그 사이에서
잡은 값이다.
"""

RING_MIN_WIDTH = 2.0
"""가장 작은 크기에서도 이 두께는 지킨다. 1px 선은 안티앨리어싱에 묻힌다."""

ICON_SCALE = 0.52
"""고리 안에 넣을 앱 아이콘의 너비 비율.

고리는 원인데 아이콘은 가로로 긴 사각형(60:50)이라 네 귀퉁이가 원보다 먼저
바깥으로 나간다. 0.72에서는 위아래가 고리에 닿아 파고든 것처럼 보였다.

실제로 칠해진 화소의 최대 반지름을 크기마다 재서 골랐다. 0.58은 20px에서 틈이
0.29px밖에 남지 않고, 0.52라야 여덟 크기 모두 1.6px 넘게 벌어진다. 16px에서는
어차피 int(16*0.55)와 int(16*0.52)가 둘 다 8px이라 0.55로 둬도 그림은 같다.
"""

RING_TRACK_COLOR = "#6E7681"
"""아직 안 채워진 부분.

**앱 테마 색을 쓰지 않는다.** 트레이가 놓이는 곳은 우리 창이 아니라 윈도우 작업
표시줄이고, 그 배경은 앱 테마가 아니라 윈도우 테마를 따라간다. 앱은 라이트로
쓰면서 작업 표시줄만 어두운 조합이 흔해서, 앱 색을 따라가면 절반은 안 보인다.

가운데 밝기의 회색이라 양쪽 모두에서 뜬다(밝은 표시줄 4.14 : 어두운 표시줄 3.55).
고리 전체를 두르는 이 선이 진행 부분의 바탕이 되어, 초록이 어디까지 찼는지를
배경과 무관하게 읽히게 한다.
"""

RING_FILL_COLOR = "#22C55E"
"""채워진 부분. 같은 이유로 고정색이다.

밝은 표시줄 대비 2.05, 어두운 표시줄 대비 7.15로 밝은 쪽이 약하지만, 이 호는
언제나 회색 바탕선 **위에** 놓이고 둘 사이 대비가 2.02에 색상까지 달라 경계가
드러난다. 배경만으로 버티는 구간은 100%뿐이고 그때는 고리가 이미 꽉 찬 원이라
모양으로 읽힌다.

브랜드색인 청록은 쓰지 않았다. 어두운 배경에서는 잘 보여도 밝은 작업 표시줄에서
회색 바탕선과 구별이 되지 않았다.
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

    원본 PNG는 64x64 캔버스에 60x50짜리 그림이 들어 있고, 위 여백이 8px인데 아래는
    6px이라 **그림이 1px 아래로 치우쳐 있다.** 캔버스를 기준으로 가운데 맞추면 그
    치우침이 그대로 남아, 고리 안에서 아래쪽만 좁아 보인다.

    그림이 실제로 든 자리를 재서 잘라 두면 가운데 맞추기가 그림 기준이 되고,
    가로세로 여백이 다른 것도 함께 해결된다. 한 번 재서 들고 있는다 — 앱이 도는
    동안 원본이 바뀔 일은 없다.
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

    그리다 실패하면 원래 아이콘으로 물러선다. 트레이에 아이콘이 없으면 앱을
    다시 부를 방법까지 사라지므로, 고리 하나 때문에 그 자리를 비울 수는 없다.
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
