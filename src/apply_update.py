"""새 실행본에서 기존 앱 파일을 교체한다. 화면은 진행 콜백만 통해 상태를 받는다."""

from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Sequence

from src.self_update import (APP_EXE_NAME, BACKUP_DIR_NAME, INTERNAL_DIR_NAME,
                             MOVE_RETRIES, MOVE_RETRY_WAIT, NEW_DIR_NAME,
                             SETTLE_SECONDS, WAIT_LIMIT_SECONDS, WORK_DIR_NAME)
from versioninfo import APP_VERSION


RESULT_NAME = "result.json"
WAIT_POLL_MS = 200
"""종료 대기를 짧게 끊어 기다리는 동안 취소 단추에도 응답한다."""
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
ERROR_INVALID_PARAMETER = 87


@dataclass(frozen=True)
class ApplyOptions:
    pid: int
    app_dir: Path
    work_dir: Path
    from_version: str
    pos: tuple[int, int] | None = None
    queued: int = 0


def parse_arguments(argv: Sequence[str]) -> ApplyOptions | None:
    if not argv or argv[0] != "--apply-update" or len(argv[1:]) % 2:
        return None
    values = {}
    allowed = {"--pid", "--app-dir", "--work-dir", "--from-version", "--pos",
               "--queued"}
    for key, value in zip(argv[1::2], argv[2::2]):
        if key not in allowed or key in values or not value:
            return None
        values[key] = value
    if not {"--pid", "--app-dir", "--work-dir", "--from-version"} <= values.keys():
        return None
    try:
        pid = int(values["--pid"])
        if pid <= 0:
            return None
        queued = int(values.get("--queued", "0"))
        if queued < 0:
            return None
        pos = None
        if "--pos" in values:
            match = re.fullmatch(r"(-?\d+),(-?\d+)", values["--pos"])
            if not match:
                return None
            pos = (int(match.group(1)), int(match.group(2)))
        return ApplyOptions(pid, Path(values["--app-dir"]), Path(values["--work-dir"]),
                            values["--from-version"], pos, queued)
    except (ValueError, OSError):
        return None


def validate_arguments(options: ApplyOptions, current_exe: Path) -> bool:
    app = options.app_dir.resolve()
    work = options.work_dir.resolve()
    new = work / NEW_DIR_NAME
    exe = current_exe.resolve()
    return (work == app / WORK_DIR_NAME
            and exe.name.lower() == APP_EXE_NAME.lower()
            and exe.is_relative_to(new)
            and (app / APP_EXE_NAME).is_file()
            and (app / INTERNAL_DIR_NAME).is_dir()
            and (new / APP_EXE_NAME).is_file()
            and (new / INTERNAL_DIR_NAME).is_dir())


def payload_files(root: Path) -> list[Path]:
    """파일 단위로 옮겨야 일부만 처리된 경우에도 그 일부를 되돌릴 수 있다."""
    internal = root / INTERNAL_DIR_NAME
    files = [Path(APP_EXE_NAME)] if (root / APP_EXE_NAME).is_file() else []
    if internal.is_dir():
        files.extend(sorted(path.relative_to(root) for path in internal.rglob("*")
                            if path.is_file()))
    return files


def file_progress(done: int, total: int, start: int, end: int) -> int:
    return start + (end - start) * done // max(1, total)


def make_result(options: ApplyOptions, stage: str, error: str = "") -> dict:
    return {"ok": stage == "done", "from_version": options.from_version,
            "to_version": APP_VERSION, "stage": stage, "error": error,
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


def write_result(options: ApplyOptions, result: dict) -> None:
    target = options.work_dir / RESULT_NAME
    temporary = options.work_dir / "result.tmp"
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, target)


