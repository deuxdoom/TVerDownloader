"""업데이트 배치를 실제로 돌려 본다. (네트워크 불필요)

**문자열 검사만으로는 부족한 부분이다.** 배치 한 줄이 틀리면 사용자의 설치본이
사라지는데, 그건 실제로 돌려 봐야만 알 수 있다. tests/ 쪽은 배치 '내용'을 보고
여기서는 배치가 '한 일'을 본다.

진짜 exe 대신 probe.cmd를 쓴다. build_batch가 exe 이름을 인자로 받는 것이 이
때문이다 — 끝에서 다시 띄우는 동작까지 포함해 전 과정을 안전하게 돌려 볼 수 있다.

모래상자는 임시 폴더에 만들고 끝나면 지운다. 프로젝트 폴더나 dist는 건드리지 않는다.
"""

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import _bootstrap

_bootstrap.setup()

from src import self_update

results = []


def report(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


def build_sandbox(root: Path, with_new_exe: bool) -> Path:
    """앱 폴더 하나를 흉내 내어 만든다.

    사용자 것(bin·설정·기록)을 함께 넣어 둔다. 교체가 그것들을 건드리지 않는지
    보는 것이 이 검사의 절반이다.
    """
    app = root / "app"
    (app / "_internal" / "assets").mkdir(parents=True)
    (app / "_internal" / "old_only.txt").write_text("옛 버전에만 있던 파일", encoding="utf-8")
    (app / "_internal" / "assets" / "shared.txt").write_text("old", encoding="utf-8")
    old_marker = app / "relaunched_old.txt"
    (app / "probe.cmd").write_text(
        f'@echo off\r\necho old> "{old_marker}"\r\nexit /b 0\r\n', encoding="ascii")

    (app / "bin").mkdir()
    (app / "bin" / "ffmpeg.exe").write_text("사용자 바이너리", encoding="utf-8")
    (app / "downloader_config.json").write_text('{"theme":"dark"}', encoding="utf-8")
    (app / "urlhistory.json").write_text("{}", encoding="utf-8")
    (app / "thumbnails").mkdir()

    work = app / self_update.WORK_DIR_NAME
    new = work / self_update.NEW_DIR_NAME
    (new / "_internal").mkdir(parents=True)
    (work / self_update.BACKUP_DIR_NAME).mkdir(parents=True)
    (new / "_internal" / "new_only.txt").write_text("새 버전 파일", encoding="utf-8")
    (new / "_internal" / "assets").mkdir()
    (new / "_internal" / "assets" / "shared.txt").write_text("new", encoding="utf-8")
    if with_new_exe:
        marker = app / "relaunched.txt"
        (new / "probe.cmd").write_text(
            f'@echo off\r\necho relaunched> "{marker}"\r\nexit /b 0\r\n', encoding="ascii")
    return app


def run_batch(app: Path, work: Path, pid: int):
    """배치를 만들어 돌리고 (종료 코드, 출력)을 돌려준다.

    **출력을 버리지 않고 파일로 받아 둔다.** 예전에는 DEVNULL로 흘려버려서, cmd가
    주석 꼬리를 명령으로 실행하며 내던 오류를 검사가 보지 못했다. 실사용에서야 드러났다.

    파이프(capture_output)를 쓰면 안 된다. 배치 끝의 `start`가 probe.cmd를 새
    창으로 띄우는데, 스크립트를 여는 `start`는 cmd를 /K로 띄워 창이 남는다. 그
    자식이 파이프를 물고 있어 읽기가 영영 끝나지 않는다(실측: 10분 넘게 매달림).
    진짜 exe는 /K로 뜨지 않으므로 이건 검사 쪽 사정이다.

    stdin은 비워 준다. 되돌리기와 포기 경로 끝에는 pause가 있어서 — 사람이 무엇이
    잘못됐는지 읽고 창을 닫으라고 일부러 둔 것이다 — 그냥 돌리면 검사가 키 입력을
    기다리며 멈춘다. 빈 입력을 물리면 EOF로 곧장 지나간다.
    """
    batch = work / self_update.BATCH_NAME
    batch.write_text(self_update.build_batch(app, work, pid, exe_name="probe.cmd"),
                     encoding="utf-8")
    log_path = work / "run.log"
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(["cmd.exe", "/c", str(batch)], cwd=str(app),
                                stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT)
        code = proc.wait(timeout=180)
    return code, log_path.read_text(encoding="utf-8", errors="replace")


PARSE_ERROR_MARKS = ("is not recognized", "was unexpected", "구문이", "인식")
"""cmd가 배치를 잘못 읽었을 때 나오는 흔적.

goto로 되돌아갈 때 바이트 위치가 어긋나면 주석의 꼬리가 명령으로 실행된다.
파일은 멀쩡히 교체되므로 출력을 보지 않으면 통과한 것처럼 보인다.
"""


def check_clean(output: str, label: str):
    bad = [l.strip() for l in output.splitlines()
           if any(m in l for m in PARSE_ERROR_MARKS)]
    report(f"{label} — cmd가 배치를 잘못 읽지 않는다", not bad,
           bad[0][:70] if bad else "")


def wait_for_relaunch(marker: Path, seconds: float = 12.0) -> bool:
    """되돌린 뒤 다시 띄운 프로그램이 실제로 돌 때까지 기다린다.

    기다리지 않고 모래상자를 지우면, 뒤늦게 뜬 창이 사라진 파일을 찾으며
    '내부 또는 외부 명령이 아닙니다'를 콘솔에 뿌린다. 검사 쪽 경쟁일 뿐이지만
    사람이 보면 제품이 고장 난 것처럼 보인다. 기다리는 김에 되돌린 뒤 다시
    띄우는 것까지 함께 확인한다.
    """
    deadline = time.time() + seconds
    while time.time() < deadline:
        if marker.exists():
            return True
        time.sleep(0.25)
    return False


def spawn_waitee():
    """배치가 종료를 기다릴 대상 프로세스. 곧바로 죽여 '닫혔다'를 만든다."""
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


print("=== 1. 정상 교체 ===")
root = Path(tempfile.mkdtemp(prefix="tvd-update-ok-"))
try:
    app = build_sandbox(root, with_new_exe=True)
    work = app / self_update.WORK_DIR_NAME

    waitee = spawn_waitee()
    time.sleep(0.3)
    waitee.kill()
    waitee.wait()

    code, output = run_batch(app, work, waitee.pid)
    report("배치가 성공으로 끝난다", code == 0, f"종료 코드={code}")
    check_clean(output, "정상 교체")

    internal = app / "_internal"
    report("새 _internal이 제자리에 있다", (internal / "new_only.txt").is_file())
    report("옛 버전에만 있던 파일이 남지 않는다 (통째로 갈아 끼움)",
           not (internal / "old_only.txt").exists(),
           "덮어쓰기였다면 old_only.txt가 남아 용량을 차지한다")
    report("같은 이름의 파일도 새 것으로 바뀐다",
           (internal / "assets" / "shared.txt").read_text(encoding="utf-8") == "new")

    report("사용자 bin 폴더는 그대로다", (app / "bin" / "ffmpeg.exe").is_file())
    report("설정 파일은 그대로다",
           (app / "downloader_config.json").read_text(encoding="utf-8") == '{"theme":"dark"}')
    report("기록 파일은 그대로다", (app / "urlhistory.json").is_file())
    report("썸네일 폴더는 그대로다", (app / "thumbnails").is_dir())

    backup = work / self_update.BACKUP_DIR_NAME
    report("백업에 옛 버전이 남아 있다",
           (backup / "_internal" / "old_only.txt").is_file() and (backup / "probe.cmd").is_file())

    for _ in range(40):
        if (app / "relaunched.txt").exists():
            break
        time.sleep(0.25)
    report("끝나면 프로그램을 다시 띄운다", (app / "relaunched.txt").exists())
finally:
    shutil.rmtree(root, ignore_errors=True)

print()
print("=== 2. 교체 실패 -> 되돌리기 ===")
root = Path(tempfile.mkdtemp(prefix="tvd-update-fail-"))
try:
    app = build_sandbox(root, with_new_exe=False)
    work = app / self_update.WORK_DIR_NAME

    waitee = spawn_waitee()
    time.sleep(0.3)
    waitee.kill()
    waitee.wait()

    code, output = run_batch(app, work, waitee.pid)
    report("배치가 실패를 알린다", code == 1, f"종료 코드={code}")
    check_clean(output, "되돌리기")

    internal = app / "_internal"
    report("옛 _internal이 제자리로 돌아온다", (internal / "old_only.txt").is_file(),
           "되돌리기가 없으면 여기서 앱이 사라진다")
    report("절반만 들어간 새 파일이 남지 않는다", not (internal / "new_only.txt").exists())
    report("옛 실행 파일이 제자리로 돌아온다", (app / "probe.cmd").is_file())
    report("사용자 파일은 여전히 그대로다",
           (app / "bin" / "ffmpeg.exe").is_file() and (app / "downloader_config.json").is_file())
    report("되돌린 뒤 옛 버전을 다시 띄운다", wait_for_relaunch(app / "relaunched_old.txt"))
finally:
    shutil.rmtree(root, ignore_errors=True)

print()
print("=== 3. 본체가 안 닫히면 아무것도 건드리지 않는다 ===")
root = Path(tempfile.mkdtemp(prefix="tvd-update-busy-"))
try:
    app = build_sandbox(root, with_new_exe=True)
    work = app / self_update.WORK_DIR_NAME

    waitee = spawn_waitee()
    time.sleep(0.3)

    batch = work / self_update.BATCH_NAME
    batch.write_text(self_update.build_batch(app, work, waitee.pid, exe_name="probe.cmd"),
                     encoding="utf-8")
    log_path = work / "waitloop.log"
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(["cmd.exe", "/c", str(batch)], cwd=str(app),
                                stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT)
        time.sleep(6)
        still_running = proc.poll() is None
        report("살아 있는 동안에는 기다리기만 한다", still_running)
        report("기다리는 동안 파일을 건드리지 않는다",
               (app / "_internal" / "old_only.txt").is_file() and (app / "probe.cmd").is_file())
        proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass

    check_clean(log_path.read_text(encoding="utf-8", errors="replace"),
                "대기 루프를 여러 번 돌 때")

    waitee.kill()
    waitee.wait()
finally:
    shutil.rmtree(root, ignore_errors=True)

print()
print("=== 4. 파일이 잠겨 있으면 다시 시도하고, 끝내 안 되면 되돌린다 ===")
root = Path(tempfile.mkdtemp(prefix="tvd-update-lock-"))
try:
    app = build_sandbox(root, with_new_exe=True)
    work = app / self_update.WORK_DIR_NAME

    waitee = spawn_waitee()
    time.sleep(0.3)
    waitee.kill()
    waitee.wait()

    locked = work / self_update.NEW_DIR_NAME / "_internal" / "new_only.txt"
    holder = open(locked, "r+b")
    try:
        started = time.time()
        code, output = run_batch(app, work, waitee.pid)
        elapsed = time.time() - started
    finally:
        holder.close()

    report("잠긴 동안 다시 시도한다", "retrying" in output,
           f"재시도 {output.count('retrying')}회 ({elapsed:.0f}초) — 검사에서는 stdin을 막아"
           " timeout 명령이 곧바로 실패하므로 간격 없이 돈다."
           " 제품은 진짜 콘솔이라 회당 2초씩 기다린다(실측 확인).")
    report("끝내 안 되면 되돌린다", code == 1, f"종료 코드={code}")
    check_clean(output, "재시도 경로")
    report("되돌린 뒤 옛 버전이 제자리에 있다",
           (app / "_internal" / "old_only.txt").is_file() and (app / "probe.cmd").is_file(),
           "카스퍼스키가 갓 풀린 파일을 붙잡고 있을 때가 이 상황이다")
    report("사용자 파일은 그대로다",
           (app / "bin" / "ffmpeg.exe").is_file() and (app / "downloader_config.json").is_file())
    report("되돌린 뒤 옛 버전을 다시 띄운다", wait_for_relaunch(app / "relaunched_old.txt"))
finally:
    shutil.rmtree(root, ignore_errors=True)

print()
print("=== 5. 소스 실행에서는 기능이 꺼진다 ===")
report("supported()가 False", self_update.supported() is False)
report("app_dir()이 None", self_update.app_dir() is None)
report("작업 폴더를 만들지 않는다", self_update.prepare_workspace() is None)

print()
subprocess.run(["taskkill", "/F", "/FI", "WINDOWTITLE eq *probe.cmd*"],
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
"""검사가 띄운 probe.cmd 창을 걷어낸다.

`start`는 스크립트를 /K로 띄워 창이 남는다. 진짜 exe에서는 생기지 않는 일이라
제품 쪽은 손댈 것이 없고, 여기서만 치운다.
"""

print("ALL PASS" if all(results) else "SOME FAILED")
sys.exit(0 if all(results) else 1)
