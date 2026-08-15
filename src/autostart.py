"""Windows 시작 프로그램 등록.

HKCU의 Run 키에 값 하나만 쓴다. 관리자 권한이 필요 없고, 끄면 값을 지워 흔적이
남지 않는다. 바로 가기를 시작 프로그램 폴더에 만드는 방법도 있지만, 그쪽은 파일을
남기고 사용자가 지워도 앱이 알 방법이 없다.

로그인할 때 뜨는 것이라 창을 띄우지 않고 트레이로 들어가도록 TRAY_FLAG를 붙여
등록한다. 켜 두는 쪽은 '받는 중인 것을 놓치지 않으려고'지 '창을 보려고'가 아니다.
"""
from __future__ import annotations

import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "TVerDownloader"
TRAY_FLAG = "--tray"


def target_command() -> str | None:
    """등록할 명령줄. 빌드된 exe가 아니면 None.

    소스로 돌릴 때는 파이썬 경로와 스크립트 경로를 함께 넣어야 하는데, 그렇게
    등록해 두면 개발 중인 사본이 로그인할 때마다 뜬다. 배포본에서만 켤 수 있게 한다.
    """
    if not getattr(sys, "frozen", False):
        return None
    return f'"{Path(sys.executable)}" {TRAY_FLAG}'


def supported() -> bool:
    """이 실행본에서 시작 프로그램 등록을 쓸 수 있는지."""
    return target_command() is not None


def is_enabled() -> bool:
    """지금 이 실행본이 시작 프로그램으로 걸려 있는지.

    값이 있어도 가리키는 경로가 다르면 꺼진 것으로 본다. 폴더째 옮겼거나 다른
    사본을 등록해 둔 상태인데, 그걸 켜져 있다고 보여 주면 사용자는 이 exe가
    자동 실행된다고 믿게 된다. 다시 켜면 지금 경로로 갱신된다.
    """
    expected = target_command()
    if expected is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            stored, _ = winreg.QueryValueEx(key, VALUE_NAME)
    except OSError:
        return False
    return str(stored).strip().lower() == expected.lower()


def set_enabled(enabled: bool) -> bool:
    """등록을 켜거나 끄고, 뜻대로 됐는지 돌려준다.

    끌 때 값이 원래 없어도 성공으로 본다. 사용자가 바란 상태('자동 실행 안 함')가
    이미 그대로라 실패라고 알릴 것이 없다.
    """
    command = target_command()
    if command is None:
        return False
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
    except OSError:
        return False
    return True


def launched_for_tray(argv: list[str] | None = None) -> bool:
    """시작 프로그램으로 실행된 것인지(창을 띄우지 말아야 하는지)."""
    return TRAY_FLAG in (sys.argv if argv is None else argv)