def wait_for_pid(pid: int, cancelled: Callable[[], bool],
                 limit_seconds: float = WAIT_LIMIT_SECONDS) -> bool | None:
    """커널 핸들로 종료를 기다려 창 없는 적용 모드에서도 PID 재사용을 피한다."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        if ctypes.get_last_error() == ERROR_INVALID_PARAMETER:
            return True
        raise OSError(ctypes.get_last_error(), "OpenProcess")
    try:
        deadline = time.monotonic() + limit_seconds
        while True:
            if cancelled():
                return None
            status = kernel.WaitForSingleObject(handle, 0)
            if status == WAIT_OBJECT_0:
                return True
            if status != WAIT_TIMEOUT:
                raise OSError(ctypes.get_last_error(), "WaitForSingleObject")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            status = kernel.WaitForSingleObject(handle,
                                                min(WAIT_POLL_MS, max(1, int(remaining * 1000))))
            if status == WAIT_OBJECT_0:
                return None if cancelled() else True
            if status != WAIT_TIMEOUT:
                raise OSError(ctypes.get_last_error(), "WaitForSingleObject")
    finally:
        kernel.CloseHandle(handle)


def launch_application(exe: Path) -> None:
    subprocess.Popen([str(exe)], cwd=str(exe.parent), close_fds=True)


def apply_update(options: ApplyOptions, on_progress: Callable[[int, str, dict], None],
                 *, current_exe: Optional[Path] = None,
                 wait: Optional[Callable[[int, Callable[[], bool]], bool | None]] = None,
                 sleep: Optional[Callable[[float], None]] = None,
                 move: Optional[Callable[[Path, Path], object]] = None,
                 copy: Optional[Callable[[Path, Path], object]] = None,
                 launch: Optional[Callable[[Path], None]] = None,
                 cancelled: Optional[Callable[[], bool]] = None) -> dict | None:
    current_exe = Path(sys.executable) if current_exe is None else Path(current_exe)
    wait = wait_for_pid if wait is None else wait
    sleep = time.sleep if sleep is None else sleep
    move = os.replace if move is None else move
    copy = shutil.copy2 if copy is None else copy
    launch = launch_application if launch is None else launch
    cancelled = (lambda: False) if cancelled is None else cancelled

    def report(percent: int, stage: str, **detail):
        on_progress(percent, stage, detail)

    def save(stage: str, error: str = "") -> dict:
        result = make_result(options, stage, error)
        write_result(options, result)
        return result

    def retry(operation):
        for attempt in range(MOVE_RETRIES):
            try:
                return operation()
            except OSError:
                if attempt + 1 == MOVE_RETRIES:
                    raise
                sleep(MOVE_RETRY_WAIT)

    app = options.app_dir
    work = options.work_dir
    new = work / NEW_DIR_NAME
    backup = work / BACKUP_DIR_NAME
    if not validate_arguments(options, current_exe):
        result = make_result(options, "bad_arguments", "invalid update paths")
        report(0, "bad_arguments", error=result["error"])
        return result

    report(0, "waiting")
    try:
        exited = wait(options.pid, cancelled)
    except OSError as error:
        result = save("failed", str(error))
        report(0, "failed", error=result["error"])
        return result
    if exited is None or cancelled():
        return None
    if not exited:
        result = save("wait_timeout", "previous process did not exit")
        report(10, "wait_timeout", error=result["error"])
        return result
    report(10, "waiting")
    sleep(SETTLE_SECONDS)
    if cancelled():
        return None

    moved: list[Path] = []
    copied: list[Path] = []
    percent = 10
    try:
        old_files = payload_files(app)
        new_files = payload_files(new)
        if not old_files or not new_files or not any(
                path.parts[0] == INTERNAL_DIR_NAME for path in new_files):
            raise OSError("incomplete update files")
        backup.mkdir(parents=True, exist_ok=True)
        if any(backup.iterdir()):
            raise OSError("backup folder is not empty")
        report(percent, "backing_up", done=0, total=len(old_files))
        for index, relative in enumerate(old_files, 1):
            destination = backup / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            retry(lambda source=app / relative, target=destination: move(source, target))
            moved.append(relative)
            percent = file_progress(index, len(old_files), 10, 25)
            report(percent, "backing_up", done=index, total=len(old_files))
        report(25, "installing", done=0, total=len(new_files))
        for index, relative in enumerate(new_files, 1):
            destination = app / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            copied.append(relative)
            retry(lambda source=new / relative, target=destination: copy(source, target))
            percent = file_progress(index, len(new_files), 25, 95)
            report(percent, "installing", done=index, total=len(new_files))
        result = save("done")
        launch(app / APP_EXE_NAME)
        report(100, "done", from_version=options.from_version, to_version=APP_VERSION)
        return result
    except OSError as error:
        cause = str(error)
        report(percent, "rolling_back", error=cause)
        try:
            for relative in reversed(copied):
                target = app / relative
                if target.exists():
                    retry(target.unlink)
            for relative in reversed(moved):
                source = backup / relative
                destination = app / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                retry(lambda old=source, target=destination: move(old, target))
            result = save("rolled_back", cause)
            launch(app / APP_EXE_NAME)
            report(percent, "rolled_back", error=cause)
            return result
        except OSError as rollback_error:
            result = make_result(options, "failed", f"{cause}; rollback: {rollback_error}")
            try:
                write_result(options, result)
            except OSError:
                pass
            report(percent, "failed", error=result["error"], path=str(backup))
            return result
