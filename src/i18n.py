"""화면 문구를 한국어·일본어·영어로 내준다.

로고(titlelogo.py)와 앱 이름(localized_app_name)만 OS 언어를 보고 갈리고 나머지는
전부 한국어였던 불일치가 이 모듈을 만든 이유다. **언어 판단은 여기 한 곳에서만
한다** - titlelogo.py도 이 모듈의 current_code()를 받아 쓰게 될 것이다.

lang/(exe 옆, 사용자가 직접 고치는 곳)과 _internal/lang(빌드에 실린 공장 출하본)을
같은 [meta] code로 매칭해 겹쳐 쌓는다. 새 버전이 키를 늘렸는데 사용자가 옛 lang/을
그대로 쓰고 있어도, 빠진 키는 공장 출하본(같은 언어 → 영어) 순으로 채워지고 그래도
없으면 키 문자열 자체를 돌려준다 - lang/이 깨지거나 통째로 사라져도 앱이 죽지 않는다.
"""
from __future__ import annotations

import configparser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QLocale

from src.utils import get_resource_path

LANG_DIR = Path("lang")
"""사용자가 두는 번역 파일 자리. CONFIG_FILE과 같은 순수 상대경로라 exe 옆(cwd)이다.

**앱이 만들지 않는다.** 배포본에 있는 것은 `_internal/lang`(공장 출하본) 하나뿐이고
그것만으로 동작한다. 여기 폴더를 두는 것은 고친 번역을 자동 업데이트에서 지키려는
사람의 선택이다 - 업데이트 배치가 갈아 끼우는 것은 exe와 `_internal`뿐이라, 공장본을
직접 고치면 다음 업데이트에 덮이지만 이 폴더는 남는다.
"""

FALLBACK_CODE = "en"

CODE_ALIASES = {"ja": "jp"}
"""ISO 639-1과 다르게 적어 둔 우리 코드. 일본어는 로고 파일명 관례를 따라 `jp`다.

**갈아 끼우는 표가 아니라 덧대는 표다.** 누가 `ja`를 code로 쓴 ini를 넣으면 그것이
먼저 잡히고, 없을 때만 `jp`를 본다 - 여기 적힌 이름 때문에 멀쩡한 파일이 밀리면 안 된다.
"""

QT_LOCALE_NAMES = {"jp": "ja", "zh": "zh_CN", "zh_hant": "zh_TW"}
"""우리 코드 -> Qt가 `qtbase_*.qm` 이름에 쓰는 로케일. 표에 없으면 코드를 그대로 넘긴다.

일본어는 로고 파일명 관례를 따라 `jp`인데 Qt는 ISO의 `ja`를 쓰고, 중국어는 우리가 문자
계열(`zh`/`zh_hant`)로 가르는 것을 Qt가 지역(`zh_CN`/`zh_TW`)으로 가른다. 표에 없는 코드도
그대로 넘겨 보는 것은 사용자가 넣은 `fr` 같은 언어를 살리기 위해서다. 그런 qm이 없으면
조용히 실패하고 Qt 기본값인 영어가 나온다 - 엉뚱한 파일을 대신 집어 오지는 않는다(실측).
"""


@dataclass(frozen=True)
class LanguageFile:
    """ini 하나를 읽은 결과. strings는 [meta]를 뺀 나머지 섹션."""
    path: Path
    code: str
    display_name: str
    strings: Dict[str, Dict[str, str]] = field(default_factory=dict)


_current_code: str = FALLBACK_CODE
_strings: Dict[str, Dict[str, str]] = {}


def _parse_ini(path: Path) -> Optional[LanguageFile]:
    """ini 하나를 읽는다. [meta] code가 없거나 깨진 파일은 조용히 건너뛴다."""
    if not path.is_file():
        return None
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error:
        return None
    if "meta" not in parser:
        return None
    code = parser["meta"].get("code", "").strip()
    if not code:
        return None
    display_name = parser["meta"].get("display_name", code).strip()
    strings = {section: dict(parser.items(section))
              for section in parser.sections() if section != "meta"}
    return LanguageFile(path=path, code=code, display_name=display_name, strings=strings)


