"""현재 공인 IP가 어느 나라인지 되풀이해 물어보는 스레드.

TVer는 일본 지역 제한이 있어 VPN 없이 받으면 전부 실패하는데, 지금은 받기 시작해서
실패해야 그것을 안다. 로그에 한 줄 알려 주자는 것이 전부다 - 막지도 묻지도 않는다.

**한 번만 묻지 않는 것은 VPN이 앱보다 늦게 켜지기 때문이다.** 켤 때 물은 답을 그대로
들고 있으면 나중에 VPN을 켠 사람에게 앱을 껐다 켜라고 요구하게 된다(사용자 지적).

**실패는 통째로 조용히 넘긴다.** 안내지 관문이라서가 아니다. 못 물어본 것을 '일본이
아니다'로 읽으면 VPN을 켜 둔 사람에게 껐다고 알리게 되어, 실패 방향이 가장 나쁘다.
"""
from __future__ import annotations

from typing import Optional

import requests
from PyQt6.QtCore import QMutex, QThread, QWaitCondition, pyqtSignal

from src.i18n import t

TRACE_URL = "https://www.cloudflare.com/cdn-cgi/trace"
"""국가를 물어보는 곳. 무료 티어를 둔 상품이 아니라 Cloudflare가 프록시 사이트마다 깔아
두는 진단 통로라, 갑자기 유료화되거나 사라질 걱정이 후보 중 가장 적다(실측 0.19초/250바이트).
"""

USER_AGENT = "TVerDownloader-RegionCheck"
"""어디서 온 요청인지 밝힌다. github_api_headers에 주체별 이름을 주는 것과 같은 이유다."""

COUNTRY_FIELD = "loc"
"""국가 코드가 담기는 줄의 이름. 응답은 JSON이 아니라 한 줄에 하나씩인 key=value다."""

JAPAN_CODE = "JP"
"""TVer를 볼 수 있는 나라. 여기가 아니면 VPN이 꺼진 것으로 본다."""

TIMEOUT = (2, 2)
"""(연결, 읽기) 제한 시간(초). 시작이 느려지면 안 되고, 늦게 온 답은 쓸모도 없다."""

MAX_BODY_BYTES = 4096
"""읽어 들일 최대 크기. 호텔·카페 로그인 페이지가 가로채면 HTML 한 장이 통째로 온다."""

STOP_WAIT_MS = 300
"""끝낼 때 스레드가 빠져나오기를 기다리는 시간(ms). 대개는 답이 이미 와 있어 곧장 돌아온다.

길게 잡을 이유가 없다 - 스레드에 부모를 두지 않아, 답을 기다리는 중이어도 프로세스는
그대로 끝난다. DNS가 막힌 회선에서는 TIMEOUT과 무관하게 십수 초가 걸려(실측 11초)
어차피 기다릴 수 없다.
"""



def country_name(code: str) -> str:
    """국가 코드를 지금 언어의 이름으로. 표에 없으면 코드를 그대로 돌려준다.

    이름표는 lang/*.ini의 [country]에 있다 - 화면에 보이는 글이라 다른 문구와 같은 자리에
    두어야 한다(예전에는 여기 한국어 표로 박혀 있어 영어 화면에 '대한민국'이 섞여 나왔다).
    **키는 소문자다** - configparser가 옵션 이름을 소문자로 접는다.
    t()는 못 찾으면 키 문자열을 돌려주므로, 그때는 코드만 남겨 예전 동작을 지킨다.
    """
    key = (code or "").strip().upper()
    if not key:
        return key
    lookup = f"country.{key.lower()}"
    name = t(lookup)
    return key if name == lookup else name


def parse_country(body: str) -> Optional[str]:
    """응답에서 두 글자 국가 코드를 꺼낸다. 없거나 두 글자가 아니면 None.

    Cloudflare는 알 수 없으면 그 줄을 빼고 Tor 출구에는 'T1'을 준다 - 그런 값이 나라로
    읽히지 않도록 아스키 알파벳 두 글자만 받는다.
    """
    for line in body.splitlines():
        key, sep, value = line.partition("=")
        if not sep or key.strip() != COUNTRY_FIELD:
            continue
        code = value.strip().upper()
        return code if len(code) == 2 and code.isascii() and code.isalpha() else None
    return None


