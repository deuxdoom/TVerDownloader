"""단축키 정의와 설정값 해석.

'어떤 동작이 있는지'와 '지금 어떤 키인지'를 한곳에 모은다 - 메인 창과 설정 창이 각자 목록을
들고 있으면 동작을 하나 늘릴 때 한쪽이 빠진다.
"""
from __future__ import annotations

from typing import NamedTuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence

CONFIG_KEY = "shortcuts"

WINDOW = "window"
DOWNLOAD_LIST = "download_list"
SEARCH_INPUT = "search_input"
"""단축키가 듣는 범위.

WINDOW만 창 전체에서 듣는다. 목록 삭제나 검색어 지우기는 수식키 없이 눌리는 키라, 범위를
좁혀 두지 않으면 글자를 입력하는 도중에 그 키를 빼앗는다.
"""

TYPING_MODIFIERS = (Qt.KeyboardModifier.ControlModifier
                    | Qt.KeyboardModifier.AltModifier
                    | Qt.KeyboardModifier.MetaModifier)
"""이 중 하나라도 끼면 글자 입력과 겹치지 않는 조합으로 본다."""

FUNCTION_KEYS = range(Qt.Key.Key_F1.value, Qt.Key.Key_F35.value + 1)


def _t(key: str) -> str:
    """i18n의 t()를 함수 안에서 끌어온다.

    utils.py가 이 모듈의 defaults()를 모듈 최상단에서 가져가고 i18n.py는 그 utils.py를
    가져가므로, 여기서 위로 import하면 순환이 된다(실측: ImportError로 pytest 수집 자체가
    멈췄다). localized_app_name이 쓰는 것과 같은 회피다.
    """
    from src.i18n import t
    return t(key)


class ShortcutDef(NamedTuple):
    """동작 하나의 기본 조합과 듣는 범위.

    이름표와 설명은 문구가 아니라 **번역 키**를 담는다. 이 목록이 모듈 상수라 값을 담으면
    i18n.setup()보다 먼저 평가되어 언어가 굳는다 - label()/hint()가 부를 때마다 새로 찾는다.
    """

    key: str
    default: str
    scope: str

    def label(self) -> str:
        return _t(f"shortcuts.{self.key}")

    def hint(self) -> str:
        return _t(f"shortcuts.{self.key}_hint")


SHORTCUT_DEFS: tuple[ShortcutDef, ...] = (
    ShortcutDef("open_settings", "Ctrl+,", WINDOW),
    ShortcutDef("toggle_log", "Ctrl+L", WINDOW),
    ShortcutDef("delete_selected", "Del", DOWNLOAD_LIST),
    ShortcutDef("clear_search", "Esc", SEARCH_INPUT),
)

DEF_BY_KEY: dict[str, ShortcutDef] = {d.key: d for d in SHORTCUT_DEFS}


def defaults() -> dict[str, str]:
    """공장 초기값 조합표."""
    return {d.key: d.default for d in SHORTCUT_DEFS}


def normalize(text: str) -> str:
    """사람이 적은 조합 문자열을 저장·비교용 표기 하나로 맞춘다.

    'ctrl+l'과 'Ctrl+L'을 다르게 보면 충돌 검사가 헛돈다. 해석되지 않는 값은 빈 문자열이
    되어 '사용 안 함'으로 떨어진다.
    """
    return QKeySequence(text or "").toString(QKeySequence.SequenceFormat.PortableText)


def display(text: str) -> str:
    """화면에 보여 줄 표기. 없으면 '사용 안 함'.

    저장은 PortableText로 하되 보여 줄 때는 OS 표기를 쓴다(macOS에서 Ctrl은 ⌘로 보인다).
    """
    seq = QKeySequence(text or "")
    return seq.toString(QKeySequence.SequenceFormat.NativeText) or _t("shortcuts.none")


def resolve(config: dict) -> dict[str, str]:
    """설정에서 지금 쓸 조합표를 만든다.

    없는 항목은 기본값으로 채우고, 값이 있는데 해석되지 않으면 비워 둔다 - 일부러 지운
    것과 구별할 수 없어 기본값으로 되돌리면 꺼 놓은 단축키가 되살아난다.
    """
    stored = config.get(CONFIG_KEY)
    stored = stored if isinstance(stored, dict) else {}
    table: dict[str, str] = {}
    for definition in SHORTCUT_DEFS:
        if definition.key in stored:
            table[definition.key] = normalize(str(stored[definition.key]))
        else:
            table[definition.key] = definition.default
    return table


def needs_typing_guard(text: str) -> bool:
    """글자를 입력하는 중에는 꺼 둬야 하는 조합인지 판별한다.

    Ctrl·Alt·Win 없이 눌리는 키는 입력칸에서 그대로 글자다. QShortcut은 켜져 있는 한 키를
    위젯보다 먼저 가져가므로 아예 비활성으로 만들어야 입력칸까지 간다. 기능키(F1~F35)는
    글자가 되지 않아 예외로 둔다.
    """
    seq = QKeySequence(text or "")
    if not seq.count() or not seq.toString():
        return False
    combination = seq[0]
    if combination.keyboardModifiers() & TYPING_MODIFIERS:
        return False
    return combination.key() not in FUNCTION_KEYS


def _overlaps(a: ShortcutDef, b: ShortcutDef) -> bool:
    """두 동작이 같은 순간에 같은 키를 두고 다툴 수 있는지.

    범위가 서로 다른 위젯이면 포커스가 한쪽에만 있어 부딪히지 않는다.
    """
    return a.scope == b.scope or WINDOW in (a.scope, b.scope)


def conflicts(table: dict[str, str]) -> list[tuple[str, list[str]]]:
    """겹치는 조합을 (조합, 동작 목록)으로 묶어 돌려준다.

    Qt는 같은 범위에 같은 조합이 둘이면 어느 쪽도 실행하지 않아, 그냥 죽은 것으로 보인다.
    """
    groups: dict[str, list[ShortcutDef]] = {}
    for definition in SHORTCUT_DEFS:
        text = table.get(definition.key, "")
        if text:
            groups.setdefault(text, []).append(definition)
    found: list[tuple[str, list[str]]] = []
    for text, members in groups.items():
        clashing = [d for d in members
                    if any(other is not d and _overlaps(d, other) for other in members)]
        if len(clashing) > 1:
            found.append((text, [d.key for d in clashing]))
    return found
