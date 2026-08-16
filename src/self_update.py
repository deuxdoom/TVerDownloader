"""새 버전으로 자기 자신을 갈아 끼우는 일.

**실행 중인 exe는 자기를 덮어쓸 수 없다.** 그래서 교체는 밖에서 해야 하고, 그
'밖'을 배치 파일이 맡는다. 본체가 스스로 닫히기를 기다렸다가 파일을 옮기고 새
본체를 띄운다.

인스톨러를 쓰지 않는 이유는 이 앱이 포터블이기 때문이다. 설정 파일과 bin 폴더를
**상대 경로**로 쓰므로 Program Files에 들어가면 쓰기 권한에서 전부 깨진다. 그래서
사용자가 두고 쓰던 폴더를 그 자리에서 갈아 끼운다.

바꾸는 것은 `TVerDownloader.exe`와 `_internal` **둘뿐이다.** bin·설정·기록·즐겨찾기·
썸네일은 손대지 않는다. 사용자의 것이고, 버전이 올라가도 그대로 써야 한다.

**_internal은 덮어쓰지 않고 통째로 갈아 끼운다.** 덮어쓰면 옛 버전에만 있던 파일이
남아 용량만 차지하고, 나중에 무엇이 어느 버전 것인지 알 수 없게 된다.

작업 폴더를 앱 폴더 **안**에 두는 것은 두 가지 이유다. 같은 볼륨이라 move가 복사가
아니라 이름 바꾸기로 끝나 순식간이고(교체가 반쯤 된 상태로 머무는 시간이 짧다),
%TEMP%에 스크립트를 떨어뜨려 실행하는 모양새를 피할 수 있다(아래 참고).

## 백신 오탐을 줄이려고 일부러 이렇게 한 것들

프로세스를 죽이고 폴더를 지우고 exe를 바꾼 뒤 다시 띄우는 일은, 하는 짓만 보면
드로퍼와 구별되지 않는다. 휴리스틱에 걸릴 만한 신호를 하나씩 뺐다.

- **%TEMP%가 아니라 앱 폴더에 배치를 쓴다.** 임시 폴더에 스크립트를 떨어뜨려
  실행하는 것은 드로퍼의 기본 동작이라 그 자체로 점수가 높다.
- **taskkill을 쓰지 않는다.** 본체는 스스로 닫히고, 배치는 PID가 사라질 때까지
  기다리기만 한다. 남의 프로세스를 강제로 끝내는 것은 신호가 세다.
- **자기 자신을 지우지 않는다.** `del "%~f0"`은 흔적을 지우는 동작이라 눈에 띈다.
  뒷정리는 다음 실행 때 앱이 한다(cleanup_workspace).
- **배치가 내려받지 않는다.** 받는 일은 본체가 HTTPS로 한다. 스크립트 안의
  certutil·bitsadmin·curl은 'download & execute'로 바로 읽힌다.
- **powershell을 부르지 않는다.** cmd 내장 명령만 쓴다. `-EncodedCommand`나
  `-ExecutionPolicy Bypass`는 특히 위험한 조합이다.
- **창을 숨기지 않는다.** 무엇을 하는 중인지 한국어로 찍는다. 사용자가 볼 수
  있다는 것 자체가 조용히 도는 것보다 낫고, 사람에게도 친절하다.
- **이름과 내용을 감추지 않는다.** 파일 이름은 update.cmd로 고정하고 각 단계에
  rem으로 설명을 붙인다. 무작위 이름과 난독화가 오히려 의심을 산다.

그래도 남는 근본 원인은 **서명이 없다는 것**이다. 서명되지 않은 exe가 서명되지
않은 다른 exe를 갈아 끼우면 어떤 백신이든 볼 수밖에 없다. 코드 서명 인증서를
붙이는 것이 진짜 해결책이고, 그 전까지는 오탐이 날 수 있다.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Iterable, Optional, Tuple

APP_EXE_NAME = "TVerDownloader.exe"
INTERNAL_DIR_NAME = "_internal"

WORK_DIR_NAME = "update-workspace"
"""교체 작업에 쓰는 폴더. 앱 폴더 안에 둔다.

