"""헤더의 앱 이름을 그림 로고로 바꿔 준다.

assets/logo/ 에는 언어 3종 × 테마 2종, 총 6개의 완성된 PNG가 들어 있다.
배경이 이미 투명하고 글자 색도 테마에 맞춰 칠해져 있어서, 여기서는 표시 크기로
줄여 쓰기만 한다.

파일은 표시 높이의 3배(462x90)로 만들어져 있어 어떤 화면 배율에서도 축소만
일어난다. 팔레트의 text 색을 바꾸면 로고 글자 색은 따라오지 않으니, 그때는
원본에서 다시 만들어 넣어야 한다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

from PyQt6.QtCore import QLocale, Qt
from PyQt6.QtGui import QImage, QPixmap

LOGO_HEIGHT = 30

LOGO_DIR = Path("assets") / "logo"
LANGUAGE_CODES = {
    QLocale.Language.Korean: "ko",
    QLocale.Language.Japanese: "jp",
}
LANGUAGE_FALLBACK = "en"

_cache: Dict[Tuple[str, str, int, float], QPixmap] = {}


def language_code(language: Optional[QLocale.Language] = None) -> str:
    """OS 표시 언어에 대응하는 로고 언어 코드. 모르는 언어면 영문."""
    if language is None:
        language = QLocale.system().language()
    return LANGUAGE_CODES.get(language, LANGUAGE_FALLBACK)


def logo_path(theme: str, language: Optional[QLocale.Language] = None) -> Path:
    """언어·테마에 맞는 로고 경로(프로젝트 기준 상대 경로)."""
    return LOGO_DIR / f"logo_{language_code(language)}_{theme}.png"


def build_logo(theme: str, height: int = LOGO_HEIGHT, dpr: float = 1.0,
               language: Optional[QLocale.Language] = None) -> Optional[QPixmap]:
    """헤더에 넣을 로고 픽스맵을 돌려준다.

    파일이 없거나 읽지 못하면 None을 돌려준다. 호출부는 글자 제목으로 되돌아가므로
    로고가 빠져도 앱은 그대로 쓸 수 있다.
    """
    from src.utils import get_resource_path

    lang = language_code(language)
    key = (lang, theme, height, dpr)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    image = QImage(str(get_resource_path(logo_path(theme, language))))
    if image.isNull():
        return None

    device_height = max(1, round(height * (dpr or 1.0)))
    scaled = image.scaledToHeight(device_height, Qt.TransformationMode.SmoothTransformation)
    pixmap = QPixmap.fromImage(scaled)
    pixmap.setDevicePixelRatio(dpr or 1.0)
    _cache[key] = pixmap
    return pixmap
