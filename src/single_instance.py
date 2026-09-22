"""앱이 둘 뜨지 않게 막고, 뒤에 뜬 쪽의 요청을 먼저 뜬 쪽에 전한다.

**가르는 것은 소켓이 아니라 이름 있는 뮤텍스다**(4.3.0). 예전에는 소켓에 붙어 보고 안 붙으면
자기가 첫째라고 보았는데, 윈도우의 QLocalServer는 같은 이름으로 여럿이 listen할 수 있어
확인과 listen 사이에 끼어든 둘째가 그대로 떴다. 앱이 뜨는 데 1~2초 걸리는 동안 한 번 더
누르거나, 로그인 자동 실행과 겹치면 났다(사용자 신고, 2026-09-22). 뮤텍스는 만드는 일과
있는지 묻는 일이 한 번의 호출이라 끼어들 틈이 없다.
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

SOCKET_NAME = "TVerDownloader_IPC_Socket"
"""먼저 뜬 쪽이 요청을 받는 소켓 이름. 보내는 쪽(진입점)과 받는 쪽(창)이 이것 하나를 본다."""

MUTEX_NAME = "Local\\TVerDownloader_SingleInstance"
"""한 사용자 세션 안에서 하나만 두게 하는 이름. `Local\\`은 세션마다 따로라 다른 계정과 겹치지 않는다."""

SHOW_REQUEST = b"show"
TRAY_REQUEST = b"tray"
"""둘째 인스턴스가 먼저 뜬 쪽에 보내는 말.

`--tray`로 뜬 쪽은 창을 띄우면 안 되므로 TRAY_REQUEST를 보낸다. **아무것도 보내지 않는
것으로 뜻을 표시하지 않는다** - 받는 쪽이 읽기에 실패한 것과 구별되지 않는다.
"""

REQUEST_WAIT_MS = 300
"""보낸 말을 기다리는 시간. 넘기면 창을 띄우는 쪽으로 간다.

실패 방향을 그쪽으로 두는 것은, 못 읽었다고 창을 안 띄우면 흔한 경로인 '두 번 실행해서
원래 창을 부르는' 동작이 이따금 죽은 것처럼 보이기 때문이다. `--tray` 둘째 실행은
로그인 때 한 번뿐이라 반대쪽 손해가 훨씬 작다.
"""

CONNECT_DEADLINE_S = 8.0
"""먼저 뜬 쪽의 소켓이 열리기를 기다리는 시간.

먼저 뜬 쪽이 아직 시작하는 중이면 뮤텍스는 있는데 소켓이 없다. 그 사이에 포기하고 끝내도
앱은 하나만 남으므로, 이 값은 창을 불러내는 요청이 닿을 여유일 뿐이다.
"""

ERROR_ALREADY_EXISTS = 183

_mutex_handle = None


def acquire_instance_lock() -> bool:
    """이 프로세스가 첫째면 뮤텍스를 쥐고 True. 이미 떠 있으면 False.

    쥔 핸들은 놓지 않는다 - 프로세스가 끝나면(죽어도) 윈도우가 거둔다. 만들지 못하는
    드문 경우에는 True를 준다. 둘이 뜨는 것이 앱이 아예 안 뜨는 것보다 낫다.
    """
    global _mutex_handle
    if _mutex_handle is not None:
        return True
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
        handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        already = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
    except (AttributeError, OSError):
        return True
    if not handle:
        return True
    if already:
        kernel32.CloseHandle(handle)
        return False
    _mutex_handle = handle
    return True


def notify_running_instance(request: bytes, deadline_s: float = CONNECT_DEADLINE_S) -> bool:
    """먼저 뜬 쪽에 요청을 보낸다. 닿았으면 True.

    먼저 뜬 쪽이 아직 소켓을 열지 않았을 수 있어 조금씩 쉬며 다시 붙는다.
    """
    from PyQt6.QtNetwork import QLocalSocket

    end = time.monotonic() + deadline_s
    while True:
        socket = QLocalSocket()
        socket.connectToServer(SOCKET_NAME)
        if socket.waitForConnected(500):
            socket.write(request)
            socket.flush()
            socket.waitForBytesWritten(1000)
            socket.close()
            return True
        socket.abort()
        if time.monotonic() >= end:
            return False
        time.sleep(0.25)
