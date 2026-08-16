"""주소 판별 두 갈래.

규칙이 일부러 두 개다. match_tver_url은 **좁게** 본다 — 클립보드 감시와 드롭이
쓰는데, 묻지도 않았는데 반응하는 자리라 아닌 것을 집어 오면 방해가 된다.
is_media_url은 **넓게** 본다 — 사람이 직접 넣은 것이라 TVer가 아니어도 yt-dlp가
받을 수 있고, 사이트 판단은 그쪽에 넘긴다.

둘을 한 파일에 둔 것은 이 대비가 무너지는 것을 함께 잡기 위해서다. 한쪽만
고치면 클립보드가 아무 주소에나 반응하거나, 유튜브 주소를 거부하게 된다.
"""

import pytest

from src.utils import match_tver_url, is_media_url


class TestMatchTverUrl:
    """클립보드·드롭이 받아들이는 TVer 주소."""

    @pytest.mark.parametrize("url", [
        "https://tver.jp/episodes/ep6hzy79h",
        "https://tver.jp/series/sryhqsa8t0",
        "https://www.tver.jp/episodes/ep1",
        "http://tver.jp/episodes/ep1",
        "https://tver.jp/episodes/ep_1-2",
    ])
    def test_정상_주소는_그대로_돌려준다(self, url):
        assert match_tver_url(url) == url

    @pytest.mark.parametrize("url", [
        "https://tver.jp/episodes/ep1?utm_source=x&t=30",
        "https://tver.jp/episodes/ep1#chapter2",
        "https://tver.jp/series/sr1?a=1#b",
    ])
    def test_쿼리와_프래그먼트가_붙어도_받는다(self, url):
        """공유 주소에는 추적 파라미터가 늘 붙어 온다."""
        assert match_tver_url(url) == url

    def test_앞뒤_공백은_다듬어_돌려준다(self):
        assert match_tver_url("  https://tver.jp/episodes/ep1  ") == "https://tver.jp/episodes/ep1"

    def test_대소문자를_가리지_않되_원문_표기를_지킨다(self):
        """받아들이기는 하지만 주소를 멋대로 소문자로 바꾸지는 않는다."""
        assert match_tver_url("https://TVER.JP/EPISODES/EP1") == "https://TVER.JP/EPISODES/EP1"

    def test_문장에_섞인_주소는_받지_않는다(self):
        """전체 일치를 요구하는 이유. 긴 글을 복사했을 때 멋대로 반응하면 안 된다."""
        assert match_tver_url("이거 봐 https://tver.jp/episodes/ep1 좋더라") is None

    def test_비슷한_호스트를_거른다(self):
        """tver.jp로 시작하는 것처럼 보이는 남의 도메인."""
        assert match_tver_url("https://tver.jp.evil.com/episodes/ep1") is None

    @pytest.mark.parametrize("text", [
        "https://tver.jp/lp/special",
        "https://tver.jp/",
        "https://youtu.be/abc",
        "tver.jp/episodes/ep1",
        "memo.txt",
        "3.14",
        "",
        None,
    ])
    def test_주소가_아니거나_에피소드_시리즈가_아니면_None(self, text):
        assert match_tver_url(text) is None


class TestIsMediaUrl:
    """입력창·다중 추가가 yt-dlp에 넘겨 볼 만한 주소인지."""

    @pytest.mark.parametrize("url", [
        "https://tver.jp/episodes/ep1",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/abc",
        "http://a.b",
        "https://example.com/path#frag",
    ])
    def test_사이트를_가리지_않는다(self, url):
        """yt-dlp가 다루는 곳이 천 곳이 넘어 목록으로 막을 수 없다."""
        assert is_media_url(url) is True

    def test_앞뒤_공백을_무시한다(self):
        assert is_media_url("  https://a.b/c  ") is True

    @pytest.mark.parametrize("text", [
        "tver.jp/episodes/ep1",
        "www.youtube.com/watch?v=1",
    ])
    def test_체계가_없으면_거부한다(self, text):
        """http:// 또는 https:// 를 반드시 요구한다.

        없이도 받아 주면 'memo.txt'나 '3.14'까지 점이 든 호스트로 보여
        거르는 의미가 사라진다.
        """
        assert is_media_url(text) is False

    @pytest.mark.parametrize("text", [
        "memo.txt",
        "3.14",
        "이 영상 좀 받아줘",
        "C:\\videos\\clip.mp4",
        "/home/user/clip.mp4",
        "",
        None,
    ])
    def test_주소가_아닌_것을_거부한다(self, text):
        assert is_media_url(text) is False

    def test_파일_스킴은_거부한다(self):
        """yt-dlp에 넘길 것은 웹 주소다. 로컬 파일은 여기로 오면 안 된다."""
        assert is_media_url("file:///C:/video.mp4") is False

    def test_점_없는_호스트는_거부한다(self):
        """localhost처럼 점이 없는 이름은 오타일 가능성이 훨씬 높다."""
        assert is_media_url("https://localhost/x") is False
