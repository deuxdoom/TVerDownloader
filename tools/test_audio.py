import subprocess
import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QCoreApplication

import _bootstrap
_bootstrap.setup()

from src.threads.download_thread import DownloadThread
from src.utils import (ERROR_STATUSES, FINISHED_STATUSES, NO_AUDIO_STATUS,
                       resolve_ffprobe_path)

app = QCoreApplication(sys.argv)
results = []
FFMPEG = _bootstrap.BIN_DIR / "ffmpeg.exe"
FFPROBE = _bootstrap.BIN_DIR / "ffprobe.exe"


def report(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


def make_thread(ffmpeg_path):
    return DownloadThread(
        url="https://tver.jp/episodes/ep1", download_folder="D:/out",
        ytdlp_exe_path="yt-dlp.exe", ffmpeg_exe_path=str(ffmpeg_path),
        output_template="%(title)s.%(ext)s", quality_format="bv*+ba/b",
        download_subtitles=False, embed_subtitles=False, subtitle_format="vtt")


print("=== 1. resolve_ffprobe_path ===")
report("실제 ffmpeg 옆의 ffprobe를 찾는다",
       resolve_ffprobe_path(str(FFMPEG)) == str(FFPROBE),
       f"{resolve_ffprobe_path(str(FFMPEG))}")
report("없는 경로면 None", resolve_ffprobe_path("D:/nope/ffmpeg.exe") is None)
report("빈 문자열이면 None", resolve_ffprobe_path("") is None)
report("None이면 None", resolve_ffprobe_path(None) is None)

print()
print("=== 2. 실제 mp4로 음성 스트림 판정 ===")
tmp = Path(tempfile.mkdtemp(prefix="audio_"))
try:
    with_audio = tmp / "with_audio.mp4"
    no_audio = tmp / "no_audio.mp4"
    subprocess.run([str(FFMPEG), "-y", "-v", "error",
                    "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=10",
                    "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
                    "-c:v", "libx264", "-c:a", "aac", "-shortest", str(with_audio)],
                   check=True, capture_output=True)
    subprocess.run([str(FFMPEG), "-y", "-v", "error",
                    "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=10",
                    "-c:v", "libx264", str(no_audio)],
                   check=True, capture_output=True)
    print(f"        생성: with_audio={with_audio.stat().st_size}B, no_audio={no_audio.stat().st_size}B")

    t = make_thread(FFMPEG)
    logs = []
    t.progress.connect(lambda url, p: logs.append(p.get("log", "")))

    report("음성 있는 파일 -> True", t._has_audio_stream(str(with_audio)) is True)
    report("음성 없는 파일 -> False", t._has_audio_stream(str(no_audio)) is False)

    logs.clear()
    broken = tmp / "broken.mp4"
    broken.write_bytes(b"not a video")
    got = t._has_audio_stream(str(broken))
    report("깨진 파일 -> None (검증 건너뜀)", got is None,
           f"반환={got!r} 로그={[l for l in logs if l][:1]}")

    logs.clear()
    t_noprobe = make_thread("D:/nope/ffmpeg.exe")
    t_noprobe.progress.connect(lambda url, p: logs.append(p.get("log", "")))
    got = t_noprobe._has_audio_stream(str(with_audio))
    report("ffprobe 없음 -> None (검증 건너뜀)", got is None,
           f"반환={got!r} 로그={[l for l in logs if l][:1]}")

    print()
    print("=== 3. 최종 상태 결정 ===")

    def final_status(thread, path, audio_result):
        """_execute_download 말미의 판정 로직을 그대로 재현한다."""
        thread._final_filepath = str(path)
        status = "완료"
        if audio_result is False:
            status = NO_AUDIO_STATUS
        return status

    for label, path, expect in (("음성 있음", with_audio, "완료"),
                                ("음성 없음", no_audio, NO_AUDIO_STATUS),
                                ("검증 불가", broken, "완료")):
        t._final_filepath = str(path)
        res = t._has_audio_stream(str(path))
        status = NO_AUDIO_STATUS if res is False else "완료"
        report(f"{label} -> 상태 '{status}'", status == expect,
               f"_has_audio_stream={res!r}")

    print()
    print("=== 4. 경고 로그 내용 ===")
    logs.clear()
    t._final_filepath = str(no_audio)
    t._warn_missing_audio()
    msg = next(l for l in logs if l)
    ok = ("경로" in msg and "음성" in msg and str(len(str(no_audio))) in msg
          and msg.startswith("[오류]"))
    report("경로 길이와 원인 추정을 담는다", ok)
    for line in msg.splitlines():
        print(f"        | {line}")
finally:
    import shutil as _sh
    _sh.rmtree(tmp, ignore_errors=True)

print()
print("=== 5. 상태 집합 반영 ===")
report("NO_AUDIO_STATUS가 ERROR_STATUSES에 있다 (재다운로드 메뉴)",
       NO_AUDIO_STATUS in ERROR_STATUSES, f"{sorted(ERROR_STATUSES)}")
report("NO_AUDIO_STATUS가 FINISHED_STATUSES에 있다 (재생/폴더 버튼)",
       NO_AUDIO_STATUS in FINISHED_STATUSES, f"{sorted(FINISHED_STATUSES)}")
report("'완료'는 ERROR_STATUSES에 없다", "완료" not in ERROR_STATUSES)

print()
print("ALL PASS" if all(results) else "SOME FAILED")
sys.exit(0 if all(results) else 1)