점으로 시작하는 숨은 이름을 쓰지 않는 것도 일부러다. 숨기면 사용자가 지우지도
못하고, 백신 쪽에서도 곱게 보지 않는다.
"""

BATCH_NAME = "update.cmd"
NEW_DIR_NAME = "new"
BACKUP_DIR_NAME = "backup"

WAIT_LIMIT_SECONDS = 60
"""본체가 닫히기를 기다리는 한계.

여기까지 안 닫히면 교체를 시작하지 않고 그냥 물러난다. 어중간하게 시작해서
반만 바뀐 상태로 남는 것이 가장 나쁘다.
"""


def supported() -> bool:
    """이 실행본에서 자동 업데이트를 쓸 수 있는지.

    소스로 돌릴 때는 끈다. 바꿔야 할 exe도 _internal도 없고, 개발 중인 작업
    폴더를 릴리스 내용으로 덮어쓰면 그때까지 고치던 것이 날아간다.
    autostart.supported()가 같은 이유로 같은 판단을 한다.
    """
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Optional[Path]:
    """exe와 _internal이 들어 있는 폴더. 빌드된 실행본이 아니면 None."""
    if not supported():
        return None
    return Path(sys.executable).resolve().parent


def work_dir() -> Optional[Path]:
    """교체 작업에 쓰는 폴더."""
    base = app_dir()
    return None if base is None else base / WORK_DIR_NAME


def is_writable(directory: Path) -> bool:
    """그 폴더에 파일을 만들 수 있는지 실제로 해 본다.

    권한을 계산으로 알아내려 들지 않는다. Program Files 아래인지, 관리자인지,
    폴더가 읽기 전용인지를 각각 따지는 것보다 한 번 써 보는 쪽이 확실하다.
    """
    probe = directory / ".write-test"
    try:
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def pick_asset(assets: Iterable[dict]) -> Optional[dict]:
    """릴리스에 붙은 파일 중 내려받을 zip을 고른다.

    zip이 여럿이면 첫 번째를 쓴다. 지금 릴리스에는 하나뿐이고, 여러 개를 두게
    되면 이름 규칙을 정한 뒤 여기를 고치는 편이 낫다.
    """
    for asset in assets or []:
        name = (asset.get("name") or "").lower()
        url = asset.get("browser_download_url")
        if name.endswith(".zip") and url:
            return asset
    return None


def find_payload_root(names: Iterable[str]) -> Optional[str]:
    """zip 안에서 exe와 _internal이 함께 있는 자리를 찾는다.

    지금 릴리스는 `TVerDownloader/` 폴더 하나로 감싸여 있지만, 감싸지 않고 올릴
    수도 있어서 두 모양을 모두 받는다. 어느 쪽인지 정해 놓고 읽으면 압축 방식이
    바뀐 날 조용히 실패한다.

    돌려주는 값은 접두사다. 감싸지 않았으면 빈 문자열.
    """
    entries = [n.replace("\\", "/") for n in names]
    exe_lower = APP_EXE_NAME.lower()
    internal_prefix = INTERNAL_DIR_NAME.lower() + "/"

    candidates = {""}
    for entry in entries:
        head, sep, _ = entry.partition("/")
        if sep:
            candidates.add(head + "/")

    for root in sorted(candidates, key=len):
        has_exe = any(e.lower() == root.lower() + exe_lower for e in entries)
        has_internal = any(e.lower().startswith(root.lower() + internal_prefix)
                           for e in entries)
        if has_exe and has_internal:
            return root
    return None


def verify_package(zip_path: Path) -> Tuple[bool, str, str]:
    """받은 zip이 쓸 만한지 본다. (성공 여부, 내용물 접두사, 문제 설명).

    **깨진 파일로 교체를 시작하면 되돌릴 것도 없이 앱이 사라진다.** 그래서 여는
    것으로 끝내지 않고 CRC까지 확인한다(testzip). 받다 만 파일은 열리기는 해도
    끝부분이 깨져 있는 경우가 많다.

    이름만 맞는 다른 zip이 올라온 경우까지 걸러내려고 exe와 _internal이 실제로
    들어 있는지도 본다.
    """
    if not zip_path.exists() or zip_path.stat().st_size == 0:
        return False, "", "내려받은 파일이 비어 있습니다."
    try:
        with zipfile.ZipFile(zip_path) as archive:
            broken = archive.testzip()
            if broken is not None:
                return False, "", f"압축 파일이 손상되었습니다: {broken}"
            root = find_payload_root(archive.namelist())
    except (zipfile.BadZipFile, OSError) as error:
        return False, "", f"압축 파일을 열지 못했습니다: {error}"

    if root is None:
        return False, "", (f"압축 안에서 {APP_EXE_NAME}과 {INTERNAL_DIR_NAME} 폴더를 "
                           "찾지 못했습니다.")
    return True, root, ""


def extract_payload(zip_path: Path, root: str, destination: Path,
                    on_progress=None) -> None:
    """zip에서 본체만 골라 destination 아래에 편다.

    root 접두사를 떼고 풀어서, 감쌌든 아니든 destination 바로 아래에
    exe와 _internal이 오게 만든다. 배치가 옮길 자리를 하나로 고정하기 위해서다.
    """
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        members = [m for m in archive.infolist()
                   if m.filename.replace("\\", "/").lower().startswith(root.lower())]
        total = len(members) or 1
        for index, member in enumerate(members, 1):
            relative = member.filename.replace("\\", "/")[len(root):]
            if not relative:
                continue
            target = destination / relative
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, open(target, "wb") as out:
                    shutil.copyfileobj(source, out)
            if on_progress:
                on_progress(index, total)


MOVE_RETRIES = 8
MOVE_RETRY_WAIT = 2
"""옮기기가 막혔을 때 다시 해 보는 횟수와 간격(초).

