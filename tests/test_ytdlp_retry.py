"""통신 오류 판별과 조회용 옵션.

증상은 이랬다. 즐겨찾기 자동 확인이 도는 중에 다른 주소를 넣으면 그 시리즈만
`Read timed out`으로 분석에 실패했다. 받는 쪽은 --retries 10으로 버티는데
물어보는 쪽만 한 번에 포기하고 있었다.

**되풀이해도 소용없는 실패까지 다시 걸면 시간만 버린다.** 없는 영상·지역
제한·404는 몇 초 뒤에도 같다. 그래서 통신이 끊겼다는 흔적이 있을 때만 다시 건다.

여기서 진짜 yt-dlp를 부르지 않는다. 판별은 문자열만 보는 순수 함수라 네트워크가
없어도 된다.
"""

import pytest

from src.threads import ytdlp_run


class TestIsRetriable:
    @pytest.mark.parametrize("stderr", [
        "ERROR: Read timed out (read timeout=20.0)",
        "urllib3.exceptions.ReadTimeoutError: timed out",
        "ConnectionResetError: [Errno 104] Connection reset by peer",
        "Remote end closed connection without response",
        "Max retries exceeded with url",
        "Temporary failure in name resolution",
        "socket.gaierror: [Errno 11001] getaddrinfo failed",
        "HTTP Error 503: Service Unavailable",
    ])
    def test_통신_문제는_다시_건다(self, stderr):
        assert ytdlp_run.is_retriable(stderr) is True

    def test_대소문자를_가리지_않는다(self):
        assert ytdlp_run.is_retriable("READ TIMED OUT") is True

    @pytest.mark.parametrize("code", ["10053", "10054", "10060", "10061", "11001"])
    def test_한국어_소켓_오류는_WinError_번호로_알아본다(self, code):
        """윈도우가 소켓 오류 문구를 한국어로 내보낸다.

        '현재 연결은 원격 호스트에 의해 강제로 끊겼습니다'에는 영어가 한 글자도
        없어서, 번호를 보지 않으면 통신 문제인 줄 모르고 그냥 포기하게 된다.
        """
        stderr = f"OSError: [WinError {code}] 현재 연결은 원격 호스트에 의해 강제로 끊겼습니다"
        assert ytdlp_run.is_retriable(stderr) is True

    @pytest.mark.parametrize("stderr", [
        "ERROR: Video unavailable",
        "ERROR: This video is not available in your region",
        "HTTP Error 404: Not Found",
        "ERROR: Unsupported URL",
        "",
        None,
    ])
    def test_되풀이해도_같을_실패는_다시_걸지_않는다(self, stderr):
        assert ytdlp_run.is_retriable(stderr) is False

    def test_404는_5xx_규칙에_걸리지_않는다(self):
        """'http error 5'가 5xx만 잡고 404를 건드리지 않아야 한다."""
        assert ytdlp_run.is_retriable("HTTP Error 404: Not Found") is False
        assert ytdlp_run.is_retriable("HTTP Error 500: Internal Server Error") is True


class TestNetworkOptions:
    def test_소켓_제한_시간을_늘려_잡는다(self):
        """프로세스를 다시 띄우는 것보다 이쪽이 싸다.

        서버가 죽은 것이 아니라 느릴 뿐이면 여기서 끝난다.
        """
        options = ytdlp_run.network_options()
        assert "--socket-timeout" in options
        assert options[options.index("--socket-timeout") + 1] == ytdlp_run.SOCKET_TIMEOUT
        assert int(ytdlp_run.SOCKET_TIMEOUT) > 20

    def test_yt_dlp_자체_재시도도_켠다(self):
        options = ytdlp_run.network_options()
        assert "--retries" in options
        assert "--extractor-retries" in options

    def test_skip_download는_들어_있지_않다(self):
        """그건 통신 규칙이 아니라 질의 의도라서 명령마다 따로 붙인다.

        --print는 이것이 빠지면 실제로 받으러 간다. 여기 넣어 두면 어느 명령에
        붙었는지 헷갈린다.
        """
        assert "--skip-download" not in ytdlp_run.network_options()


class TestBackoff:
    def test_지수_백오프는_3초에서_6초로_늘어난다(self):
        delays = [ytdlp_run.RETRY_BASE_DELAY * (2 ** (attempt - 1))
                  for attempt in range(1, ytdlp_run.MAX_ATTEMPTS)]
        assert delays == [3, 6]

    def test_최대_시도는_세_번이다(self):
        assert ytdlp_run.MAX_ATTEMPTS == 3
