"""진행률 환산.

카드와 트레이 고리가 같은 값을 보여야 해서 정리는 한 곳에서만 한다. 그 한 곳이
두 군데로 나뉘어 있다 — **조각 수를 아는 DownloadThread가 전체 기준으로 환산하고,
utils.item_percent는 받은 값을 다듬기만 한다.**

여기서 틀리면 눈에 아주 잘 띈다. 실제로 있었던 증상이 이랬다.

- 50%까지 차오르다 갑자기 완료 (유튜브처럼 조각이 하나인 곳을 둘로 가정)
- 자막을 받는 동안 진행바가 절반까지 차오르고 영상 내내 '오디오 다운로드 중'
- 마지막 구간에서 진행률이 뒤로 감 (표지 그림을 본편으로 셈)
"""

import pytest

from src.utils import item_percent
from src.threads.download_thread import DownloadThread


class TestItemPercent:
    """화면 쪽 정리. 값이 없으면 이전 값을 지킨다."""

    def test_값이_없으면_이전_값을_지킨다(self):
        """상태만 바뀐 알림마다 0으로 떨어지면 눈금이 깜빡인다."""
        assert item_percent(None, 42) == 42

    def test_숫자_문자열도_받는다(self):
        assert item_percent("37", 0) == 37

    def test_소수점은_버린다(self):
        assert item_percent(99.9, 0) == 99

    @pytest.mark.parametrize("raw,expected", [(150, 100), (-5, 0), (100, 100), (0, 0)])
    def test_0에서_100_사이로_자른다(self, raw, expected):
        assert item_percent(raw, 7) == expected

    @pytest.mark.parametrize("raw", ["abc", "", [], {}, object()])
    def test_숫자로_못_읽으면_이전_값을_지킨다(self, raw):
        assert item_percent(raw, 55) == 55


class TestOverallPercent:
    """조각 하나의 진행률을 항목 전체 기준으로 옮긴다."""

    def make(self, parts, index, aside=False):
        thread = DownloadThread.__new__(DownloadThread)
        thread._parts, thread._part_index, thread._aside = parts, index, aside
        return thread

    def test_두_조각_중_첫째는_앞_절반에_들어간다(self):
        assert self.make(2, 0)._overall_percent(50) == 25.0

    def test_두_조각_중_둘째는_뒤_절반에_들어간다(self):
        assert self.make(2, 1)._overall_percent(50) == 75.0

    def test_한_조각이면_그대로_쓴다(self):
        """유튜브처럼 소리까지 든 파일 하나를 주는 곳. 둘로 가정하면 50%에서 멈춘다."""
        assert self.make(1, 0)._overall_percent(50) == 50.0

    def test_조각_경계가_이어진다(self):
        """첫 조각의 끝과 둘째 조각의 시작이 같아야 눈금이 튀지 않는다."""
        assert self.make(2, 0)._overall_percent(100) == self.make(2, 1)._overall_percent(0)

    def test_본편이_아니면_알리지_않는다(self):
        """자막·표지 그림. None을 주면 화면이 마지막 값을 지킨다."""
        assert self.make(2, 0, aside=True)._overall_percent(50) is None

    def test_첫_조각_전에는_알리지_않는다(self):
        """본편보다 먼저 오는 자막을 받는 중이다."""
        assert self.make(2, -1)._overall_percent(50) is None

    def test_100을_넘지_않는다(self):
        assert self.make(2, 1)._overall_percent(150) == 100.0


class TestBeginDestination:
    """Destination 한 줄을 받아 몇 번째 조각인지 정한다."""

    def make(self, parts=2, sidecars=()):
        thread = DownloadThread.__new__(DownloadThread)
        thread._parts, thread._part_index, thread._aside = parts, -1, False
        thread._current_component = ""
        thread._sidecar_paths = set(sidecars)
        return thread

    def test_본편을_순서대로_센다(self):
        thread = self.make()
        thread._begin_destination("video.mp4")
        assert (thread._part_index, thread._aside) == (0, False)
        thread._begin_destination("audio.m4a")
        assert (thread._part_index, thread._aside) == (1, False)

    def test_미리_알려진_곁다리는_세지_않는다(self):
        """yt-dlp가 'Writing ... to:'로 먼저 알려 준 경로."""
        thread = self.make(sidecars=["sub.ja.vtt"])
        thread._begin_destination("sub.ja.vtt")
        assert thread._aside is True
        assert thread._part_index == -1

    def test_자막이_먼저_와도_본편이_첫_조각을_차지한다(self):
        """34KB짜리 자막이 첫 조각 자리를 가져가면 진행바가 순식간에 50%까지 찬다."""
        thread = self.make(sidecars=["sub.ja.vtt"])
        thread._begin_destination("sub.ja.vtt")
        thread._begin_destination("video.mp4")
        assert thread._part_index == 0

    def test_조각_수를_넘으면_곁다리로_본다(self):
        """표지 그림은 본편 뒤에 온다. 세면 마지막 구간을 0부터 다시 그린다."""
        thread = self.make(parts=2)
        thread._begin_destination("video.mp4")
        thread._begin_destination("audio.m4a")
        thread._begin_destination("cover.webp")
        assert thread._aside is True
        assert thread._part_index == 1

    def test_두_조각이면_구성_요소_이름을_붙인다(self):
        thread = self.make(parts=2)
        thread._begin_destination("video.mp4")
        assert thread._current_component == "비디오"
        thread._begin_destination("audio.m4a")
        assert thread._current_component == "오디오"

    def test_한_조각이면_이름을_붙이지_않는다(self):
        """소리까지 든 파일 하나인데 '비디오'라고 적으면 거짓말이 된다."""
        thread = self.make(parts=1)
        thread._begin_destination("all.mp4")
        assert thread._current_component == ""


class TestOutputPatterns:
    """yt-dlp 출력에서 값을 뽑는 정규식."""

    def test_조각_수를_읽는다(self):
        m = DownloadThread.FORMAT_COUNT_RE.search("[info] Downloading 1 format(s): 401+251")
        assert len(m.group(1).split("+")) == 2

    def test_조각이_하나인_경우도_읽는다(self):
        m = DownloadThread.FORMAT_COUNT_RE.search("[info] Downloading 1 format(s): 18")
        assert len(m.group(1).split("+")) == 1

    @pytest.mark.parametrize("line,expected", [
        (r"[info] Writing video subtitles to: C:\dl\s\ep1.ja.vtt", r"C:\dl\s\ep1.ja.vtt"),
        (r"[info] Writing video thumbnail to: C:\dl\s\ep1.webp", r"C:\dl\s\ep1.webp"),
        ("[info] Writing video subtitles to: /home/u/ep1.ja.vtt", "/home/u/ep1.ja.vtt"),
    ])
    def test_곁다리_경로를_뽑는다(self, line, expected):
        """윈도우 역슬래시 경로가 그대로 살아야 나중에 Destination과 맞춰 볼 수 있다."""
        m = DownloadThread.SIDECAR_WRITE_RE.match(line)
        assert m is not None
        assert m.group(1).strip() == expected

    def test_Destination_줄은_곁다리로_잡히지_않는다(self):
        assert DownloadThread.SIDECAR_WRITE_RE.match(
            r"[download] Destination: C:\dl\s\ep1.f401.mp4") is None

    def test_기본_조각_수는_둘이다(self):
        """TVer는 늘 영상과 소리를 따로 준다. 1로 가정하면 100%가 찼다가 0으로 떨어진다."""
        assert DownloadThread.DEFAULT_PARTS == 2