**백신이 갓 풀린 파일을 붙잡고 있는 동안 'Access is denied'가 난다.** 97개짜리
_internal을 통째로 옮기는 순간이라 그중 하나만 검사 중이어도 막힌다. 실제로
카스퍼스키에서 이 자리에서 실패했다. 잠깐 기다렸다 다시 하면 대개 지나간다.

8회 x 2초 = 최대 16초. 그래도 안 되면 진짜 권한 문제이므로 되돌리기로 간다.
"""

SETTLE_SECONDS = 2
"""본체가 닫힌 뒤 손대기 전에 두는 뜸.

닫히자마자 파일을 건드리면 백신이 그 프로세스의 파일들을 아직 훑고 있다.
"""


def build_batch(app_directory: Path, work_directory: Path, pid: int,
                exe_name: str = APP_EXE_NAME) -> str:
    """교체를 맡을 배치 내용을 만든다.

    순수 함수로 둔 이유는 이걸 눈으로 확인하고 검사로 고정하기 위해서다. 실제로
    돌려 보기 전에는 맞는지 알기 어려운 코드이고, 한 줄 틀리면 앱이 사라진다.

    **되돌리기가 이 스크립트의 본론이다.** move가 끝내 실패하면 곧장 :restore로
    가서 백업을 제자리에 돌려놓는다. 백업은 같은 볼륨에 있어 되돌리는 것도
    이름 바꾸기라 실패할 여지가 적다.

    ## 되돌아가는 구간(:waitloop, :move_retry_loop)은 반드시 ASCII만 쓴다

    cmd는 배치 파일을 **바이트 오프셋**으로 되짚는데, chcp 65001에서 UTF-8 한글이
    섞여 있으면 그 위치가 어긋난다. goto로 되돌아간 뒤 줄 **중간부터** 실행되어
    한국어 주석의 꼬리가 명령으로 실행된다. 실제로 이렇게 나왔다.

        '믿으면' is not recognized as an internal or external command,
        '파일을' is not recognized as an internal or external command,

    실측으로 가른 결과는 이렇다.

    | 배치 구성 | 결과 |
    |---|---|
    | 한국어 주석이 루프 **안** | 깨짐 (위 오류) |
    | 한국어가 루프 **앞**에만 | 정상 |
    | 루프 안이 전부 ASCII | 정상 |

    그래서 **앞으로만 가는 구간에는 한국어를 그대로 두고**(사용자가 읽어야 한다),
    되돌아가는 두 구간만 ASCII로 적는다. 편하다고 그 안에 한국어를 넣으면 다시
    깨진다.
    """
    app = str(app_directory)
    work = str(work_directory)
    return f"""@echo off
