"""헤더의 앱 이름을 그림 로고로 바꿔 준다.

assets/logo/에 언어 3종 × 테마 2종의 완성된 PNG가 있다. 표시 높이의 3배(462x90)로
만들어져 어떤 배율에서도 축소만 일어난다. 팔레트의 text 색을 바꿔도 로고 글자 색은
따라오지 않으므로 그때는 원본에서 다시 만들어 넣어야 한다.

로고 언어는 **앱이 지금 쓰는 언어**(i18n.current_code())를 따른다 - OS 언어를 직접
묻지 않는다. 그러지 않으면 설정에서 언어를 영어로 골라도 로고만 OS 언어(예: 한국어)로
남는, 애초에 이 다국어화를 시작하게 만든 그 불일치가 되풀이된다.

**그림이 있는 언어는 세 벌뿐이고 나머지는 영어 로고를 쓴다**(logo_language). 번역
파일만 넣으면 언어가 늘어나는 구조라 로고가 언어 수를 따라가지 않는다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

from PyQt6.QtCore import QLocale, Qt
from PyQt6.QtGui import QImage, QPixmap

from src import i18n

LOGO_HEIGHT = 30

LOGO_DIR = Path("assets") / "logo"
LANGUAGE_FALLBACK = "en"

LOGO_LANGUAGES = ("ko", "jp", "en")
"""전용 로고 그림이 있는 언어. **언어를 늘려도 여기는 늘리지 않는다.**

로고는 글자를 그려 넣은 그림이라 언어마다 새로 만들어야 하는데, 번역 파일 하나만
넣으면 언어가 늘어나는 구조와 맞지 않는다. 그림이 없는 언어는 영어 로고를 쓴다.
"""

_cache: Dict[Tuple[str, str, int, float], QPixmap] = {}


def language_code(language: Optional[QLocale.Language] = None) -> str:
    """앱이 지금 쓰는 언어 코드. language를 넘기면 그 OS 언어로 가정한다(검증용) -
    localized_app_name()과 같은 패턴이다. 넘기지 않으면 i18n의 현재 언어를 따른다.
    """
    if language is not None:
        return i18n.code_for_os_language(language)
    return i18n.current_code()


def logo_language(language: Optional[QLocale.Language] = None) -> str:
    """실제로 쓸 로고의 언어. 그림이 없는 언어는 영어로 떨어진다.

    **떨어뜨리지 않으면 헤더가 글자 제목으로 바뀐다.** 그림을 못 읽었을 때의 대비인
    그 경로가, 로고가 아예 없는 언어에서는 늘 걸려 그 언어만 헤더 모양이 달라진다.
    """
    code = language_code(language)
    return code if code in LOGO_LANGUAGES else LANGUAGE_FALLBACK


def logo_path(theme: str, language: Optional[QLocale.Language] = None) -> Path:
    """언어·테마에 맞는 로고 경로(프로젝트 기준 상대 경로)."""
    return LOGO_DIR / f"logo_{logo_language(language)}_{theme}.png"


def build_logo(theme: str, height: int = LOGO_HEIGHT, dpr: float = 1.0,
               language: Optional[QLocale.Language] = None) -> Optional[QPixmap]:
    """헤더에 넣을 로고 픽스맵. 없거나 못 읽으면 None이고 호출부는 글자 제목으로 돌아간다."""
    from src.utils import get_resource_path

    lang = logo_language(language)
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
