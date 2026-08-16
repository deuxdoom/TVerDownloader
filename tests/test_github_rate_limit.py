"""GitHub API 호출 한도 판정.

업데이트 확인이 조용히 실패하던 자리다. 403은 권한 문제로도 오고 429는 일시적
과부하로도 오기 때문에, 상태 코드만 보고 '한도 초과'라고 말하면 엉뚱한 안내를
띄우게 된다. 남은 호출 수가 0이라고 **명시된** 경우만 한도로 본다.

헤더는 남이 주는 값이라 없을 수도, 숫자가 아닐 수도 있다. 그때 예외가 밖으로
나가면 업데이트 확인이 앱 전체를 끌고 넘어진다.
"""

import re

import pytest

from src.utils import (is_rate_limited, rate_limit_reset_text, rate_limit_message,
                       github_api_headers, RATE_LIMIT_STATUSES)


class TestIsRateLimited:
    @pytest.mark.parametrize("status", RATE_LIMIT_STATUSES)
    def test_한도_상태코드에_남은_호출이_0이면_한도_초과(self, fake_response, status):
        response = fake_response(status, {"X-RateLimit-Remaining": "0"})
        assert is_rate_limited(response) is True

    @pytest.mark.parametrize("status", RATE_LIMIT_STATUSES)
    def test_남은_호출이_있으면_한도가_아니다(self, fake_response, status):
        """403이지만 권한 문제인 경우. 기다린다고 풀리지 않는다."""
        response = fake_response(status, {"X-RateLimit-Remaining": "17"})
        assert is_rate_limited(response) is False

    def test_헤더가_아예_없으면_한도가_아니다(self, fake_response):
        assert is_rate_limited(fake_response(403, {})) is False

    @pytest.mark.parametrize("status", [200, 404, 500, 502])
    def test_다른_상태코드는_헤더와_무관하게_한도가_아니다(self, fake_response, status):
        response = fake_response(status, {"X-RateLimit-Remaining": "0"})
        assert is_rate_limited(response) is False

    def test_남은_호출이_숫자가_아니면_한도가_아니다(self, fake_response):
        """문자열 '0'과의 정확한 비교라 이상한 값은 자연히 걸러진다."""
        response = fake_response(403, {"X-RateLimit-Remaining": "없음"})
        assert is_rate_limited(response) is False


class TestRateLimitResetText:
    def test_에포크_초를_읽을_수_있는_시각으로_바꾼다(self, fake_response):
        response = fake_response(403, {"X-RateLimit-Reset": "1700000000"})
        got = rate_limit_reset_text(response)
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", got)

    def test_헤더가_없으면_빈_문자열(self, fake_response):
        """호출부는 시각 안내만 생략하고 나머지 문구를 그대로 쓴다."""
        assert rate_limit_reset_text(fake_response(403, {})) == ""

    @pytest.mark.parametrize("raw", ["", "곧", "abc", "1.5", "9" * 30, "-1" * 20, None])
    def test_잘못된_값이면_예외_없이_빈_문자열(self, fake_response, raw):
        """남이 주는 값이라 무엇이든 올 수 있다. 여기서 터지면 업데이트 확인이 죽는다."""
        response = fake_response(403, {"X-RateLimit-Reset": raw})
        assert rate_limit_reset_text(response) == ""


class TestRateLimitMessage:
    def test_시각을_알면_함께_알린다(self, fake_response):
        response = fake_response(403, {"X-RateLimit-Reset": "1700000000"})
        got = rate_limit_message(response)
        assert "호출 한도를 초과했습니다" in got
        assert "이후에 풀립니다" in got

    def test_시각을_모르면_앞부분만_알린다(self, fake_response):
        got = rate_limit_message(fake_response(403, {}))
        assert "호출 한도를 초과했습니다" in got
        assert "이후에 풀립니다" not in got


class TestHeaders:
    def test_User_Agent가_반드시_들어간다(self):
        """없으면 GitHub이 403으로 막는다. 이게 빠지면 한도와 구별되지 않는다."""
        headers = github_api_headers("TVerDownloader/3.3.0")
        assert headers["User-Agent"] == "TVerDownloader/3.3.0"
        assert headers["Accept"] == "application/vnd.github+json"
