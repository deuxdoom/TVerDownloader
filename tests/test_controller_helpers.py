"""컨트롤러 안의 순수 헬퍼.

컨트롤러 대부분은 창과 목록 위젯을 만져야 해서 tools/ 몫이다. 다만 몇 개는
입력과 출력만 있는 계산이라 여기서 본다. 창을 만들지 않으므로 이 파일은
QApplication이 필요 없다.
"""

import pytest

from src.controllers.download_list import DownloadListController
from src.controllers.library import LibraryController
from src.input_sources import InputSources
from src.utils import FILENAME_TITLE_MAX_LENGTH


class TestSafeFilename:
    """썸네일을 저장할 때 제목에서 파일 이름을 만든다."""

    @pytest.mark.parametrize("ch", list('<>:"/\\|?*'))
    def test_윈도우가_막는_글자를_바꾼다(self, ch):
        got = DownloadListController._safe_filename(f"제{ch}목")
        assert ch not in got

    def test_제어문자도_바꾼다(self):
        got = DownloadListController._safe_filename("제\x00목\x1f끝")
        assert "\x00" not in got and "\x1f" not in got

    def test_앞뒤_공백과_점을_떼어_낸다(self):
        """점으로 끝나는 이름은 윈도우가 만들지 못한다."""
        assert DownloadListController._safe_filename("  제목...  ") == "제목"

    def test_비면_기본_이름을_준다(self):
        assert DownloadListController._safe_filename("   ...   ") == "thumbnail"
        assert DownloadListController._safe_filename("") == "thumbnail"

    def test_너무_길면_잘라_낸다(self):
        got = DownloadListController._safe_filename("가" * 300)
        assert len(got) == FILENAME_TITLE_MAX_LENGTH

    def test_멀쩡한_이름은_그대로_둔다(self):
        assert DownloadListController._safe_filename("아메토크 제1화") == "아메토크 제1화"


class TestElide:
    """알림 창에 보여 줄 한 줄을 줄인다."""

    def test_짧으면_그대로(self):
        assert InputSources._elide("짧은글", 10) == "짧은글"

    def test_한계와_같으면_그대로(self):
        assert InputSources._elide("12345", 5) == "12345"

    def test_넘으면_줄임표를_붙여_한계를_지킨다(self):
        got = InputSources._elide("1234567890", 5)
        assert len(got) == 5
        assert got.endswith("…")


class TestControllerConstants:
    def test_자동_추가_한계는_둘이다(self):
        """이보다 많으면 선택 창을 띄운다.

        50~70개짜리 시리즈가 확인 없이 대기열에 쏟아지면 정작 지금 받고 싶은
        영상이 그 뒤로 밀린다.
        """
        assert LibraryController.FAV_AUTO_ADD_LIMIT == 2

    def test_기록은_백_개까지만_그린다(self):
        assert LibraryController.HISTORY_MAX_DISPLAY == 100

    def test_즐겨찾기는_스무_개까지(self):
        assert LibraryController.MAX_FAVORITES == 20

    def test_잘못된_주소는_다섯_줄까지만_보여_준다(self):
        """스무 줄을 통째로 붙여 놓으면 창이 화면을 넘는다."""
        assert InputSources.BAD_URL_PREVIEW == 5
