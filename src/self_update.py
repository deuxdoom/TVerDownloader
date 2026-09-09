"""새 버전으로 자기 자신을 갈아 끼우는 일.

실행 중인 exe는 자기를 덮어쓸 수 없어 교체는 배치가 맡는다. 바꾸는 것은 exe와
_internal 둘뿐이고 나머지(bin·설정·기록·썸네일)는 사용자 것이라 손대지 않는다.
백신이 드로퍼로 보지 않도록 %TEMP%·taskkill·자기 삭제·powershell·내려받기는 쓰지 않는다.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Iterable, Optional, Tuple

from src.i18n import t

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


DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")
"""맨 앞의 드라이브 지정자. 'C:x'는 그 드라이브의 현재 폴더를 가리켜 목적지를 벗어난다."""


def escapes_destination(name: str) -> bool:
    """압축 항목 이름이 풀어 놓을 폴더 밖을 가리키는가.

    `destination / relative`는 `..`도 앞의 `/`도 접지 않아, 그대로 쓰면 **작업 폴더 바깥을
    덮어쓴다.** CRC 검사(testzip)는 내용이 온전한지만 보므로 이것을 잡지 못한다.

    정상 릴리스에서 나오는 일은 아니고, 꾸러미가 바뀌었을 때를 위한 층이다. 그런 zip이라면
    exe 자체가 이미 문제이므로 이것만으로 안전해지지는 않는다 - 값싼 방어라서 둔다.
    """
    path = name.replace("\\", "/")
    if path.startswith("/") or DRIVE_PREFIX_RE.match(path):
        return True
    return any(part == ".." for part in path.split("/"))


def verify_package(zip_path: Path) -> Tuple[bool, str, str]:
    """받은 zip이 쓸 만한지 본다. (성공 여부, 내용물 접두사, 문제 설명).

    깨진 파일로 교체를 시작하면 되돌릴 것도 없이 앱이 사라져, 여는 것으로 끝내지 않고
    CRC까지 본다(testzip). exe와 _internal이 실제로 들어 있는지도 함께 본다.
    **폴더를 벗어나는 항목이 하나라도 있으면 꾸러미째 거부한다** - 다듬어서 받아들이면
    무엇을 덮어쓸 뻔했는지 아무도 모르게 된다.
    """
    if not zip_path.exists() or zip_path.stat().st_size == 0:
        return False, "", t("update.pkg_empty")
    try:
        with zipfile.ZipFile(zip_path) as archive:
            broken = archive.testzip()
            if broken is not None:
                return False, "", t("update.pkg_broken", name=broken)
            names = archive.namelist()
            unsafe = next((name for name in names if escapes_destination(name)), None)
            if unsafe is not None:
                return False, "", t("update.pkg_unsafe", name=unsafe)
            root = find_payload_root(names)
            if root is not None:
                unsafe = next((name for name, relative in payload_members(names, root)
                               if escapes_destination(relative)), None)
                if unsafe is not None:
                    return False, "", t("update.pkg_unsafe", name=unsafe)
    except (zipfile.BadZipFile, OSError) as error:
        return False, "", t("update.pkg_unreadable", error=error)

    if root is None:
        return False, "", t("update.pkg_incomplete", exe=APP_EXE_NAME,
                            folder=INTERNAL_DIR_NAME)
    return True, root, ""


def payload_members(names: Iterable[str], root: str):
    """root 아래 항목을 (원래 이름, 상대 경로)로 내준다.

    **검증하는 쪽과 푸는 쪽이 같은 것을 봐야 한다.** 원래 이름만 보면
    `TVerDownloader/C:/x`가 통과한 뒤 접두사를 떼면서 `C:/x`가 되어 다른 드라이브를
    가리키고, `TVerDownloader//x`는 `/x`가 되어 드라이브 루트를 가리킨다(실측). 떼는
    규칙이 두 곳에 적히면 이렇게 어긋난다.
    """
    for name in names:
        normalized = name.replace("\\", "/")
        if not normalized.lower().startswith(root.lower()):
            continue
        relative = normalized[len(root):]
        if not relative:
            continue
        yield name, relative


def extract_payload(zip_path: Path, root: str, destination: Path,
                    on_progress=None) -> None:
    """zip에서 본체만 골라 destination 바로 아래에 편다. 배치가 옮길 자리를 하나로 고정한다.

    벗어나는 항목은 verify_package가 이미 걸렀지만 여기서도 본다 - 푸는 일이 이 함수
    하나뿐이라, 관문을 거치지 않고 불리는 길이 생겨도 폴더 밖에 쓰지는 않는다.
    """
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        by_name = {m.filename: m for m in archive.infolist()}
        picked = [(by_name[name], relative)
                  for name, relative in payload_members(by_name, root)
                  if not escapes_destination(relative)]
        total = len(picked) or 1
        for index, (member, relative) in enumerate(picked, 1):
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

ECHO_ESCAPES = {"^": "^^", "&": "^&", "<": "^<", ">": "^>", "|": "^|", "%": "%%"}
"""배치의 echo·title에 그대로 넣으면 cmd가 명령으로 읽는 글자들과 그 대체 표기."""


def echo_safe(text: str) -> str:
    """번역문을 배치의 한 줄로 쓸 수 있게 다듬는다.

    lang/*.ini는 **사용자가 직접 고치는 파일이라** %나 >가 섞여 들어올 수 있고, 그대로
    두면 cmd가 변수 확장이나 리다이렉트로 읽어 교체가 그 자리에서 어긋난다. 여러 줄로
    적힌 값도 한 줄로 눕힌다 - 둘째 줄부터는 echo 없이 남아 그 자체가 명령이 된다.
    """
    flat = " ".join((text or "").split())
    return "".join(ECHO_ESCAPES.get(ch, ch) for ch in flat) or "."


def build_batch(app_directory: Path, work_directory: Path, pid: int,
                exe_name: str = APP_EXE_NAME) -> str:
    """교체를 맡을 배치 내용을 만든다. 순수 함수라 눈으로 보고 검사로 고정할 수 있다.

    **되돌아가는 구간(:waitloop, :move_retry_loop)에는 어느 언어도 넣지 않는다.** cmd는
    배치를 바이트 오프셋으로 되짚어, chcp 65001에서 아스키가 아닌 글자가 섞이면 goto로
    돌아간 뒤 줄 중간부터 실행되어 주석의 꼬리가 명령이 된다. 앞으로만 가는 구간은 멀쩡해
    사용자가 읽을 안내를 t()로 넣는다 - 값은 반드시 echo_safe를 거친다.
    """
    app = str(app_directory)
    work = str(work_directory)
    say = lambda key, **kw: echo_safe(t(key, **kw))
    return f"""@echo off
chcp 65001 > nul
title {say("update_batch.title")}
setlocal

rem {say("update_batch.rem_made_by")}
rem {say("update_batch.rem_scope")}
rem   1) {say("update_batch.rem_step1")}
rem   2) {say("update_batch.rem_step2", exe=exe_name, folder=INTERNAL_DIR_NAME)}
rem   3) {say("update_batch.rem_step3")}
rem {say("update_batch.rem_rollback")}

set "APP_DIR={app}"
set "WORK_DIR={work}"
set "EXE_NAME={exe_name}"
set "APP_PID={pid}"
set "MOVE_TRIES={MOVE_RETRIES}"

echo.
echo   {say("update_batch.title")}
echo   ================================================
echo.
echo   {say("update_batch.waiting")}

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
echo   {say("update_batch.give_up")}
echo   {say("update_batch.give_up_hint")}
echo.
pause
exit /b 1

:closed
timeout /t {SETTLE_SECONDS} /nobreak >nul

echo   {say("update_batch.backing_up")}
call :move_retry "%APP_DIR%\\{INTERNAL_DIR_NAME}" "%WORK_DIR%\\{BACKUP_DIR_NAME}\\{INTERNAL_DIR_NAME}"
if errorlevel 1 goto restore
call :move_retry "%APP_DIR%\\%EXE_NAME%" "%WORK_DIR%\\{BACKUP_DIR_NAME}\\%EXE_NAME%"
if errorlevel 1 goto restore

echo   {say("update_batch.installing")}
call :move_retry "%WORK_DIR%\\{NEW_DIR_NAME}\\{INTERNAL_DIR_NAME}" "%APP_DIR%\\{INTERNAL_DIR_NAME}"
if errorlevel 1 goto restore
call :move_retry "%WORK_DIR%\\{NEW_DIR_NAME}\\%EXE_NAME%" "%APP_DIR%\\%EXE_NAME%"
if errorlevel 1 goto restore

echo.
echo   {say("update_batch.done")}
echo   {say("update_batch.done_hint")}
start "" "%APP_DIR%\\%EXE_NAME%"
exit /b 0

:restore
echo.
echo   {say("update_batch.rolling_back")}
if not exist "%WORK_DIR%\\{BACKUP_DIR_NAME}\\{INTERNAL_DIR_NAME}" goto restore_exe
if exist "%APP_DIR%\\{INTERNAL_DIR_NAME}" rmdir /s /q "%APP_DIR%\\{INTERNAL_DIR_NAME}"
call :move_retry "%WORK_DIR%\\{BACKUP_DIR_NAME}\\{INTERNAL_DIR_NAME}" "%APP_DIR%\\{INTERNAL_DIR_NAME}"

:restore_exe
if not exist "%WORK_DIR%\\{BACKUP_DIR_NAME}\\%EXE_NAME%" goto restore_done
if exist "%APP_DIR%\\%EXE_NAME%" del /q "%APP_DIR%\\%EXE_NAME%"
call :move_retry "%WORK_DIR%\\{BACKUP_DIR_NAME}\\%EXE_NAME%" "%APP_DIR%\\%EXE_NAME%"

:restore_done
echo   {say("update_batch.rolled_back")}
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
