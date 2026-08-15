import shutil
import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QCoreApplication

import _bootstrap
_bootstrap.setup()

from src.threads.download_thread import DownloadThread
from src.threads.conversion_thread import ConversionThread
from src.utils import load_config

app = QCoreApplication(sys.argv)
results = []


def build(download_subs, embed, fmt="vtt"):
    t = DownloadThread(
        url="https://tver.jp/episodes/ep1", download_folder="D:/out",
        ytdlp_exe_path="yt-dlp.exe", ffmpeg_exe_path="bin/ffmpeg.exe",
        output_template="%(title)s.%(ext)s", quality_format="bv*+ba/b",
        download_subtitles=download_subs, embed_subtitles=embed, subtitle_format=fmt)
    return t._build_command("D:/out/video.mp4")


def check(name, cmd, must_have, must_not_have):
    ok = all(f in cmd for f in must_have) and all(f not in cmd for f in must_not_have)
    subs = [a for a in cmd if "sub" in a.lower() or a == "ja"]
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"        자막 인자: {subs}")
    if not ok:
        print(f"        기대 포함 {must_have} / 기대 제외 {must_not_have}")
    results.append(ok)


print("=== _build_command 자막 인자 ===")
check("임베드 모드: --write-subs 없이 --embed-subs만",
      build(True, True),
      ["--embed-subs", "--sub-langs", "ja"],
      ["--write-subs", "--sub-format", "--no-write-subs"])

check("별도 저장(vtt): --write-subs + --sub-format",
      build(True, False, "vtt"),
      ["--write-subs", "--sub-format", "vtt", "--sub-langs", "ja"],
      ["--embed-subs", "--no-write-subs"])

check("별도 저장(srt): 받을 땐 vtt, 이후 ffmpeg로 변환",
      build(True, False, "srt"),
      ["--write-subs", "--sub-format", "vtt"],
      ["--embed-subs", "--no-write-subs"])

check("자막 끔: --no-write-subs만",
      build(False, False),
      ["--no-write-subs"],
      ["--write-subs", "--embed-subs", "--sub-langs", "--sub-format"])

print()
print("=== SRT 후변환 조건 ===")
for embed, fmt, expect in [(True, "srt", False), (False, "srt", True),
                           (False, "vtt", False), (True, "vtt", False)]:
    t = DownloadThread(url="u", download_folder="d", ytdlp_exe_path="y",
                       ffmpeg_exe_path="bin/ffmpeg.exe", output_template="%(title)s.%(ext)s",
                       quality_format="q", download_subtitles=True,
                       embed_subtitles=embed, subtitle_format=fmt)
    actual = t.download_subtitles and not t.embed_subtitles and t.subtitle_format == "srt"
    ok = actual == expect
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  embed={embed!s:5s} fmt={fmt}  -> 변환시도={actual}")


print()
print("=== _handle_sidecar_subtitles ===")


def sidecar_case(name, sidecars, delete_original, expect_moved, expect_left):
    tmp = Path(tempfile.mkdtemp(prefix="subs_"))
    try:
        old = tmp / "아메토크 제1화.mp4"
        old.write_bytes(b"video")
        for s in sidecars:
            (tmp / s).write_text("sub", encoding="utf-8")
        new = tmp / "아메토크 제1화_h264.mp4"
        new.write_bytes(b"converted")

        conv = ConversionThread("u", str(old), "ffmpeg", None, "h264",
                                delete_original, "cpu", {})
        logs = []
        conv.log.connect(logs.append)
        conv._handle_sidecar_subtitles(old, new)

        after = sorted(p.name for p in tmp.iterdir())
        moved = [n for n in after if n.startswith("아메토크 제1화_h264.") and not n.endswith(".mp4")]
        left = [n for n in after if n.startswith("아메토크 제1화.") and not n.endswith(".mp4")]
        ok = sorted(moved) == sorted(expect_moved) and sorted(left) == sorted(expect_left)
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        print(f"        결과 파일: {after}")
        for l in logs:
            print(f"        | {l}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


sidecar_case("임베드 모드(사이드카 없음) -> 조용히 통과",
             [], True, [], [])

sidecar_case("별도 저장 vtt + 원본 삭제 -> 이름 변경",
             ["아메토크 제1화.ja.vtt"], True,
             ["아메토크 제1화_h264.ja.vtt"], [])

sidecar_case("별도 저장 srt + 원본 유지 -> 복사",
             ["아메토크 제1화.ja.srt"], False,
             ["아메토크 제1화_h264.ja.srt"], ["아메토크 제1화.ja.srt"])

print()
print("=== 스템이 같은 경우(컨테이너 변환) ===")
tmp = Path(tempfile.mkdtemp(prefix="subs_"))
try:
    old = tmp / "clip.mp4"; old.write_bytes(b"v")
    (tmp / "clip.ja.vtt").write_text("s", encoding="utf-8")
    new = tmp / "clip.avi"; new.write_bytes(b"v")
    conv = ConversionThread("u", str(old), "ffmpeg", "avi", None, True, "cpu", {})
    conv._handle_sidecar_subtitles(old, new)
    after = sorted(p.name for p in tmp.iterdir())
    ok = after == ["clip.avi", "clip.ja.vtt", "clip.mp4"]
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  스템 동일 -> 손대지 않음: {after}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
cfg = load_config()
print("=== 기본 설정 ===")
for key in ("download_subtitles", "embed_subtitles", "subtitle_format"):
    print(f"  {key} = {cfg[key]!r}")
ok = cfg["download_subtitles"] is True and cfg["embed_subtitles"] is False and cfg["subtitle_format"] == "vtt"
results.append(ok)
print(("PASS" if ok else "FAIL") + "  기본값: 자막 받기 O, 임베드 X, vtt")

print()
print("ALL PASS" if all(results) else "SOME FAILED")
sys.exit(0 if all(results) else 1)
