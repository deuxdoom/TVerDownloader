"""새 로고 이미지를 헤더용 PNG 6종(언어 3 × 테마 2)으로 변환한다.

    python tools/gen_titlelogo.py logo_ko.png logo_jp.png logo_en.png
    python tools/gen_titlelogo.py mylogo.png --lang ko

파일명에 _ko / _jp(_ja) / _en 이 들어 있으면 언어를 알아서 잡고, 없으면 --lang으로
지정한다. 결과는 assets/logo/logo_<lang>_<theme>.png 로 덮어쓴다.

입력 형태는 세 가지를 알아서 구분한다.
  - 투명 배경(알파 있음)  : 알파를 그대로 쓴다
  - 흰 배경(알파 없음)    : 배경을 빼고 잉크만 남긴다
  - 어두운 배경(알파 없음): 마찬가지로 배경을 빼고 잉크만 남긴다

무채색 글자는 테마의 본문 색으로 다시 칠하고, 색이 있는 글자는 원래 색을 지킨다.
그래서 라이트에서는 검은 글자, 다크에서는 흰 글자로 나오면서 브랜드 색은 유지된다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication

from src.qss import palette
from src.titlelogo import LOGO_DIR, LOGO_HEIGHT

ROOT = Path(__file__).resolve().parent.parent
THEMES = ("light", "dark")

EXPORT_SCALE = 3
NEUTRAL_SATURATION = 60
COLOR_EDGE_SPAN = 48.0

LANG_TOKENS = {"ko": "ko", "kr": "ko", "jp": "jp", "ja": "jp", "en": "en", "us": "en"}


def detect_language(path: Path) -> str | None:
    for token in path.stem.lower().replace("-", "_").split("_"):
        if token in LANG_TOKENS:
            return LANG_TOKENS[token]
    return None


def luminance(color: QColor) -> float:
    return 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()


def has_real_transparency(image: QImage) -> bool:
    if not image.hasAlphaChannel():
        return False
    for x in range(0, image.width(), 3):
        for y in range(0, image.height(), 3):
            if QColor.fromRgba(image.pixel(x, y)).alpha() < 240:
                return True
    return False


def background_color(image: QImage) -> QColor:
    """네 모서리에서 배경색을 고른다. 로고는 보통 여백이 있어 모서리가 배경이다."""
    w, h = image.width() - 1, image.height() - 1
    corners = [QColor(image.pixel(x, y)) for x, y in ((0, 0), (w, 0), (0, h), (w, h))]
    return corners[0] if len(set(c.name() for c in corners)) > 2 else max(
        corners, key=lambda c: sum(1 for o in corners if abs(luminance(o) - luminance(c)) < 12))


def extract_ink(image: QImage) -> QImage:
    """배경을 투명으로 만들고 잉크만 남긴 ARGB 이미지를 돌려준다."""
    out = image.convertToFormat(QImage.Format.Format_ARGB32)
    if has_real_transparency(out):
        return out

    background = background_color(out)
    bg_lum = luminance(background)

    neutral_span = 1.0
    for x in range(out.width()):
        for y in range(out.height()):
            color = QColor(out.pixel(x, y))
            if color.saturation() < NEUTRAL_SATURATION:
                neutral_span = max(neutral_span, abs(luminance(color) - bg_lum))

    for x in range(out.width()):
        for y in range(out.height()):
            color = QColor(out.pixel(x, y))
            distance = max(abs(color.red() - background.red()),
                           abs(color.green() - background.green()),
                           abs(color.blue() - background.blue()))
            if distance <= 2:
                out.setPixelColor(x, y, QColor(0, 0, 0, 0))
                continue
            if color.saturation() < NEUTRAL_SATURATION:
                alpha = round(min(255.0, abs(luminance(color) - bg_lum) / neutral_span * 255.0))
            else:
                alpha = round(min(255.0, distance / COLOR_EDGE_SPAN * 255.0))
            out.setPixelColor(x, y, QColor(color.red(), color.green(), color.blue(), alpha))
    return out


def tint_neutrals(image: QImage, ink_color: str) -> QImage:
    """무채색 잉크만 테마 본문 색으로 바꾼다. 색이 있는 부분은 그대로 둔다."""
    out = image.copy()
    ink = QColor(ink_color)
    for x in range(out.width()):
        for y in range(out.height()):
            color = QColor.fromRgba(out.pixel(x, y))
            if color.alpha() == 0 or color.saturation() >= NEUTRAL_SATURATION:
                continue
            out.setPixelColor(x, y, QColor(ink.red(), ink.green(), ink.blue(), color.alpha()))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="로고 이미지를 헤더용 PNG로 변환합니다.")
    parser.add_argument("sources", nargs="+", type=Path, help="원본 로고 이미지")
    parser.add_argument("--lang", choices=("ko", "jp", "en"),
                        help="언어 코드. 파일명으로 알 수 없을 때 지정합니다.")
    parser.add_argument("--out", type=Path, default=ROOT / LOGO_DIR, help="출력 폴더")
    parser.add_argument("--height", type=int, default=LOGO_HEIGHT * EXPORT_SCALE,
                        help=f"내보낼 높이(px). 기본 {LOGO_HEIGHT * EXPORT_SCALE}")
    args = parser.parse_args()

    app = QApplication([])
    args.out.mkdir(parents=True, exist_ok=True)

    failures = 0
    for source in args.sources:
        if not source.is_file():
            print(f"[건너뜀] 파일이 없습니다: {source}", file=sys.stderr); failures += 1; continue

        lang = args.lang or detect_language(source)
        if lang is None:
            print(f"[건너뜀] 언어를 알 수 없습니다: {source.name} (--lang 으로 지정하세요)",
                  file=sys.stderr); failures += 1; continue

        image = QImage(str(source))
        if image.isNull():
            print(f"[건너뜀] 이미지를 읽지 못했습니다: {source}", file=sys.stderr); failures += 1; continue

        scaled = image.scaledToHeight(args.height, Qt.TransformationMode.SmoothTransformation)
        transparent = has_real_transparency(scaled.convertToFormat(QImage.Format.Format_ARGB32))
        ink = extract_ink(scaled)
        print(f"{source.name}  -> 언어 {lang}, 입력 {image.width()}x{image.height()}, "
              f"{'투명 배경' if transparent else '배경 제거함'}")

        for theme in THEMES:
            out_path = args.out / f"logo_{lang}_{theme}.png"
            tint_neutrals(ink, palette(theme)["text"]).save(str(out_path), "PNG")
            print(f"   {out_path.relative_to(ROOT) if out_path.is_relative_to(ROOT) else out_path}"
                  f"  ({ink.width()}x{args.height})")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
