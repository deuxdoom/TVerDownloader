"""설정에서 언어를 바꿨을 때 앱을 다시 띄운다.

self_update.py와 다른 점은 **파일을 바꾸지 않는다는 것**이다. 그래서 배치도,
구 프로세스가 죽기를 기다리는 PID 폴링도 필요 없다 - 구 프로세스가 단일 인스턴스
소켓을 스스로 닫고 새 프로세스를 띄운 뒤에야 정리하고 끝나면(호출부인
TrayController.restart_for_language_change), 새 프로세스가 뜨는 시점엔 소켓
자리가 이미 비어 있어 레이스가 나지 않는다.
"""
from __future__ import annotations

import subprocess
import sys
from typing import List

from src import self_update

SOCKET_NAME = "TVerDownloader_IPC_Socket"
"""단일 인스턴스를 가리는 소켓 이름.

진입점이 아니라 여기 두는 것은, 재시작이 새 프로세스를 띄우기 **전에** 이 자리를 비워야
하는 쪽이라서다. 두 곳에 적으면 한쪽만 고쳤을 때 새 프로세스가 자기를 중복 실행으로 본다.
"""


SHOW_REQUEST = b"show"
TRAY_REQUEST = b"tray"
"""둘째 인스턴스가 먼저 뜬 쪽에 보내는 말.

`--tray`로 뜬 쪽은 창을 띄우면 안 되므로 TRAY_REQUEST를 보낸다. **아무것도 보내지 않는
것으로 뜻을 표시하지 않는다** - 받는 쪽이 읽기에 실패한 것과 구별되지 않는다.
SOCKET_NAME과 같은 이유로 여기 둔다: 보내는 쪽과 받는 쪽이 다른 파일에 있다.
"""

REQUEST_WAIT_MS = 300
"""보낸 말을 기다리는 시간. 넘기면 창을 띄우는 쪽으로 간다.

실패 방향을 그쪽으로 두는 것은, 못 읽었다고 창을 안 띄우면 흔한 경로인 '두 번 실행해서
원래 창을 부르는' 동작이 이따금 죽은 것처럼 보이기 때문이다. `--tray` 둘째 실행은
로그인 때 한 번뿐이라 반대쪽 손해가 훨씬 작다.
"""


def build_restart_args() -> List[str]:
    """새로 띄울 프로세스의 실행 인자. frozen이면 exe 자신, 소스면 인터프리터+스크립트."""
    if self_update.supported():
        app_dir = self_update.app_dir()
        return [str(app_dir / self_update.APP_EXE_NAME)]
    return [sys.executable, *sys.argv]


def spawn_new_instance() -> bool:
    """새 프로세스를 띄운다. 실패해도 예외를 던지지 않는다 - 호출부가 되돌릴 수 있게."""
    try:
        subprocess.Popen(build_restart_args(), close_fds=True)
        return True
    except OSError:
        return False
