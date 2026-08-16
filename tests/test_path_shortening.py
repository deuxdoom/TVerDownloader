"""저장 경로가 너무 길 때 이름을 줄이는 규칙.

원래 _build_final_filepath 안에 묻혀 있어서, 극단적으로 긴 이름을 넣어 보려면
다운로드를 통째로 돌려야 했다. 계산 자체는 파일 시스템도 yt-dlp도 건드리지
않으므로 순수 함수(shorten_long_path)로 떼어 두고 여기서 직접 부른다.

이 규칙이 중요한 이유는 실패가 조용하기 때문이다. TVer는 영상과 음성을 따로
받아 합치는데 음성 쪽 임시 파일명이 더 길어서 먼저 경로 제한에 걸린다. 그러면
yt-dlp는 0으로 끝나고 영상만 남아, 겉보기에는 성공한 것처럼 보인다.
"""

import os

import pytest

from src.threads.download_thread import shorten_long_path, MAX_PATH_LEN, MIN_NAME_LEN

DL = r"C:\dl"


class TestNotTooLong:
    """줄일 필요가 없을 때."""

    def test_짧으면_손대지_않는다(self):
        full, shortened = shorten_long_path(DL, "시리즈/제1화", "mp4")
        assert shortened is None
        assert full.endswith("제1화.mp4")

    def test_줄이지_않았으면_둘째_값이_None이다(self):
        """부르는 쪽은 이 값으로 안내 로그를 낼지 정한다."""
        _, shortened = shorten_long_path(DL, "ep1", "mp4")
        assert shortened is None

    def test_경계값_바로_아래는_그대로_둔다(self):
        base = "a" * (MAX_PATH_LEN - len(DL) - len("\\") - len(".mp4"))
        full, shortened = shorten_long_path(DL, base, "mp4")
        assert len(full) == MAX_PATH_LEN
        assert shortened is None


class TestSeriesFolderKept:
    """시리즈 폴더가 있을 때 구분자가 살아남는가.

    구분자를 잃으면 시리즈 폴더가 사라지고 파일이 최상위에 쏟아진다. 이름이
    조금 잘리는 것보다 훨씬 나쁜 결과라서 따로 묶어 둔다.
    """

    def test_회차명이_길어도_폴더_구분자가_남는다(self):
        full, shortened = shorten_long_path(DL, "시리즈이름/" + "가" * 300, "mp4")
        assert "/" in full
        assert "/" in shortened
        assert full.startswith(DL)

    def test_폴더명이_길어도_구분자가_남는다(self):
        full, _ = shorten_long_path(DL, "폴" * 300 + "/제1화", "mp4")
        assert "/" in full

    def test_둘_다_길어도_구분자가_남는다(self):
        full, _ = shorten_long_path(DL, "폴" * 300 + "/" + "가" * 300, "mp4")
        assert "/" in full

    def test_회차명부터_줄이고_폴더는_나중에_줄인다(self):
        """폴더를 먼저 깎으면 같은 시리즈가 서로 다른 폴더로 흩어진다.

        회차명만 줄여서 들어맞는 경우 폴더 이름은 온전해야 한다.
        """
        folder = "시리즈이름"
        full, _ = shorten_long_path(DL, f"{folder}/" + "가" * 300, "mp4")
        assert f"{folder}/" in full

    def test_폴더가_없으면_구분자를_만들지_않는다(self):
        full, _ = shorten_long_path(DL, "가" * 300, "mp4")
        assert "/" not in full


class TestShortensToLimit:
    """실제로 제한 안에 들어가는가."""

    @pytest.mark.parametrize("rel", [
        "가" * 300,
        "시리즈/" + "가" * 300,
        "폴" * 300 + "/제1화",
        "폴" * 300 + "/" + "가" * 300,
        "폴" * 300 + "/ab",
    ])
    def test_제한_안으로_들어온다(self, rel):
        full, shortened = shorten_long_path(DL, rel, "mp4")
        assert len(full) <= MAX_PATH_LEN
        assert shortened is not None

    def test_확장자는_잘리지_않는다(self):
        """이름을 줄이지 확장자를 건드리지는 않는다. 잘리면 재생기가 못 연다."""
        full, _ = shorten_long_path(DL, "가" * 300, "mp4")
        assert full.endswith(".mp4")

    def test_돌려주는_상대경로가_실제_경로와_맞는다(self):
        """안내 로그에 찍히는 값이라 실제 저장 위치와 어긋나면 안 된다."""
        full, shortened = shorten_long_path(DL, "시리즈/" + "가" * 300, "mp4")
        assert full == os.path.join(DL, shortened)

    def test_max_len을_넘겨_받을_수_있다(self):
        """인자로 바꿀 수 있어야 경계 조건을 직접 재 볼 수 있다."""
        full, shortened = shorten_long_path(DL, "가" * 100, "mp4", max_len=60)
        assert len(full) <= 60
        assert shortened is not None


class TestBestEffortLimits:
    """할 수 있는 만큼만 줄인다. 반드시 들어맞는다고 약속하지 않는다."""

    def test_이름은_최소_길이_아래로는_깎지_않는다(self):
        """두 글자짜리 이름은 어느 회차인지 알아볼 수 없다.

        경로가 조금 넘치더라도 알아볼 수 있는 편이 낫다는 판단이다.
        """
        full, _ = shorten_long_path(DL, "폴" * 300 + "/" + "가" * 300, "mp4")
        base = full.rsplit("/", 1)[1]
        assert len(base) - len(".mp4") >= MIN_NAME_LEN

    def test_저장_폴더_자체가_길면_제한을_못_지킨다(self):
        """사용자가 고른 폴더는 우리가 줄일 수 없다.

        이 경우 음성만 저장에 실패하고 영상만 남을 수 있는데, 그건
        _warn_missing_audio가 따로 알린다. 여기서는 '못 지킨다'는 사실만
        기록해 둔다 — 모르고 있다가 나중에 놀라지 않으려고.
        """
        long_dir = "C:\\" + "d" * 300
        full, shortened = shorten_long_path(long_dir, "s/ep1", "mp4")
        assert len(full) > MAX_PATH_LEN
        assert shortened is not None