chcp 65001 > nul
title TVer Downloader 업데이트
setlocal

rem 이 파일은 TVer Downloader가 새 버전을 넣기 위해 만든 것입니다.
rem 하는 일은 아래 세 가지뿐이고, 무엇도 내려받지 않습니다.
rem   1) 프로그램이 스스로 닫히기를 기다린다
rem   2) 기존 {exe_name}과 {INTERNAL_DIR_NAME}을 백업 폴더로 옮긴다
rem   3) 새 파일을 제자리에 옮기고 프로그램을 다시 띄운다
rem 옮기다 실패하면 백업을 그대로 되돌립니다.
rem
rem 되돌아가는 구간(:waitloop, :move_retry_loop)에는 한국어를 쓰지 않습니다.
rem cmd가 goto로 되짚을 때 바이트 위치가 어긋나 줄 중간부터 실행되기 때문입니다.

set "APP_DIR={app}"
set "WORK_DIR={work}"
set "EXE_NAME={exe_name}"
set "APP_PID={pid}"
set "MOVE_TRIES={MOVE_RETRIES}"

echo.
echo   TVer Downloader 업데이트
echo   ================================================
echo.
echo   프로그램이 닫히기를 기다리는 중입니다...

set /a WAITED=0

:waitloop
tasklist /FI "PID eq %APP_PID%" /NH 2>nul | findstr /C:"%APP_PID%" >nul
if errorlevel 1 goto closed
set /a WAITED+=1
if %WAITED% GEQ {WAIT_LIMIT_SECONDS} goto give_up
timeout /t 1 /nobreak >nul
goto waitloop

:give_up
echo.
echo   [중단] 프로그램이 닫히지 않아 업데이트를 하지 않았습니다.
echo   파일은 하나도 건드리지 않았습니다. 프로그램을 끄고 다시 시도해 주세요.
echo.
pause
exit /b 1

:closed
timeout /t {SETTLE_SECONDS} /nobreak >nul

echo   기존 파일을 백업합니다...
call :move_retry "%APP_DIR%\\{INTERNAL_DIR_NAME}" "%WORK_DIR%\\{BACKUP_DIR_NAME}\\{INTERNAL_DIR_NAME}"
if errorlevel 1 goto restore
call :move_retry "%APP_DIR%\\%EXE_NAME%" "%WORK_DIR%\\{BACKUP_DIR_NAME}\\%EXE_NAME%"
if errorlevel 1 goto restore

echo   새 버전을 넣습니다...
call :move_retry "%WORK_DIR%\\{NEW_DIR_NAME}\\{INTERNAL_DIR_NAME}" "%APP_DIR%\\{INTERNAL_DIR_NAME}"
if errorlevel 1 goto restore
call :move_retry "%WORK_DIR%\\{NEW_DIR_NAME}\\%EXE_NAME%" "%APP_DIR%\\%EXE_NAME%"
if errorlevel 1 goto restore

echo.
echo   업데이트를 마쳤습니다. 프로그램을 다시 시작합니다.
echo   (남은 백업은 프로그램이 켜질 때 정리합니다)
start "" "%APP_DIR%\\%EXE_NAME%"
exit /b 0

:restore
echo.
echo   [실패] 교체 중 문제가 생겨 원래 버전으로 되돌립니다...
if not exist "%WORK_DIR%\\{BACKUP_DIR_NAME}\\{INTERNAL_DIR_NAME}" goto restore_exe
if exist "%APP_DIR%\\{INTERNAL_DIR_NAME}" rmdir /s /q "%APP_DIR%\\{INTERNAL_DIR_NAME}"
call :move_retry "%WORK_DIR%\\{BACKUP_DIR_NAME}\\{INTERNAL_DIR_NAME}" "%APP_DIR%\\{INTERNAL_DIR_NAME}"

