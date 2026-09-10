"""네트워크 주소·경로가 바뀌었다고 윈도우가 알려 주는 것을 받아 신호로 바꾼다.

IP 국가를 주기적으로 다시 묻는 대신 이것을 쓴다 - VPN을 켜면 가상 어댑터에 주소가 붙고
기본 경로가 그쪽으로 돌아가므로, **그 순간에만 한 번 물어보면 된다.** 평소에는 콜백이
오지 않아 값을 치를 것이 아무것도 없다(실측: 등록해 둔 채 10초 동안 0건).

주기 확인(30초 간격)을 먼저 만들었다가 걷어냈다 - 하루를 켜 두면 2,880번을 묻는데 그중
쓸모 있는 것은 VPN을 켠 직후 한 번뿐이다(사용자 지적).
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PyQt6.QtCore import QObject, pyqtSignal

AF_UNSPEC = 0
"""IPv4·IPv6을 가리지 않고 받는다. VPN이 어느 쪽으로 붙든 알아야 한다."""

_CALLBACK = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int)
"""(CallerContext, Row, NotificationType). 무엇이 바뀌었는지는 보지 않는다 - 바뀌었다는
사실만으로 다시 물어보면 되고, Row를 뜯으면 구조체 정의를 판마다 따라가야 한다."""

_NOTIFY_ARGTYPES = [ctypes.c_ushort, _CALLBACK, ctypes.c_void_p, ctypes.c_ubyte,
                    ctypes.POINTER(wintypes.HANDLE)]


class NetworkChangeWatcher(QObject):
    """네트워크가 바뀔 때마다 `changed`를 낸다. 시작하지 못하면 조용히 아무 일도 하지 않는다.

    **콜백은 윈도우 스레드 풀에서 불린다.** 그래서 거기서 하는 일을 시그널 하나로 줄였다 -
    Qt가 큐 연결로 창 스레드에 넘겨 주므로 위젯을 만지는 코드는 제자리에서 돈다.
    """

    changed = pyqtSignal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._handles: list[wintypes.HANDLE] = []
        self._callbacks: list = []
        """**콜백 객체를 여기 붙잡아 둔다.** 지역 변수로 두면 파이썬이 거둬 가고, 윈도우는
        이미 사라진 함수를 부르러 온다."""
        self._api = None

    def start(self) -> bool:
        """주소 변경과 경로 변경 알림을 등록한다. 하나라도 걸리면 참.

        **둘 다 보는 것은 VPN 연결이 두 단계라서다.** 주소가 붙는 것이 먼저이고 기본 경로가
        그쪽으로 도는 것이 나중이라, 뒤엣것까지 봐야 통신이 실제로 옮겨 간 시점을 잡는다.
        """
        if self._handles:
            return True
        try:
            self._api = ctypes.WinDLL("iphlpapi")
        except OSError:
            return False
        for name in ("NotifyUnicastIpAddressChange", "NotifyRouteChange2"):
            self._register(name)
        return bool(self._handles)

    def _register(self, name: str):
        """알림 하나를 건다. 실패는 조용히 넘긴다 - 안내가 늦어질 뿐 앱이 못 돌 이유가 아니다."""
        function = getattr(self._api, name, None)
        if function is None:
            return
        function.argtypes = _NOTIFY_ARGTYPES
        function.restype = ctypes.c_ulong
        callback = _CALLBACK(lambda _context, _row, _kind: self.changed.emit())
        handle = wintypes.HANDLE()
        try:
            failed = function(AF_UNSPEC, callback, None, 0, ctypes.byref(handle))
        except Exception:
            return
        if failed:
            return
        self._callbacks.append(callback)
        self._handles.append(handle)

    def stop(self):
        """등록을 거둔다. **남긴 채 프로세스가 끝나면 이미 사라진 콜백이 불린다.**"""
        cancel = getattr(self._api, "CancelMibChangeNotify2", None) if self._api else None
        if cancel is not None:
            cancel.argtypes = [wintypes.HANDLE]
            cancel.restype = ctypes.c_ulong
            for handle in self._handles:
                try:
                    cancel(handle)
                except Exception:
                    pass
        self._handles.clear()
        self._callbacks.clear()
