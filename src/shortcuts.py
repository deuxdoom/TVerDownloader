"""단축키 정의와 설정값 해석.

조합을 사용자가 바꿀 수 있어서 '어떤 동작이 있는지'와 '지금 어떤 키인지'를 한곳에
모은다. 메인 창은 동작 이름으로만 연결하고 설정 창은 같은 목록으로 편집 화면을
만든다. 양쪽이 각자 목록을 들고 있으면 동작을 하나 늘릴 때 한쪽이 빠진다.
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

WINDOW만 창 전체에서 듣고, 나머지는 지정한 위젯에 포커스가 있을 때만 듣는다.
목록 삭제나 검색어 지우기는 수식키 없이 눌리는 키라서, 범위를 좁혀 두지 않으면
글자를 입력하는 도중에 그 키를 빼앗는다.
"""

TYPING_MODIFIERS = (Qt.KeyboardModifier.ControlModifier
                    | Qt.KeyboardModifier.AltModifier
                    | Qt.KeyboardModifier.MetaModifier)
"""이 중 하나라도 끼면 글자 입력과 겹치지 않는 조합으로 본다."""

FUNCTION_KEYS = range(Qt.Key.Key_F1.value, Qt.Key.Key_F35.value + 1)


class ShortcutDef(NamedTuple):
    """동작 하나의 이름표와 기본 조합, 듣는 범위."""

    key: str
    label: str
    default: str
    scope: str
    hint: str


SHORTCUT_DEFS: tuple[ShortcutDef, ...] = (
    ShortcutDef("open_settings", "설정 열기", "Ctrl+,", WINDOW,
                "창 어디에서나 설정 창을 엽니다."),
    ShortcutDef("toggle_log", "로그 패널 열고 닫기", "Ctrl+L", WINDOW,
                "오른쪽 로그 패널을 접거나 폽니다."),
    ShortcutDef("delete_selected", "목록에서 선택 항목 삭제", "Del", DOWNLOAD_LIST,
                "다운로드 목록에 포커스가 있을 때만 동작합니다. 진행 중인 항목은 남습니다."),
    ShortcutDef("clear_search", "검색어 지우기", "Esc", SEARCH_INPUT,
                "기록·즐겨찾기 탭의 검색칸에 포커스가 있을 때만 동작합니다."),
)

DEF_BY_KEY: dict[str, ShortcutDef] = {d.key: d for d in SHORTCUT_DEFS}


def defaults() -> dict[str, str]:
    """공장 초기값 조합표."""
    return {d.key: d.default for d in SHORTCUT_DEFS}


def normalize(text: str) -> str:
    """사람이 적은 조합 문자열을 저장·비교용 표기 하나로 맞춘다.

    'ctrl+l'과 'Ctrl+L'을 다른 조합으로 보면 충돌 검사가 헛돌고, 설정 파일을 직접
    고친 뒤 앱이 다르게 읽는 일이 생긴다. 해석되지 않는 값은 빈 문자열이 되어
    '사용 안 함'으로 떨어진다.
    """
    return QKeySequence(text or "").toString(QKeySequence.SequenceFormat.PortableText)


def display(text: str) -> str:
    """화면에 보여 줄 표기. 없으면 '사용 안 함'.

    저장은 PortableText로 하지만 보여 줄 때는 OS 표기를 쓴다. macOS에서 Ctrl이
    ⌘로 보이는 것처럼, 사용자가 자기 키보드에서 실제로 보는 이름이어야 한다.
    """
    seq = QKeySequence(text or "")
    return seq.toString(QKeySequence.SequenceFormat.NativeText) or "사용 안 함"


def resolve(config: dict) -> dict[str, str]:
    """설정에서 지금 쓸 조합표를 만든다.

    설정에 없는 항목은 기본값으로 채운다. 값이 있는데 해석되지 않으면 비워 둔다.
    사용자가 일부러 지운 것과 구별할 방법이 없고, 멋대로 기본값으로 되돌리면
    꺼 놓은 단축키가 되살아난다.
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

    Ctrl·Alt·Win 없이 눌리는 키는 입력칸에서 그대로 글자이거나 편집 동작이다.
    QShortcut은 켜져 있는 한 키를 위젯보다 먼저 가져가므로, 이런 조합은 입력 중에
    아예 비활성으로 만들어야 눌린 키가 입력칸까지 간다.

    기능키(F1~F35)는 예외다. 수식키가 없어도 글자가 되지 않아서, 입력 중이라고
    막으면 얻는 것 없이 동작만 사라진다.
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

    범위가 서로 다른 위젯이면 포커스가 한쪽에만 있으므로 같은 키를 써도 부딪히지
    않는다. 창 전체를 듣는 쪽은 어느 위젯에 포커스가 있든 끼어든다.
    """
    return a.scope == b.scope or WINDOW in (a.scope, b.scope)


def conflicts(table: dict[str, str]) -> list[tuple[str, list[str]]]:
    """겹치는 조합을 (조합, 동작 목록)으로 묶어 돌려준다.

    Qt는 같은 범위에 같은 조합이 둘 있으면 어느 쪽도 실행하지 않는다. 저장하기
    전에 잡지 않으면 사용자에게는 그냥 단축키가 죽은 것으로 보인다.
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
