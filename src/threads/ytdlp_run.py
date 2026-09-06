"""yt-dlp에 정보를 물어볼 때 쓰는 공통 규칙.

받는 쪽은 --retries 10으로 버티는데 물어보는 쪽(시리즈 분석, 다운로드 직전 메타데이터)은
한 번에 포기하고 있었다. 회선을 나눠 쓰면 기본 20초 안에 답이 오지 않아 Read timed out으로
떨어진다. 두 조회 경로가 같은 조건으로 버티도록 규칙을 한곳에 모은다.
"""
from __future__ import annotations

import subprocess
import time
from typing import Callable, List, Optional, Tuple

from src.i18n import t
from src.utils import get_startupinfo

SOCKET_TIMEOUT = "30"
"""yt-dlp에 넘길 소켓 제한 시간(초). 기본값 20초를 늘려 잡는다.

프로세스를 다시 띄우는 것보다 싸다 - 서버가 죽은 것이 아니라 느릴 뿐이면 여기서 끝난다.
"""

YTDLP_RETRIES = "3"
"""yt-dlp 자체 재시도 횟수. 프로세스를 다시 띄우기 전에 안에서 먼저 버틴다."""

MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 3
"""일시적인 통신 오류일 때만 쓰는 지수 백오프. 3초 → 6초.

한 번 걸렸다고 버리면 시작할 때 도는 즐겨찾기 확인에서 그 시리즈만 조용히 빠진다.
"""

RETRIABLE_MARKERS = (
    "read timed out",
    "timed out",
    "timeout",
    "connection reset",
    "connection aborted",
    "connection refused",
    "remote end closed connection",
    "max retries exceeded",
    "temporary failure in name resolution",
    "getaddrinfo failed",
    "transporterror",
    "incompleteread",
    "http error 5",
    "connectionreset",
    "connectionabort",
    "connectionrefused",
    "winerror 10053",
    "winerror 10054",
    "winerror 10060",
    "winerror 10061",
    "winerror 11001",
)
"""다시 걸어 볼 만한 실패의 흔적. 없는 영상·지역 제한·404는 되풀이해야 시간만 버린다.

**WinError 번호를 넣는 이유는 윈도우가 소켓 오류 문구를 한국어로 내보내기 때문이다** -
'현재 연결은 원격 호스트에 의해 강제로 끊겼습니다'에는 영어가 한 글자도 없다. 띄어쓰기
없는 표기(connectionreset)는 파이썬 예외 이름이 그대로 찍히는 경우를 위한 것이다.
"""


def network_options() -> List[str]:
    """정보 조회용 yt-dlp 공통 옵션."""
    return ["--no-warnings",
            "--socket-timeout", SOCKET_TIMEOUT,
            "--retries", YTDLP_RETRIES,
            "--extractor-retries", YTDLP_RETRIES]


def is_retriable(stderr: str) -> bool:
    """다시 걸어 볼 만한 실패인지 오류 문구로 가른다."""
    text = (stderr or "").lower()
    return any(marker in text for marker in RETRIABLE_MARKERS)


ABORTED = "aborted"
"""부르는 쪽이 그만두라고 해서 끝났을 때의 오류 **코드**.

실패와 구별하려고 둔다. 받는 곳(metadata_prefetch._on_failed)이 아무것도 알리지 않고
물러나므로 화면에 나가지 않는다 - 문구가 아니라 코드인 것이 그래서다(상태 코드와 같다).
"""


def run(command: List[str], timeout: int, label: str,
        on_log: Optional[Callable[[str], None]] = None,
        on_spawn: Optional[Callable[[subprocess.Popen], None]] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> Tuple[bool, str, str]:
    """yt-dlp를 돌리고 (성공 여부, 표준 출력, 오류 문구)를 돌려준다.

    통신 문제로 보이면 지수 백오프로 다시 건다(제한 시간을 넘긴 경우는 제외).
    **중간에 그만두려면 두 갈고리가 함께 필요하다** - on_spawn은 갓 띄운 프로세스를 넘겨
    communicate()의 붙잡힘을 풀게 하고, should_stop은 죽인 뒤 오류 문구 때문에 다시 걸리는
    것을 막는다. 하나만 있으면 종료가 몇 초씩 늘어진다.
    """
    out = err = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if should_stop and should_stop():
            return False, "", ABORTED
        try:
            proc = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                startupinfo=get_startupinfo(), text=True,
                encoding="utf-8", errors="ignore"
            )
        except OSError as e:
            return False, "", t("ytdlp.spawn_failed", error=e)
        if on_spawn:
            on_spawn(proc)

        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return False, "", t("ytdlp.timeout", label=label, seconds=timeout)

        if proc.returncode == 0:
            return True, out, err
        if should_stop and should_stop():
            return False, "", ABORTED
        if attempt >= MAX_ATTEMPTS or not is_retriable(err):
            break

        delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
        if on_log:
            on_log(t("ytdlp.retry", seconds=delay, attempt=attempt + 1, total=MAX_ATTEMPTS))
        time.sleep(delay)
    return False, out, err
