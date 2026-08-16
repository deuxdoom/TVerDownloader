"""썸네일 스레드 대기열이 지워진 스레드를 밟고 죽지 않는지 본다.

재현 조건은 '한 번에 쏟아지는 요청'이다. 기록 탭은 새로 고칠 때마다
history_list.clear() 뒤에 최대 100개의 카드를 다시 만들고, 카드마다
썸네일을 건다. 여섯 개만 돌고 나머지는 대기열에 쌓이므로 finished가
연달아 터지는 상황이 그대로 만들어진다.

네트워크는 쓰지 않는다. run()을 짧은 sleep으로 바꿔 끼워도 문제의 경주는
그대로 재현된다 - 깨지는 자리는 내려받기가 아니라 finished 뒤의 뒷정리다.
"""
import sys
import time

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QApplication

app = QApplication(sys.argv)

import _bootstrap
_bootstrap.setup()

from src import widgets

results = []


def report(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


def fake_run(self):
    """실제 통신 대신 잠깐 쉬었다가 같은 모양의 결과를 낸다."""
    time.sleep(0.004)
    self.loaded.emit((self.url, None))


widgets.ThumbnailDownloader.run = fake_run

crashes = []
_original_hook = sys.excepthook


def record(exc_type, exc, tb):
    crashes.append(f"{exc_type.__name__}: {exc}")


sys.excepthook = record

original_sweep = widgets._ThumbCoordinator.on_thread_finished
dead_seen = []


def watched_sweep(self):
    """훑는 도중 이미 지워진 스레드가 실제로 나오는지 세어 둔다.

    이 수가 0이면 경주가 재현되지 않은 것이라, 통과해도 의미가 없다.
    """
    for thread in list(widgets._running_thumb_threads):
        if widgets.sip.isdeleted(thread):
            dead_seen.append(1)
    return original_sweep(self)


widgets._ThumbCoordinator.on_thread_finished = watched_sweep


class QSink(QObject):
    """수신자가 QObject 바운드 메서드여야 한다는 조건을 맞추기 위한 그릇."""

    def on_loaded(self, result):
        pass


sink = QSink()
BURST = 40
ROUNDS = 12
rounds = [0]


def burst():
    rounds[0] += 1
    for i in range(BURST):
        widgets.start_thumbnail_download(f"https://example.invalid/{rounds[0]}-{i}.jpg",
                                         sink.on_loaded)
    if rounds[0] >= ROUNDS:
        timer.stop()
        QTimer.singleShot(600, app.quit)


timer = QTimer()
timer.timeout.connect(burst)
timer.start(30)
QTimer.singleShot(8000, app.quit)
app.exec()

sys.excepthook = _original_hook
widgets._ThumbCoordinator.on_thread_finished = original_sweep

report("경주가 실제로 재현됐다 (지워진 스레드를 훑는 중 만남)", bool(dead_seen),
       f"만난 횟수 {len(dead_seen)}")
report("뒷정리 중 RuntimeError가 나지 않는다", not crashes,
       "; ".join(crashes[:3]))
report("끝난 뒤 대기열이 비어 있다", not widgets._pending_thumbs,
       f"남은 대기 {len(widgets._pending_thumbs)}")

for leftover in list(widgets._running_thumb_threads):
    if not widgets.sip.isdeleted(leftover):
        leftover.wait(2000)

print()
print("ALL PASS" if all(results) else "SOME FAILED")
sys.exit(0 if all(results) else 1)