class RegionCheckThread(QThread):
    """공인 IP의 국가를 되풀이해 물어보고, 알아낸 때마다 알린다.

    **같은 답이 또 와도 그대로 알린다.** 무엇이 달라졌는지 가르는 일은 창이 한다 - 이쪽은
    지금 어디인지를 관측할 뿐이고, 어떤 안내를 이미 내보냈는지는 여기서 알 길이 없다.
    """

    resolved = pyqtSignal(str)
    """알아낸 두 글자 국가 코드. 실패했을 때는 이쪽이 나오지 않는다."""

    failed = pyqtSignal()
    """물어보지 못했다. **resolved와 반드시 갈라 둔다** - 모르는 것과 일본이 아닌 것은 다르다.

    이유는 싣지 않는다. 사용자가 손댈 것이 없고, 부르는 쪽이 하는 일도 문구 하나로 같다.
    """

    def __init__(self):
        """**부모를 받지 않는다.** 창의 자식으로 두면 답을 기다리는 중에 창이 헐릴 때
        QThread가 파괴되어 프로세스가 그 자리에서 죽는다(실측: 부모 있으면 종료 코드 127).
        """
        super().__init__()
        self._stop_flag = False
        self._pending = False
        self._mutex = QMutex()
        self._wake = QWaitCondition()

    def stop(self):
        """받아 온 답을 버리고 기다리는 중이면 곧장 깨운다.

        **깨우지 않으면 스레드가 영원히 기다린다.** 다음 요청이 올 때까지 시간 제한 없이
        멎어 있는 구조라, 끝내라는 뜻을 같은 조건 변수로 전해야 빠져나온다.
        """
        self._stop_flag = True
        self._wake.wakeAll()

    def request_recheck(self):
        """다시 물어보라고 시킨다. 네트워크가 바뀌었을 때 창이 부른다.

        **확인하는 중에 와도 잃지 않는다** - 깃발을 세워 두면 이번 확인을 마친 스레드가
        기다리지 않고 곧바로 한 번 더 묻는다. VPN이 붙는 동안 알림이 잇달아 오는 자리다.
        """
        self._mutex.lock()
        self._pending = True
        self._wake.wakeAll()
        self._mutex.unlock()

    def run(self):
        while not self._stop_flag:
            code = self._lookup()
            if self._stop_flag:
                return
            if code:
                self.resolved.emit(code)
            else:
                self.failed.emit()
            self._await_request()

    def _await_request(self):
        """다시 물어보라는 말이 올 때까지 기다린다. **시간 제한을 두지 않는다.**

        주기적으로 깨어날 이유가 없다 - IP가 달라지는 것은 네트워크가 바뀔 때뿐이고 그것은
        `net_watch`가 알려 준다. 기다리는 동안 이 스레드가 쓰는 것은 아무것도 없다.
        """
        self._mutex.lock()
        try:
            while not self._stop_flag and not self._pending:
                self._wake.wait(self._mutex)
            self._pending = False
        finally:
            self._mutex.unlock()

    def _lookup(self) -> Optional[str]:
        """국가 코드를 받아 온다. 무엇이 잘못되든 None.

        예외를 종류로 가르지 않는 것은 통신 실패든 형식 변경이든 결론이 같아서다 - 알리지
        않고 넘어간다.
        """
        try:
            with requests.get(TRACE_URL, headers={"User-Agent": USER_AGENT},
                              timeout=TIMEOUT, stream=True) as response:
                if response.status_code != 200:
                    return None
                body = response.raw.read(MAX_BODY_BYTES, decode_content=True)
        except Exception:
            return None
        return parse_country(bytes(body or b"").decode("utf-8", "replace"))