def _scan_dir(directory: Path) -> Dict[str, LanguageFile]:
    """폴더 안의 *.ini를 전부 읽어 code로 묶는다. 폴더가 없으면 빈 사전."""
    result: Dict[str, LanguageFile] = {}
    if not directory.is_dir():
        return result
    for path in sorted(directory.glob("*.ini")):
        info = _parse_ini(path)
        if info is not None:
            result[info.code] = info
    return result


def _factory_dir() -> Path:
    return get_resource_path(LANG_DIR)


def _user_dir() -> Path:
    return LANG_DIR


def _scan_both() -> Tuple[Dict[str, LanguageFile], Dict[str, LanguageFile]]:
    """공장본과 사용자 폴더를 한 번씩 훑어 (공장본, 사용자)로 돌려준다.

    **한 번 훑는 데 18ms 든다**(ini 일곱 개 × 565키, 실측). 시작할 때
    resolve_code와 load_language가 각자 두 번씩 훑어 네 번이던 것을 두 번으로
    줄이려고 둔다. **읽은 것을 캐시하지는 않는다** - 파일 상태로 무효화하면 앱을
    켜 둔 채 ini를 넣었을 때 설정 창 목록에 바로 나타나던 동작이 그 판정에 걸리고,
    아끼는 값은 여기서 이미 다 나온다.
    """
    return _scan_dir(_factory_dir()), _scan_dir(_user_dir())


def _merge_strings(base: Dict[str, Dict[str, str]],
                   overlay: Dict[str, Dict[str, str]]) -> None:
    """overlay가 base의 같은 섹션·키를 덮어쓴다. 없는 섹션은 그대로 추가."""
    for section, options in overlay.items():
        base.setdefault(section, {}).update(options)


def available_languages() -> List[LanguageFile]:
    """설정 창 콤보에 채울 목록. 사용자 폴더의 표시 이름이 공장본보다 우선한다."""
    factory, user = _scan_both()
    merged: Dict[str, LanguageFile] = {}
    merged.update(factory)
    merged.update(user)
    return sorted(merged.values(), key=lambda info: info.code)


def locale_candidates(locale: QLocale) -> List[str]:
    """QLocale 하나를 우리 코드 후보로 푼다. **좁은 것부터 넓은 것 순**이다.

    zh_TW이면 `zh_tw` -> `zh_hant` -> `zh`가 되어, 번체 전용 ini를 나중에 넣으면
    그것이 먼저 잡히고 없는 동안에는 `zh` 하나로 둘 다 받는다. 지역보다 문자 계열을
    뒤에 두는 것은 홍콩·마카오처럼 지역이 갈려도 문자가 같은 경우를 함께 담기 위해서다.
    """
    language = (QLocale.languageToCode(locale.language()) or "").lower()
    if not language:
        return []
    territory = (QLocale.territoryToCode(locale.territory()) or "").lower()
    script = (QLocale.scriptToCode(locale.script()) or "").lower()
    candidates = []
    if territory:
        candidates.append(f"{language}_{territory}")
    if script:
        candidates.append(f"{language}_{script}")
    candidates.append(language)
    return candidates


def code_for_os_language(os_language: Optional[QLocale.Language] = None,
                         available: Optional[set] = None) -> str:
    """OS 언어에 맞는 코드. **실제로 있는 언어 파일 중에서만 고른다.**

    표에 적어 둔 언어만 알아보던 것을 lang/의 [meta] code와 맞추는 방식으로 바꿨다.
    예전에는 코드에 적힌 한국어·일본어 둘뿐이라, 중국어 윈도우에서 chinese.ini를 넣어도
    영어로 떨어졌다. ini만 넣으면 그 언어가 살아나는 것이 이 설계의 요점이다.

    있는 것만 고르는 것이 요점의 뒷면이다 - 파일이 없는 언어를 코드로 돌려주면 로고와
    앱 이름만 그 언어가 되고 문구는 영어로 남는, 애초에 고치려던 불일치가 되돌아온다.
    available은 이미 훑어 둔 쪽이 넘겨 주는 것이고, 없으면 여기서 훑는다.
    """
    if available is None:
        factory, user = _scan_both()
        available = set(factory) | set(user)
    locale = QLocale(os_language) if os_language is not None else QLocale.system()
    for candidate in locale_candidates(locale):
        for code in (candidate, CODE_ALIASES.get(candidate)):
            if code and code in available:
                return code
    return FALLBACK_CODE


