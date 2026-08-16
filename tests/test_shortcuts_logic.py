"""단축키 해석과 충돌 판정.

QKeySequence는 QApplication 없이도 문자열을 해석하므로 여기서 돌릴 수 있다.
설정 화면에 실제로 그려 보는 일은 tools/test_shortcuts.py 몫이다.

충돌 판정이 특히 중요하다. Qt는 같은 범위에 같은 조합이 둘이면 **어느 쪽도**
실행하지 않는다. 저장하기 전에 잡지 못하면 사용자에게는 그냥 단축키가 죽은
것으로 보이고, 설정 화면 어디에도 이상한 곳이 없다.
"""

import pytest

from src import shortcuts


class TestNormalize:
    @pytest.mark.parametrize("raw", ["ctrl+l", "Ctrl+L", "CTRL+L"])
    def test_대소문자를_한_표기로_모은다(self, raw):
        """다르게 보면 충돌 검사가 헛돌고, 설정 파일을 손으로 고쳤을 때 어긋난다."""
        assert shortcuts.normalize(raw) == "Ctrl+L"

    @pytest.mark.parametrize("raw", ["", None, "그런키없음"])
    def test_해석되지_않으면_빈_문자열이_되어_사용_안_함이_된다(self, raw):
        assert shortcuts.normalize(raw) == ""


class TestDisplay:
    def test_비어_있으면_사용_안_함으로_보인다(self):
        assert shortcuts.display("") == "사용 안 함"

    def test_조합이_있으면_그_이름을_보인다(self):
        assert shortcuts.display("Ctrl+L")


class TestResolve:
    def test_설정이_비면_기본값으로_채운다(self):
        table = shortcuts.resolve({})
        assert table == shortcuts.defaults()

    def test_저장된_값이_기본값을_이긴다(self):
        table = shortcuts.resolve({"shortcuts": {"open_settings": "Ctrl+P"}})
        assert table["open_settings"] == "Ctrl+P"

    def test_저장되지_않은_항목만_기본값으로_채운다(self):
        table = shortcuts.resolve({"shortcuts": {"open_settings": "Ctrl+P"}})
        assert table["toggle_log"] == shortcuts.DEF_BY_KEY["toggle_log"].default

    def test_일부러_비운_것은_되살리지_않는다(self):
        """빈 값은 '사용 안 함'이다. 기본값으로 되돌리면 꺼 놓은 단축키가 살아난다."""
        table = shortcuts.resolve({"shortcuts": {"toggle_log": ""}})
        assert table["toggle_log"] == ""

    def test_해석되지_않는_값도_비운_것으로_본다(self):
        table = shortcuts.resolve({"shortcuts": {"toggle_log": "그런키없음"}})
        assert table["toggle_log"] == ""

    def test_저장값이_dict가_아니면_전부_기본값(self):
        """설정 파일이 깨졌을 때 앱이 죽지 않아야 한다."""
        assert shortcuts.resolve({"shortcuts": "이상한값"}) == shortcuts.defaults()

    def test_저장값을_정규화해서_돌려준다(self):
        table = shortcuts.resolve({"shortcuts": {"toggle_log": "ctrl+l"}})
        assert table["toggle_log"] == "Ctrl+L"


class TestNeedsTypingGuard:
    """글자를 입력하는 중에 꺼 둬야 하는 조합인지."""

    @pytest.mark.parametrize("combo", ["Del", "Esc", "A", "1"])
    def test_수식키가_없으면_보호가_필요하다(self, combo):
        """QShortcut이 켜져 있으면 키를 위젯보다 먼저 가져간다."""
        assert shortcuts.needs_typing_guard(combo) is True

    @pytest.mark.parametrize("combo", ["Ctrl+L", "Alt+F4", "Ctrl+Shift+P"])
    def test_수식키가_끼면_보호가_필요_없다(self, combo):
        assert shortcuts.needs_typing_guard(combo) is False

    @pytest.mark.parametrize("combo", ["F1", "F5", "F12"])
    def test_기능키는_예외다(self, combo):
        """수식키가 없어도 글자가 되지 않는다. 막으면 얻는 것 없이 동작만 사라진다."""
        assert shortcuts.needs_typing_guard(combo) is False

    @pytest.mark.parametrize("combo", ["", None, "그런키없음"])
    def test_빈_조합은_보호할_것이_없다(self, combo):
        assert shortcuts.needs_typing_guard(combo) is False


class TestConflicts:
    def test_겹치지_않으면_빈_목록(self):
        assert shortcuts.conflicts(shortcuts.defaults()) == []

    def test_같은_범위에서_겹치면_잡는다(self):
        """open_settings와 toggle_log는 둘 다 창 전체 범위다."""
        table = dict(shortcuts.defaults(), open_settings="Ctrl+L", toggle_log="Ctrl+L")
        found = shortcuts.conflicts(table)
        assert len(found) == 1
        combo, keys = found[0]
        assert combo == "Ctrl+L"
        assert set(keys) == {"open_settings", "toggle_log"}

    def test_창_전체_범위는_위젯_범위와도_부딪힌다(self):
        """창 전체를 듣는 쪽은 어느 위젯에 포커스가 있든 끼어든다."""
        table = dict(shortcuts.defaults(), open_settings="Del")
        found = shortcuts.conflicts(table)
        assert found and found[0][0] == "Del"

    def test_서로_다른_위젯_범위끼리는_충돌이_아니다(self):
        """포커스가 한쪽에만 있으므로 같은 키를 써도 부딪히지 않는다."""
        table = dict(shortcuts.defaults(), delete_selected="Esc", clear_search="Esc")
        assert shortcuts.conflicts(table) == []

    def test_빈_조합끼리는_충돌이_아니다(self):
        """'사용 안 함'이 여럿이라고 부딪힐 일은 없다."""
        table = {d.key: "" for d in shortcuts.SHORTCUT_DEFS}
        assert shortcuts.conflicts(table) == []


class TestDefs:
    def test_기본값에_모든_동작이_들어_있다(self):
        assert set(shortcuts.defaults()) == {d.key for d in shortcuts.SHORTCUT_DEFS}

    def test_기본_조합끼리는_겹치지_않는다(self):
        """공장 초기값이 서로 부딪히면 처음 켠 사람부터 단축키가 죽는다."""
        values = [d.default for d in shortcuts.SHORTCUT_DEFS]
        assert len(values) == len(set(values))

    def test_모든_동작에_범위가_지정돼_있다(self):
        valid = {shortcuts.WINDOW, shortcuts.DOWNLOAD_LIST, shortcuts.SEARCH_INPUT}
        assert all(d.scope in valid for d in shortcuts.SHORTCUT_DEFS)
