"""yt-dlp에 정보를 물어볼 때 쓰는 공통 규칙.

파일을 받는 쪽은 `--retries 10`으로 오래 버티는데, 정보를 물어보는 쪽(시리즈 분석,
다운로드 직전 메타데이터)은 한 번에 포기하고 있었다. 분석이 도는 동안 다운로드가
함께 돌면 회선을 나눠 쓰게 되고, 그때 statics.tver.jp가 기본 20초 안에 응답하지
못해 `Read timed out`으로 떨어진다. 사용자가 시리즈를 확인하는 중에 다른 주소를
넣었을 때 유독 자주 나던 이유가 이것이다.

두 조회 경로가 같은 조건으로 버텨야 해서 규칙을 한곳에 모은다. 한쪽만 고쳐 두면
어느 경로로 들어왔느냐에 따라 결과가 달라진다.
"""
from __future__ import annotations

import subprocess
import time
from typing import Callable, List, Optional, Tuple

from src.utils import get_startupinfo

SOCKET_TIMEOUT = "30"
"""yt-dlp에 넘길 소켓 제한 시간(초). 기본값 20초를 늘려 잡는다.

프로세스를 다시 띄우는 것보다 이쪽이 싸다. 서버가 죽은 것이 아니라 느릴 뿐이면
여기서 끝난다.
"""

YTDLP_RETRIES = "3"
"""yt-dlp 자체 재시도 횟수. 프로세스를 다시 띄우기 전에 안에서 먼저 버틴다."""

MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 3
"""일시적인 통신 오류일 때만 쓰는 지수 백오프. 3초 → 6초.

한 번 걸렸다고 시리즈 하나를 통째로 버리면, 시작할 때 도는 즐겨찾기 확인에서
그 시리즈만 조용히 빠진다. 사용자는 새 회차가 없는 줄로 안다.
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
"""다시 걸어 볼 만한 실패의 흔적.

없는 영상·지역 제한·404처럼 몇 초 뒤에도 같을 실패까지 되풀이하면 시간만 버린다.
통신이 끊겼다는 표시가 나왔을 때만 다시 건다. "http error 5"는 5xx만 걸리고
404는 걸리지 않는다.

WinError 번호를 함께 넣는 이유는 **윈도우가 소켓 오류 문구를 한국어로 내보내기
때문이다.** '현재 연결은 원격 호스트에 의해 강제로 끊겼습니다'에는 영어 표시가
하나도 없어, 번호를 보지 않으면 통신 문제인 줄 모르고 그냥 포기하게 된다.
10053 연결 중단 · 10054 연결 끊김 · 10060 시간 초과 · 10061 연결 거부 ·
11001 호스트를 찾지 못함.

띄어쓰기가 없는 표기(connectionreset)도 함께 둔다. 파이썬 예외 이름이 그대로
찍히는 경우(ConnectionResetError)가 있어 'connection reset'으로는 걸리지 않는다.
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


def run(command: List[str], timeout: int, label: str,
        on_log: Optional[Callable[[str], None]] = None) -> Tuple[bool, str, str]:
    """yt-dlp를 돌리고 (성공 여부, 표준 출력, 오류 문구)를 돌려준다.

    통신 문제로 보이면 지수 백오프로 다시 건다. 제한 시간을 넘긴 경우는 다시 걸지
    않는다. --socket-timeout이 있어 정상적인 실패는 그보다 훨씬 빨리 돌아오므로,
    여기까지 왔다면 몇 분을 더 기다린다고 달라질 상황이 아니다.

    부르는 쪽이 모두 작업 스레드라 여기서 그냥 자도 화면은 멈추지 않는다.
    """
    out = err = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            proc = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                startupinfo=get_startupinfo(), text=True,
                encoding="utf-8", errors="ignore"
            )
        except OSError as e:
            return False, "", f"yt-dlp를 실행하지 못했습니다: {e}"

        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return False, "", f"{label}이(가) 제한 시간 {timeout}초를 넘겨 중단했습니다."

        if proc.returncode == 0:
            return True, out, err
        if attempt >= MAX_ATTEMPTS or not is_retriable(err):
            break

        delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
        if on_log:
            on_log(f" ... 통신이 원활하지 않습니다. {delay}초 후 다시 시도합니다"
                   f" ({attempt + 1}/{MAX_ATTEMPTS}).")
        time.sleep(delay)
    return False, out, err
