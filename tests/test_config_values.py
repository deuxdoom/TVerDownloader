"""설정값 정규화와 잡다한 순수 헬퍼.

동시 다운로드 수는 설정 파일에서 오는 값이라 무엇이든 들어올 수 있다. 예전
버전이 쓰던 키 이름도 여럿이라, 그걸 못 읽으면 사용자가 정해 둔 값이 조용히
기본값으로 되돌아간다.
"""

import pytest

from src.utils import (canonicalize_config_parallel, resolve_ffprobe_path,
                       localized_app_name, DEFAULT_PARALLEL, PARALLEL_MIN, PARALLEL_MAX,
                       ERROR_STATUSES, FINISHED_STATUSES, NO_AUDIO_STATUS)


class TestCanonicalizeParallel:
    def test_정상_값은_그대로(self):
        assert canonicalize_config_parallel({"max_concurrent_downloads": 3}) == 3

    @pytest.mark.parametrize("raw,expected", [
        (0, PARALLEL_MIN), (-5, PARALLEL_MIN),
        (999, PARALLEL_MAX), (PARALLEL_MAX + 1, PARALLEL_MAX),
    ])
    def test_범위를_벗어나면_잘라_넣는다(self, raw, expected):
        assert canonicalize_config_parallel({"max_concurrent_downloads": raw}) == expected

    @pytest.mark.parametrize("raw", ["3", 3.0, "3.7"])
    def test_숫자로_읽을_수_있으면_받는다(self, raw):
        """설정 파일을 손으로 고치면 문자열로 들어온다."""
        assert canonicalize_config_parallel({"max_concurrent_downloads": raw}) == 3

    @pytest.mark.parametrize("raw", ["많이", None, [], {}])
    def test_숫자가_아니면_기본값(self, raw):
        assert canonicalize_config_parallel({"max_concurrent_downloads": raw}) == DEFAULT_PARALLEL

    def test_설정이_비면_기본값(self):
        assert canonicalize_config_parallel({}) == DEFAULT_PARALLEL

    @pytest.mark.parametrize("legacy", [
        "max_parallel", "max_parallel_downloads", "parallel_downloads",
        "concurrent_downloads", "max_concurrent", "concurrency",
    ])
    def test_예전_키_이름도_읽는다(self, legacy):
        """못 읽으면 사용자가 정해 둔 값이 조용히 기본값으로 되돌아간다."""
        assert canonicalize_config_parallel({legacy: 7}) == 7

    def test_현재_키가_예전_키를_이긴다(self):
        assert canonicalize_config_parallel(
            {"max_concurrent_downloads": 2, "max_parallel": 9}) == 2

    @pytest.mark.parametrize("container", ["downloads", "download", "settings", "general", "app"])
    def test_한_겹_안쪽에_있어도_찾는다(self, container):
        assert canonicalize_config_parallel({container: {"max_parallel": 4}}) == 4

    def test_안쪽_값이_dict가_아니면_넘어간다(self):
        assert canonicalize_config_parallel({"downloads": "이상한값"}) == DEFAULT_PARALLEL


class TestResolveFfprobePath:
    def test_경로가_비면_None(self):
        assert resolve_ffprobe_path("") is None
        assert resolve_ffprobe_path(None) is None

    def test_없는_파일이면_None(self, tmp_path):
        assert resolve_ffprobe_path(str(tmp_path / "ffmpeg.exe")) is None

    def test_같은_폴더의_짝을_찾는다(self, tmp_path):
        (tmp_path / "ffprobe.exe").write_bytes(b"x")
        got = resolve_ffprobe_path(str(tmp_path / "ffmpeg.exe"))
        assert got == str(tmp_path / "ffprobe.exe")

    def test_확장자_없는_이름도_찾는다(self, tmp_path):
        (tmp_path / "ffprobe").write_bytes(b"x")
        got = resolve_ffprobe_path(str(tmp_path / "ffmpeg"))
        assert got == str(tmp_path / "ffprobe")

    def test_경로_중간에_ffmpeg가_들어_있어도_엉뚱하게_바꾸지_않는다(self, tmp_path):
        """확장자가 붙은 쪽을 먼저 시도하는 이유다."""
        nested = tmp_path / "ffmpeg" / "bin"
        nested.mkdir(parents=True)
        (nested / "ffprobe.exe").write_bytes(b"x")
        got = resolve_ffprobe_path(str(nested / "ffmpeg.exe"))
        assert got == str(nested / "ffprobe.exe")


class TestStatusSets:
    def test_음성_없음은_실패이면서_동시에_완료다(self):
        """파일은 손에 남지만 재다운로드 대상이다. 양쪽에 다 들어가야 한다."""
        assert NO_AUDIO_STATUS in ERROR_STATUSES
        assert NO_AUDIO_STATUS in FINISHED_STATUSES

    def test_완료는_오류가_아니다(self):
        assert "완료" in FINISHED_STATUSES
        assert "완료" not in ERROR_STATUSES

    @pytest.mark.parametrize("status", ["오류", "취소됨", "실패", "중단", "변환 오류"])
    def test_재다운로드_대상_상태들(self, status):
        assert status in ERROR_STATUSES


class TestLocalizedAppName:
    def test_언어별_이름을_돌려준다(self):
        from PyQt6.QtCore import QLocale
        assert localized_app_name(QLocale.Language.Korean) == "티버 다운로더"
        assert localized_app_name(QLocale.Language.Japanese) == "TVer ダウンローダー"

    def test_모르는_언어는_영문_이름(self):
        from PyQt6.QtCore import QLocale
        assert localized_app_name(QLocale.Language.German) == "TVer Downloader"
