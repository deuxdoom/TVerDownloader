import sys
from datetime import datetime

from PyQt6.QtCore import QCoreApplication

import requests

import _bootstrap
_bootstrap.setup()

from src.threads.setup_thread import SetupThread
from src.utils import is_rate_limited, rate_limit_message

app = QCoreApplication(sys.argv)

RESET_EPOCH = int(datetime(2026, 8, 14, 21, 30, 0).timestamp())


class FakeResponse:
    def __init__(self, status, headers=None, payload=None, bad_json=False):
        self.status_code = status
        self.headers = requests.structures.CaseInsensitiveDict(headers or {})
        self._payload = payload
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._payload


class Probe(SetupThread):
    """실제로 자지 않고 대기 시간만 기록한다."""

    def __init__(self):
        super().__init__(None)
        self.slept = []
        self.logs = []
        self.log.connect(self.logs.append)

    def msleep(self, ms):
        self.slept.append(ms // 1000)


def run(name, responses, expect_result, expect_attempts, expect_sleeps):
    probe = Probe()
    calls = {"n": 0}
    captured = {}

    def fake_get(url, **kwargs):
        calls["n"] += 1
        captured["headers"] = kwargs.get("headers")
        item = responses[min(calls["n"] - 1, len(responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    original = requests.get
    requests.get = fake_get
    try:
        result = probe._get_api_info("https://api.github.com/x")
    finally:
        requests.get = original

    ok = (result == expect_result and calls["n"] == expect_attempts
          and probe.slept == expect_sleeps)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"        요청 {calls['n']}회, 대기 {probe.slept}, 결과 {result!r}")
    if captured.get("headers"):
        print(f"        헤더 {dict(captured['headers'])}")
    for line in probe.logs:
        print(f"        | {line}")
    return ok


results = []

results.append(run(
    "200 정상",
    [FakeResponse(200, payload={"tag_name": "v1.2.3"})],
    {"tag_name": "v1.2.3"}, 1, []))

results.append(run(
    "403 + Remaining:0  -> 재시도 없이 즉시 중단",
    [FakeResponse(403, {"X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(RESET_EPOCH)})],
    None, 1, []))

results.append(run(
    "429 + Remaining:0  -> 재시도 없이 즉시 중단",
    [FakeResponse(429, {"X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(RESET_EPOCH)})],
    None, 1, []))

results.append(run(
    "403 이지만 Remaining 있음 -> 한도 아님, 재시도 없음",
    [FakeResponse(403, {"X-RateLimit-Remaining": "37"})],
    None, 1, []))

results.append(run(
    "네트워크 오류 3회 -> 3초, 6초 백오프",
    [requests.exceptions.ConnectionError("no route to host")],
    None, 3, [3, 6]))

results.append(run(
    "네트워크 오류 후 2번째에 복구",
    [requests.exceptions.Timeout("timed out"),
     FakeResponse(200, payload={"tag_name": "v9"})],
    {"tag_name": "v9"}, 2, [3]))

results.append(run(
    "500 서버 오류 -> 백오프 재시도",
    [FakeResponse(500)],
    None, 3, [3, 6]))

results.append(run(
    "404 -> 재시도 무의미, 즉시 중단",
    [FakeResponse(404)],
    None, 1, []))

results.append(run(
    "200 이지만 JSON 깨짐 -> 재시도 없이 중단",
    [FakeResponse(200, bad_json=True)],
    None, 1, []))

print()
limited = FakeResponse(403, {"X-RateLimit-Remaining": "0",
                             "X-RateLimit-Reset": str(RESET_EPOCH)})
print("리셋 시각 변환:", rate_limit_message(limited))
no_header = FakeResponse(403, {"X-RateLimit-Remaining": "0"})
print("Reset 헤더 없음:", rate_limit_message(no_header))
junk = FakeResponse(403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "nonsense"})
print("Reset 헤더 이상:", rate_limit_message(junk))
print("소문자 헤더도 인식:", is_rate_limited(
    FakeResponse(403, {"x-ratelimit-remaining": "0"})))

print()
print("ALL PASS" if all(results) else "SOME FAILED")
sys.exit(0 if all(results) else 1)
