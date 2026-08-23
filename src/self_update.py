"""새 버전으로 자기 자신을 갈아 끼우는 일.

실행 중인 exe는 자기를 덮어쓸 수 없어 교체는 배치가 맡는다. 바꾸는 것은 exe와
_internal 둘뿐이고 나머지(bin·설정·기록·썸네일)는 사용자 것이라 손대지 않는다.
백신이 드로퍼로 보지 않도록 %TEMP%·taskkill·자기 삭제·powershell·내려받기는 쓰지 않는다.
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
"""교체 작업에 쓰는 폴더. 앱 폴더 안에 둔다 - 숨은 이름은 지우지도 못하고 백신도 곱게 안 본다."""

BATCH_NAME = "update.cmd"
NEW_DIR_NAME = "new"
BACKUP_DIR_NAME = "backup"

WAIT_LIMIT_SECONDS = 60
"""본체가 닫히기를 기다리는 한계. 넘으면 시작하지 않는다 - 반만 바뀐 상태가 가장 나쁘다."""


def supported() -> bool:
    """이 실행본에서 자동 업데이트를 쓸 수 있는지.

    소스로 돌릴 때는 끈다 - 바꿀 exe가 없고, 개발 중인 폴더를 릴리스로 덮으면 고치던 것이 날아간다.
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
    """그 폴더에 파일을 만들 수 있는지 실제로 해 본다. 권한을 계산으로 알아내려 들지 않는다."""
    probe = directory / ".write-test"
    try:
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def pick_asset(assets: Iterable[dict]) -> Optional[dict]:
    """릴리스에 붙은 파일 중 내려받을 zip을 고른다. 여럿이면 첫 번째 - 지금은 하나뿐이다."""
    for asset in assets or []:
        name = (asset.get("name") or "").lower()
        url = asset.get("browser_download_url")
        if name.endswith(".zip") and url:
            return asset
    return None


def find_payload_root(names: Iterable[str]) -> Optional[str]:
    """zip 안에서 exe와 _internal이 함께 있는 자리를 찾는다. 돌려주는 값은 접두사다.

    감싼 폴더가 있을 수도 없을 수도 있어 두 모양을 모두 받는다. 하나로 정해 놓고
    읽으면 압축 방식이 바뀐 날 조용히 실패한다.
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

    깨진 파일로 교체를 시작하면 되돌릴 것도 없이 앱이 사라져, 여는 것으로 끝내지 않고
    CRC까지 본다(testzip). exe와 _internal이 실제로 들어 있는지도 함께 본다.
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
    """zip에서 본체만 골라 destination 바로 아래에 편다. 배치가 옮길 자리를 하나로 고정한다."""
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

백신이 갓 풀린 파일을 붙잡고 있으면 'Access is denied'가 난다(카스퍼스키에서 실제로).
97개짜리 _internal을 통째로 옮기는 순간이라 그중 하나만 검사 중이어도 막힌다.
"""

SETTLE_SECONDS = 2
"""본체가 닫힌 뒤 손대기 전에 두는 뜸. 백신이 그 프로세스의 파일들을 아직 훑고 있다."""


def build_batch(app_directory: Path, work_directory: Path, pid: int,
                exe_name: str = APP_EXE_NAME) -> str:
    """교체를 맡을 배치 내용을 만든다. 순수 함수라 눈으로 보고 검사로 고정할 수 있다.

    **되돌아가는 구간(:waitloop, :move_retry_loop)에는 한국어를 쓰지 않는다.** cmd는
    배치를 바이트 오프셋으로 되짚어, chcp 65001에서 한글이 섞이면 goto로 돌아간 뒤 줄
    중간부터 실행되어 주석의 꼬리가 명령이 된다. 앞으로만 가는 구간의 한국어는 멀쩡하다.
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
    """작업 폴더를 비우고 새로 만든다. 쓸 수 없으면 None. 지난번 찌꺼기가 새 파일과 섞인다."""
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

    여기까지 왔다는 것은 새 버전이 실제로 떴다는 뜻이라 그때 백업을 버려도 안전하다.
    """
    work = work_dir()
    if work is not None and work.exists():
        shutil.rmtree(work, ignore_errors=True)


def launch_updater(work: Path, pid: Optional[int] = None) -> bool:
    """배치를 새 창으로 띄운다. 본체는 곧바로 종료해야 한다. 창을 숨기지 않는 이유는 위에 있다."""
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

    압축을 푸는 도중 디스크가 찼거나 백신이 파일 하나를 격리해 갔을 수 있다. 배치도
    파일이 없으면 되돌리기로 가지만, 애초에 시작하지 않는 편이 낫다.
    """
    new_dir = work / NEW_DIR_NAME
    exe = new_dir / exe_name
    internal = new_dir / INTERNAL_DIR_NAME
    return exe.is_file() and exe.stat().st_size > 0 and internal.is_dir() and any(internal.iterdir())
