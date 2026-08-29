"""현재 공인 IP가 어느 나라인지 한 번 물어보는 스레드.

TVer는 일본 지역 제한이 있어 VPN 없이 받으면 전부 실패하는데, 지금은 받기 시작해서
실패해야 그것을 안다. 켤 때 로그에 한 줄 알려 주자는 것이 전부다 - 막지도 묻지도 않는다.

**실패는 통째로 조용히 넘긴다.** 안내지 관문이라서가 아니다. 못 물어본 것을 '일본이
아니다'로 읽으면 VPN을 켜 둔 사람에게 껐다고 알리게 되어, 실패 방향이 가장 나쁘다.
"""
from __future__ import annotations

from typing import Optional

import requests
from PyQt6.QtCore import QThread, pyqtSignal

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


COUNTRY_NAMES = {
    "JP": "일본", "KR": "대한민국", "US": "미국", "CN": "중국", "TW": "대만",
    "HK": "홍콩", "MO": "마카오", "SG": "싱가포르", "MY": "말레이시아",
    "TH": "태국", "VN": "베트남", "PH": "필리핀", "ID": "인도네시아",
    "IN": "인도", "PK": "파키스탄", "BD": "방글라데시", "NP": "네팔",
    "LK": "스리랑카", "MM": "미얀마", "KH": "캄보디아", "LA": "라오스",
    "MN": "몽골", "KZ": "카자흐스탄", "UZ": "우즈베키스탄",
    "GB": "영국", "IE": "아일랜드", "FR": "프랑스", "DE": "독일",
    "NL": "네덜란드", "BE": "벨기에", "LU": "룩셈부르크", "CH": "스위스",
    "AT": "오스트리아", "IT": "이탈리아", "ES": "스페인", "PT": "포르투갈",
    "SE": "스웨덴", "NO": "노르웨이", "DK": "덴마크", "FI": "핀란드",
    "IS": "아이슬란드", "PL": "폴란드", "CZ": "체코", "SK": "슬로바키아",
    "HU": "헝가리", "RO": "루마니아", "BG": "불가리아", "GR": "그리스",
    "HR": "크로아티아", "SI": "슬로베니아", "RS": "세르비아", "UA": "우크라이나",
    "RU": "러시아", "BY": "벨라루스", "LT": "리투아니아", "LV": "라트비아",
    "EE": "에스토니아", "MD": "몰도바", "AL": "알바니아", "CY": "키프로스",
    "MT": "몰타", "TR": "튀르키예",
    "CA": "캐나다", "MX": "멕시코", "BR": "브라질", "AR": "아르헨티나",
    "CL": "칠레", "CO": "콜롬비아", "PE": "페루", "VE": "베네수엘라",
    "EC": "에콰도르", "UY": "우루과이", "PA": "파나마", "CR": "코스타리카",
    "GT": "과테말라", "DO": "도미니카 공화국",
    "AU": "호주", "NZ": "뉴질랜드",
    "AE": "아랍에미리트", "SA": "사우디아라비아", "QA": "카타르",
    "KW": "쿠웨이트", "BH": "바레인", "OM": "오만", "IL": "이스라엘",
    "JO": "요르단", "IQ": "이라크", "IR": "이란",
    "EG": "이집트", "ZA": "남아프리카 공화국", "NG": "나이지리아",
    "KE": "케냐", "MA": "모로코", "TN": "튀니지", "DZ": "알제리",
    "GH": "가나", "ET": "에티오피아",
}
"""국가 코드를 한국어 이름으로. VPN 출구로 흔한 곳과 주요국을 담았다.

전 세계를 다 적지 않는 것은 여기 없는 코드가 나와도 코드 그대로 보여 주면 뜻이 통하기
때문이다. 이름을 못 찾았다고 안내를 거르는 쪽이 훨씬 나쁘다.
"""


def country_name(code: str) -> str:
    """국가 코드를 사람이 읽을 이름으로. 표에 없으면 코드를 그대로 돌려준다."""
    key = (code or "").strip().upper()
    return COUNTRY_NAMES.get(key, key)


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
    """공인 IP의 국가를 한 번 물어보고, 알아낸 때만 알린다."""

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

    def stop(self):
        """받아 온 답을 버린다. 통신은 곧 제한 시간에 걸려 스스로 끝난다."""
        self._stop_flag = True

    def run(self):
        code = self._lookup()
        if self._stop_flag:
            return
        if code:
            self.resolved.emit(code)
        else:
            self.failed.emit()

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