def resolve_code(config_language: str, os_language: Optional[QLocale.Language] = None,
                 scanned: Optional[Tuple[Dict[str, LanguageFile],
                                         Dict[str, LanguageFile]]] = None) -> str:
    """설정값과 OS 언어로 실제 쓸 코드를 정한다.

    사용자가 명시적으로 고른 값이 유효하면(사용자/공장본 어느 쪽에든 있으면) 그 값을
    쓰고, "system"이거나 값이 사라졌으면 OS 표시 언어를 본다. os_language를 넘기면
    그 값으로(검증용) - localized_app_name()과 같은 패턴이다. scanned를 넘기면 폴더를
    다시 훑지 않는다(setup이 load_language와 나눠 쓴다).
    """
    factory, user = scanned if scanned is not None else _scan_both()
    available = set(factory) | set(user)
    if config_language and config_language != "system" and config_language in available:
        return config_language
    return code_for_os_language(os_language, available)


def load_language(code: str,
                  scanned: Optional[Tuple[Dict[str, LanguageFile],
                                          Dict[str, LanguageFile]]] = None) -> None:
    """code에 해당하는 문구를 계층 폴백으로 쌓아 전역 테이블에 싣는다.

    쌓는 순서(먼저 깐 것이 나중 것에 덮인다): 영어 공장본 -> 같은 언어 공장본 ->
    같은 언어 사용자 폴더. 사용자가 고친 값이 항상 최종적으로 이긴다. scanned를 넘기면
    폴더를 다시 훑지 않는다.
    """
    global _current_code, _strings
    factory, user = scanned if scanned is not None else _scan_both()

    merged: Dict[str, Dict[str, str]] = {}
    english = factory.get(FALLBACK_CODE) or user.get(FALLBACK_CODE)
    if english is not None:
        _merge_strings(merged, english.strings)
    if code != FALLBACK_CODE:
        same_factory = factory.get(code)
        if same_factory is not None:
            _merge_strings(merged, same_factory.strings)
    same_user = user.get(code)
    if same_user is not None:
        _merge_strings(merged, same_user.strings)

    _strings = merged
    _current_code = code


def setup(config: dict) -> None:
    """앱 시작 시 한 번 부른다. 설정에 맞는 언어를 싣는다.

    **폴더를 한 번만 훑어 두 함수가 나눠 쓴다** - 각자 훑으면 같은 ini 일곱 개를 두 번
    파싱해 시작이 그만큼 늦는다(한 번에 18ms, 실측).
    """
    scanned = _scan_both()
    load_language(resolve_code(config.get("language", "system"), scanned=scanned),
                  scanned=scanned)


def current_code() -> str:
    return _current_code


def qt_locale(code: Optional[str] = None) -> QLocale:
    """Qt 기본 위젯 번역을 고를 때 쓸 QLocale. 넘기지 않으면 지금 쓰는 언어를 본다.

    **OS 언어를 물으면 안 된다** - 설정에서 영어를 골랐는데 입력칸 우클릭 메뉴만
    한국어로 남는 것이, 이 모듈을 만들게 한 불일치와 같은 종류다.
    """
    target = code or _current_code
    return QLocale(QT_LOCALE_NAMES.get(target, target))


def t(key: str, **kwargs) -> str:
    """"section.option" 키로 문구를 찾는다. 없으면 키 자체를 돌려준다(앱이 죽지 않는다).

    자리표시자가 안 맞아도(옛 lang/에 새 인자가 없는 서식이 남아 있는 경우) 예외
    대신 서식을 채우지 못한 원문을 그대로 돌려준다.
    """
    section, _, option = key.partition(".")
    template = _strings.get(section, {}).get(option)
    if template is None:
        return key
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        return template
