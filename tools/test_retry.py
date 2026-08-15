import subprocess
import sys
import time

import _bootstrap
_bootstrap.setup()

from src.threads import ytdlp_run
from src.threads.download_thread import DownloadThread
from src.threads.series_parse_thread import SeriesParseThread

results = []

TIMEOUT_ERROR = (
    "ERROR: [TVer] ep6q9y33zb: Unable to download JSON metadata: "
    "HTTPSConnectionPool(host='statics.tver.jp', port=443): Read timed out. "
    "(read timeout=20.0) (caused by TransportError(\"HTTPSConnectionPool("
    "host='statics.tver.jp', port=443): Read timed out. (read timeout=20.0)\"))"
)


def report(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


class FakeProc:
    """정해 둔 결과를 돌려주는 가짜 yt-dlp 프로세스."""

    def __init__(self, returncode, out, err, hang=False):
        self.returncode = returncode
        self._out = out
        self._err = err
        self._hang = hang
        self.killed = False

    def communicate(self, timeout=None):
        if self._hang:
            self._hang = False
            raise subprocess.TimeoutExpired("yt-dlp", timeout)
        return self._out, self._err

    def kill(self):
        self.killed = True


class Popen:
    """Popen 자리를 대신하며 부른 명령과 돌려줄 결과를 기록한다."""

    def __init__(self, results):
        self.results = list(results)
        self.commands = []
        self.procs = []

    def __call__(self, command, **kwargs):
        self.commands.append(list(command))
        proc = self.results.pop(0)
        self.procs.append(proc)
        return proc


print("=== 1. 다시 걸 실패와 그러지 않을 실패 ===")
report("보고된 그 오류를 다시 걸 대상으로 본다", ytdlp_run.is_retriable(TIMEOUT_ERROR) is True)
for text in ("Read timed out. (read timeout=20.0)",
             "ConnectionResetError(10054, ...)",
             "Remote end closed connection without response",
             "Max retries exceeded with url",
             "HTTP Error 503: Service Unavailable",
             "Temporary failure in name resolution",
             "<urlopen error [WinError 10054] 현재 연결은 원격 호스트에 의해 "
             "강제로 끊겼습니다>",
             "[WinError 11001] 이러한 호스트가 없습니다"):
    report(f"다시 건다: {text[:40]}", ytdlp_run.is_retriable(text) is True)

for text in ("ERROR: [TVer] Video unavailable",
             "ERROR: HTTP Error 404: Not Found",
             "ERROR: This video is not available in your country",
             "ERROR: Unsupported URL: https://example.com/x",
             ""):
    report(f"포기한다: {text[:40] or '(빈 오류)'}", ytdlp_run.is_retriable(text) is False)

print()
print("=== 2. 지수 백오프로 다시 건다 ===")
real_popen, real_sleep = subprocess.Popen, time.sleep
logs, sleeps = [], []
fake = Popen([FakeProc(1, "", TIMEOUT_ERROR),
              FakeProc(1, "", TIMEOUT_ERROR),
              FakeProc(0, '{"title": "ok"}', "")])
ytdlp_run.subprocess.Popen = fake
ytdlp_run.time.sleep = lambda s: sleeps.append(s)
try:
    ok, out, err = ytdlp_run.run(["yt-dlp", "-J", "url"], 60, "시리즈 1차 분석", logs.append)
finally:
    ytdlp_run.subprocess.Popen = real_popen
    ytdlp_run.time.sleep = real_sleep

report("세 번째에 성공한다", ok and out == '{"title": "ok"}', f"{ok} {out!r}")
report("세 번 걸었다", len(fake.commands) == 3, f"{len(fake.commands)}회")
report("3초 → 6초로 쉬었다", sleeps == [3, 6], f"{sleeps}")
report("다시 건다는 것을 로그로 알린다", len(logs) == 2 and "다시 시도" in logs[0], f"{logs}")
report("몇 번째인지도 알린다", "(2/3)" in logs[0] and "(3/3)" in logs[1], f"{logs}")

logs, sleeps = [], []
fake = Popen([FakeProc(1, "", TIMEOUT_ERROR)] * 3)
ytdlp_run.subprocess.Popen = fake
ytdlp_run.time.sleep = lambda s: sleeps.append(s)
try:
    ok, out, err = ytdlp_run.run(["yt-dlp", "-J", "url"], 60, "시리즈 1차 분석", logs.append)
finally:
    ytdlp_run.subprocess.Popen = real_popen
    ytdlp_run.time.sleep = real_sleep

report("끝내 안 되면 실패로 돌려준다", ok is False)
report("세 번까지만 건다", len(fake.commands) == ytdlp_run.MAX_ATTEMPTS, f"{len(fake.commands)}회")
report("마지막 실패 뒤에는 쉬지 않는다", sleeps == [3, 6], f"{sleeps}")
report("원래 오류 문구를 그대로 넘긴다", "Read timed out" in err)

logs, sleeps = [], []
fake = Popen([FakeProc(1, "", "ERROR: HTTP Error 404: Not Found")])
ytdlp_run.subprocess.Popen = fake
ytdlp_run.time.sleep = lambda s: sleeps.append(s)
try:
    ok, out, err = ytdlp_run.run(["yt-dlp", "-J", "url"], 60, "시리즈 1차 분석", logs.append)
finally:
    ytdlp_run.subprocess.Popen = real_popen
    ytdlp_run.time.sleep = real_sleep

report("고쳐질 리 없는 실패는 한 번만 건다", len(fake.commands) == 1 and not ok, f"{len(fake.commands)}회")
report("그때는 쉬지도 알리지도 않는다", sleeps == [] and logs == [])

print()
print("=== 3. 제한 시간을 넘기면 죽이고 끝낸다 ===")
logs, sleeps = [], []
hung = FakeProc(0, "", "", hang=True)
fake = Popen([hung, FakeProc(0, "{}", "")])
ytdlp_run.subprocess.Popen = fake
ytdlp_run.time.sleep = lambda s: sleeps.append(s)
try:
    ok, out, err = ytdlp_run.run(["yt-dlp", "-J", "url"], 300, "시리즈 1차 분석", logs.append)
finally:
    ytdlp_run.subprocess.Popen = real_popen
    ytdlp_run.time.sleep = real_sleep

report("멈춘 프로세스를 죽인다", hung.killed)
report("다시 걸지 않는다", len(fake.commands) == 1, f"{len(fake.commands)}회")
report("무엇이 시간을 넘겼는지 알려 준다",
       "시리즈 1차 분석" in err and "300초" in err, f"{err!r}")

print()
print("=== 4. 두 조회 경로가 같은 옵션을 쓴다 ===")
options = ytdlp_run.network_options()
report("소켓 제한 시간을 30초로 올렸다",
       "--socket-timeout" in options
       and options[options.index("--socket-timeout") + 1] == "30", f"{options}")
report("yt-dlp 자체 재시도도 켠다",
       "--retries" in options and "--extractor-retries" in options, f"{options}")

series_source = (_bootstrap.ROOT / "src" / "threads" / "series_parse_thread.py").read_text(encoding="utf-8")
report("시리즈 분석 세 갈래가 모두 공통 옵션을 쓴다",
       series_source.count("ytdlp_run.network_options()") == 3,
       f"{series_source.count('ytdlp_run.network_options()')}곳")
report("시리즈 분석이 직접 Popen을 부르지 않는다", "subprocess.Popen" not in series_source)
report("전체 분석에도 제한 시간이 생겼다", SeriesParseThread.PARSE_TIMEOUT == 300)
report("시리즈 분석 세 갈래가 모두 --skip-download",
       series_source.count("--skip-download") == 3,
       f"{series_source.count('--skip-download')}곳")

download_source = (_bootstrap.ROOT / "src" / "threads" / "download_thread.py").read_text(encoding="utf-8")
report("다운로드 직전 조회도 같은 옵션을 쓴다",
       "ytdlp_run.network_options()" in download_source)
report("조회 제한 시간이 20초에서 늘었다", DownloadThread.METADATA_TIMEOUT == 60)
report("받는 명령은 예전 그대로 --retries 10",
       '"--retries", "10", "--fragment-retries", "10"' in download_source)

print()
print("ALL PASS" if all(results) else f"SOME FAILED ({results.count(False)}건)")
sys.exit(0 if all(results) else 1)
