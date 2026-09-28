"""체크 표시, 라디오 점, 스핀박스 화살표를 그려 임시 폴더에 PNG로 내보낸다.

스타일시트가 걸리면 Qt가 표시기(subcontrol)를 네이티브로 그리지 않아, QSS로 배경만 칠하면 체크
표시가 사라진 녹색 사각형이 된다. QSS의 url()은 파일 경로만 받으므로 1x와 @2x를 써 두고 경로를
넘긴다. 폴더는 모든 실행이 함께 쓴다 - 4.5.0 전에는 실행마다 새로 만들어 켠 횟수만큼 쌓였다.
"""
from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Dict

from PyQt6.QtCore import QBuffer, QIODevice, QPointF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen

BOX = 15
ARROW_W, ARROW_H = 11, 7

DIR_NAME = "tverdl_indicators"
"""모든 실행이 함께 쓰는 폴더. 옛 폴더를 지우는 이름 규칙(LEGACY_PREFIX)에 걸리지 않게 짓는다."""

LEGACY_PREFIX = "tverdl_ind_"
"""4.5.0 전 판이 실행마다 `tempfile.mkdtemp`로 만들고 남긴 폴더의 이름 머리."""

IMAGE_KEYS = ("check", "check_menu", "dot", "arrow_up", "arrow_down")
"""QSS가 꺼내 쓰는 이름. 그리기에 실패해도 모두 빈 경로로 채운다.

하나라도 빠지면 QSS를 짓다가 KeyError로 앱이 뜨지 않는다(4.4.0까지 `check_menu`가 빠져 있었다).
"""

_dir: Path | None = None
_cache: Dict[str, Dict[str, str]] = {}


def _out_dir() -> Path:
    global _dir
    if _dir is None:
        folder = Path(tempfile.gettempdir()) / DIR_NAME
        folder.mkdir(parents=True, exist_ok=True)
        _dir = folder
    return _dir


def _canvas(width: int, height: int, scale: int) -> QImage:
    """QPixmap이 아니라 QImage인 것은 앱 없이도 그릴 수 있어서다. 앱 안에서는 PNG가 바이트까지 같다(실측)."""
    image = QImage(width * scale, height * scale, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    return image


def _draw_check(scale: int, color: str) -> QImage:
    image = _canvas(BOX, BOX, scale)
    painter = QPainter(image)
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
    return image


def _draw_dot(scale: int, color: str) -> QImage:
    image = _canvas(BOX, BOX, scale)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    r = 3.0 * scale
    center = QPointF(BOX * scale / 2, BOX * scale / 2)
    painter.drawEllipse(center, r, r)
    painter.end()
    return image


def _draw_chevron(scale: int, color: str, up: bool) -> QImage:
    image = _canvas(ARROW_W, ARROW_H, scale)
    painter = QPainter(image)
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
    return image


def _png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return buffer.data().data()


def write_if_changed(path: Path, data: bytes) -> None:
    """내용이 다를 때만 임시 이름에 써서 바꿔 단다. 같은 파일을 다른 실행이 읽고 있을 수 있다.

    바꿔 달지 못해도 파일이 있으면 그것을 쓴다(업데이트 적용 창과 옛 본체가 함께 도는 순간). 같은
    내용이면 시각만 새로 적어 예전처럼 켤 때마다 새 파일로 보이게 한다 - 오래된 임시 파일로 지워지지 않게.
    """
    try:
        if path.read_bytes() == data:
            with contextlib.suppress(OSError):
                os.utime(path)
            return
    except OSError:
        pass
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temp.write_bytes(data)
    try:
        os.replace(temp, path)
    except OSError:
        with contextlib.suppress(OSError):
            temp.unlink()
        if not path.is_file():
            raise


def _save(name: str, one_x: QImage, two_x: QImage) -> str:
    """1x와 @2x를 나란히 저장하고 QSS에 넣을 경로(1x)를 돌려준다."""
    base = _out_dir() / f"{name}.png"
    write_if_changed(base, _png_bytes(one_x))
    write_if_changed(_out_dir() / f"{name}@2x.png", _png_bytes(two_x))
    return base.as_posix()


def indicator_images(theme: str, colors: dict) -> Dict[str, str]:
    """테마별 표시기 이미지를 만들고 QSS용 경로 모음을 돌려준다.

    이미 만든 테마는 다시 그리지 않는다. 실패해도 빈 경로를 돌려주어 색 채움만 남는다.
    """
    cached = _cache.get(theme)
    if cached is not None:
        return cached

    try:
        on_accent = colors["accent_fg"]
        arrow = colors["text"]
        images = {
            "check": _save(f"check_{theme}", _draw_check(1, on_accent), _draw_check(2, on_accent)),
            "check_menu": _save(f"checkmenu_{theme}", _draw_check(1, colors["accent"]),
                                _draw_check(2, colors["accent"])),
            "dot": _save(f"dot_{theme}", _draw_dot(1, on_accent), _draw_dot(2, on_accent)),
            "arrow_up": _save(f"up_{theme}", _draw_chevron(1, arrow, True), _draw_chevron(2, arrow, True)),
            "arrow_down": _save(f"down_{theme}", _draw_chevron(1, arrow, False), _draw_chevron(2, arrow, False)),
        }
    except Exception as e:
        print(f"WARNING: 표시기 이미지를 만들지 못했습니다: {e}")
        images = {key: "" for key in IMAGE_KEYS}

    _cache[theme] = images
    return images


def remove_legacy_dirs(temp_dir: Path) -> int:
    """4.5.0 전 판이 남긴 폴더를 지우고 지운 개수를 돌려준다. 실패는 삼킨다."""
    try:
        folders = [path for path in temp_dir.iterdir()
                   if path.name.startswith(LEGACY_PREFIX) and path.is_dir()]
    except OSError:
        return 0
    removed = 0
    for folder in folders:
        shutil.rmtree(folder, ignore_errors=True)
        if not folder.exists():
            removed += 1
    return removed


def start_legacy_cleanup() -> None:
    """remove_legacy_dirs를 따로 돌린다. 수천 개가 쌓인 PC가 있어 창을 짓는 동안 막지 않게 한다.

    **메인 창만 부른다.** 업데이트 적용 창은 옛 본체와 함께 돌아, 그 본체가 쓰는 폴더를 지우게 된다.
    """
    threading.Thread(target=remove_legacy_dirs, args=(Path(tempfile.gettempdir()),),
                     name="indicator-cleanup", daemon=True).start()
