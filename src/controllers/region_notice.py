"""지역 안내를 맡는다. 켤 때 IP 국가를 묻고, 네트워크가 바뀌면 다시 물어 달라진 것만 알린다.

**막지도 묻지도 않고 알리기만 한다** - VPN을 켰는지는 TVer에서 무엇을 하든 먼저 알아야 할 것이라
끄는 설정을 두지 않는다. 확인 스레드에 부모를 주지 않으므로 이 객체가 끝까지 참조를 들고 있는다
(놓으면 도는 채로 파괴된다). 창에서는 env_ready · append_notice · ui.set_notice만 빌려 쓴다.
"""

from PyQt6.QtCore import QTimer

from src.i18n import t
from src.net_watch import NetworkChangeWatcher
from src.threads.region_thread import (RegionCheckThread, JAPAN_CODE, STOP_WAIT_MS,
                                       country_name)


class RegionNotice:
    """IP 국가 확인과 그 안내를 맡는 조작 묶음."""

    PROBE_DELAYS_MS = (3_000, 12_000, 30_000)
    """네트워크가 바뀐 뒤 다시 물어보는 시점들(마지막 알림으로부터).

    **한 번만 물으면 아직 옛 나라가 온다.** VPN은 어댑터에 주소가 붙는 것과 통신이 실제로
    그쪽으로 도는 것 사이에 시차가 있어, 첫 알림이 오는 순간에는 아직 옮겨 가지 않았다.
    세 번이면 대개 잡히고 통신은 다 합쳐 750바이트다.

    **주기 확인이 아니다.** 네트워크가 바뀌지 않는 동안에는 이 타이머가 아예 돌지 않는다.
    """

    FALLBACK_KEYS = ("log.region_check_failed",
                     "log.region_fallback_restricted",
                     "log.region_fallback_vpn")
    """확인하지 못했을 때 내보내는 안내. 나라를 모르니 무엇을 하라고만 말한다.

    **여기서 조용히 넘어가면 안 된다** - 확인이 실패하는 상황은 대개 통신이 이상할 때라,
    VPN이 꺼져 있을 법한 자리이기도 하다. 모른다는 사실을 밝히고 예전 안내를 그대로 준다.
    문구가 아니라 번역 키를 담는 것은 클래스 상수라 값이 모듈 로드 시점에 굳기 때문이다.
    """

    def __init__(self, window):
        self.window = window
        self.thread = None
        self.watcher = None
        self._probe_timer = None
        self._probe_index = 0
        self._code = ""
        self._failed = False
        self._notified = None
        """마지막으로 알린 상태 - 국가 코드이거나, 확인 실패 안내를 냈다는 뜻의 빈 문자열.

        VPN을 켜고 끄면 같은 답이 여러 번 오므로 **무엇이 달라졌는지 여기서 가른다.**
        아무것도 알리지 않은 상태를 빈 문자열과 구별해야 해서 None으로 시작한다.
        """

    def start(self):
        """지금 IP가 일본인지 물어보러 보낸다. 준비를 기다리지 않는 것은 yt-dlp와 무관해서다."""
        self.thread = RegionCheckThread()
        self.thread.resolved.connect(self._on_resolved)
        self.thread.failed.connect(self._on_failed)
        self.thread.start()
        self._start_network_watch()

    def _start_network_watch(self):
        """네트워크가 바뀌는 것을 지켜보다가 그때만 다시 묻게 한다.

        **주기적으로 다시 묻지 않는 근거가 여기 있다**(사용자 지시, 2026-09-10). IP가
        달라지는 것은 네트워크가 바뀔 때뿐이라, 그 순간을 윈도우에게 얻어 오면 평소에
        치를 값이 없다. 걸지 못했으면 켤 때 한 번 물은 답이 그대로 남는다 - 오늘 이전과
        같은 상태이고, 그렇다고 앱이 못 돌 이유는 아니다.
        """
        self._probe_index = 0
        self._probe_timer = QTimer(self.window)
        self._probe_timer.setSingleShot(True)
        self._probe_timer.timeout.connect(self._fire_probe)
        self.watcher = NetworkChangeWatcher(self.window)
        self.watcher.changed.connect(self.on_network_changed)
        self.watcher.start()

    def on_network_changed(self):
        """네트워크가 바뀌었다. 자리잡을 틈을 두고 몇 번 물어본다.

        타이머를 다시 걸어 두는 것이 곧 디바운스다 - VPN이 붙는 동안 알림이 잇달아 오는데,
        그때마다 묻지 않고 **마지막 알림을 기준으로** 세 번만 묻는다.
        """
        if self._probe_timer is None:
            return
        self._probe_index = 0
        self._probe_timer.start(self.PROBE_DELAYS_MS[0])

    def _fire_probe(self):
        """지금 한 번 묻고, 남은 시점이 있으면 그 간격만큼 다시 건다."""
        if self.thread is None or self._probe_timer is None:
            return
        self.thread.request_recheck()
        self._probe_index += 1
        delays = self.PROBE_DELAYS_MS
        if self._probe_index < len(delays):
            self._probe_timer.start(delays[self._probe_index] - delays[self._probe_index - 1])

    def _on_resolved(self, country_code: str):
        """알아낸 국가를 적어 둔다. 알릴지는 준비가 끝났는지와 달라졌는지에 달렸다."""
        self._code = country_code
        self.show()

    def _on_failed(self):
        """못 물어봤다. **이미 무언가 알렸으면 아무 말도 하지 않는다.**

        VPN을 켜고 끄는 그 순간에는 통신이 잠깐 끊겨 확인이 실패하는데, 그때마다 '확인에
        실패했다'를 내보내면 정작 나라가 바뀐 안내가 그 줄들에 묻힌다. 모르는 동안에는
        마지막으로 알아낸 나라가 그대로 서 있는 것이 맞다.
        """
        if self._notified is not None:
            return
        self._failed = True
        self.show()

    def show(self):
        """지역 안내를 로그 맨 아래에 붙인다. 알리기만 하고 아무것도 막지 않는다.

        준비가 끝난 뒤로 미루는 것은 yt-dlp·FFmpeg 확인 줄 사이에 끼면 읽는 차례가 끊기기
        때문이다. 답이 온 것과 준비가 끝난 것 중 늦게 오는 쪽이 이 함수를 부른다.
        **IP는 어디에도 적지 않는다** - 로그를 그대로 붙여 도움을 청하는 자리가 있다.

        **나라가 달라졌을 때만 다시 붙인다.** 같은 답을 그대로 찍으면 로그가 그 줄로 차고,
        위에서 아래로 읽는 흐름도 끊긴다. 문구를 새로 만들지 않은 것은 지금 어디인지를
        말하는 글이 언제 붙어도 그대로 통하기 때문이다.
        """
        if not self.window.env_ready:
            return
        state = self._code or ("" if self._failed else None)
        if state is None or state == self._notified:
            return
        lines, color_key = self.message(state)
        self._notified = state
        self.window.append_notice(t("log.heading_notice"), lines, color_key=color_key)

    def message(self, state: str):
        """알릴 상태(국가 코드, 실패면 빈 문자열)를 지금 언어의 안내 줄과 색으로 바꾼다."""
        if state == JAPAN_CODE:
            return [t("log.region_ok")], "log_success"
        if state:
            return [t("log.region_not_japan"),
                    t("log.region_use_vpn", country=country_name(state)),
                    t("log.region_restricted")], "notice"
        return [t(key) for key in self.FALLBACK_KEYS], "notice"

    def retranslate(self):
        """목록 위 안내 줄만 새 언어로 다시 쓴다. 로그에 같은 안내를 또 붙이지 않는다."""
        if self._notified is None:
            return
        lines, color_key = self.message(self._notified)
        self.window.ui.set_notice(lines[0], color_key)

    def stop(self):
        """지역 확인을 거둔다. 아직 답을 기다리는 중이면 그 답을 버리고 그냥 끝낸다.

        오래 기다리지 않는 것은 DNS가 막힌 회선에서 십수 초가 걸리기 때문이다 - 부모 없는
        스레드라 도는 채로 두어도 프로세스가 그대로 끝난다.

        **네트워크 감시를 먼저 거둔다.** 그쪽 등록을 남긴 채 프로세스가 끝나면 윈도우가
        이미 사라진 콜백을 부르러 온다.
        """
        if self.watcher is not None:
            self.watcher.stop()
        if self._probe_timer is not None:
            self._probe_timer.stop()
        if self.thread is None:
            return
        self.thread.stop()
        self.thread.wait(STOP_WAIT_MS)