:restore_exe
if not exist "%WORK_DIR%\\{BACKUP_DIR_NAME}\\%EXE_NAME%" goto restore_done
if exist "%APP_DIR%\\%EXE_NAME%" del /q "%APP_DIR%\\%EXE_NAME%"
call :move_retry "%WORK_DIR%\\{BACKUP_DIR_NAME}\\%EXE_NAME%" "%APP_DIR%\\%EXE_NAME%"

:restore_done
echo   원래 버전으로 되돌렸습니다. 프로그램을 다시 시작합니다.
start "" "%APP_DIR%\\%EXE_NAME%"
echo.
pause
exit /b 1

rem ---- ASCII only below: this block is re-entered by goto ----
rem A security scanner may hold freshly extracted files for a moment.
rem Retry a few times before giving up and rolling back.

:move_retry
set /a MOVE_N=0

:move_retry_loop
move %1 %2 >nul 2>&1
if not errorlevel 1 exit /b 0
set /a MOVE_N+=1
if %MOVE_N% GEQ %MOVE_TRIES% exit /b 1
echo     file is in use, retrying %MOVE_N%/%MOVE_TRIES% ...
timeout /t {MOVE_RETRY_WAIT} /nobreak >nul
goto move_retry_loop
"""


def prepare_workspace() -> Optional[Path]:
    """작업 폴더를 비우고 새로 만든다. 쓸 수 없으면 None.

    지난번 찌꺼기가 남아 있으면 새 파일과 섞인다. 시작할 때 통째로 지운다.
    """
    work = work_dir()
    if work is None:
        return None
    base = app_dir()
    if base is None or not is_writable(base):
        return None
    shutil.rmtree(work, ignore_errors=True)
    try:
        (work / NEW_DIR_NAME).mkdir(parents=True, exist_ok=True)
        (work / BACKUP_DIR_NAME).mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return work


def cleanup_workspace() -> None:
    """남아 있는 작업 폴더를 지운다. 앱이 켜질 때 부른다.

    **여기까지 왔다는 것은 새 버전이 실제로 떴다는 뜻이다.** 그래서 이 시점에
    백업을 버려도 안전하다. 교체가 잘못돼 새 버전이 아예 뜨지 못했다면 이 코드에
    차례가 오지 않으므로 백업은 그대로 남아 있다.
    """
    work = work_dir()
    if work is not None and work.exists():
        shutil.rmtree(work, ignore_errors=True)


def launch_updater(work: Path, pid: Optional[int] = None) -> bool:
    """배치를 새 창으로 띄운다. 본체는 곧바로 종료해야 한다.

    창을 숨기지 않는 이유는 위 모듈 설명에 적어 두었다. 무엇을 하는 중인지
    보이는 편이 사람에게도 백신에게도 낫다.
    """
    base = app_dir()
    if base is None:
        return False
    batch_path = work / BATCH_NAME
    try:
        batch_path.write_text(
            build_batch(base, work, os.getpid() if pid is None else pid),
            encoding="utf-8")
        subprocess.Popen(["cmd.exe", "/c", str(batch_path)], cwd=str(base),
                         creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
                         close_fds=True)
        return True
    except OSError:
        return False


def staged_payload_ok(work: Path, exe_name: str = APP_EXE_NAME) -> bool:
    """옮길 준비가 실제로 끝났는지 마지막으로 본다.

    배치를 띄우기 직전의 마지막 관문이다. 여기서 한 번 더 보는 이유는, 압축을
    푸는 도중 디스크가 찼거나 백신이 파일 하나를 격리해 갔을 수 있어서다.
    배치는 파일이 없으면 되돌리기로 가지만, 애초에 시작하지 않는 편이 낫다.
    """
    new_dir = work / NEW_DIR_NAME
    exe = new_dir / exe_name
    internal = new_dir / INTERNAL_DIR_NAME
    return exe.is_file() and exe.stat().st_size > 0 and internal.is_dir() and any(internal.iterdir())
