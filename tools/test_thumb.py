import subprocess
import sys
import shutil
import tempfile
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QEventLoop

import _bootstrap
_bootstrap.setup()

from src.threads.download_thread import DownloadThread
from src.utils import load_config

app = QCoreApplication(sys.argv)
results = []
YT = str(_bootstrap.BIN_DIR / "yt-dlp.exe")
FFMPEG = str(_bootstrap.BIN_DIR / "ffmpeg.exe")
FFPROBE = str(_bootstrap.BIN_DIR / "ffprobe.exe")
URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def report(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


def make(folder, embed_thumbnail, template="%(title)s.%(ext)s"):
    return DownloadThread(
        url=URL, download_folder=str(folder), ytdlp_exe_path=YT, ffmpeg_exe_path=FFMPEG,
        output_template=template, quality_format="bv*+ba/b",
        download_subtitles=False, embed_subtitles=False, subtitle_format="vtt",
        embed_thumbnail=embed_thumbnail)


print("=== 1. 명령 조립 ===")
t_on = make("D:/out", True)
t_off = make("D:/out", False)
cmd_on = t_on._build_command("D:/out/v.mp4")
cmd_off = t_off._build_command("D:/out/v.mp4")
report("켜면 --embed-thumbnail 추가", "--embed-thumbnail" in cmd_on)
report("끄면 안 붙음", "--embed-thumbnail" not in cmd_off)
report("--write-thumbnail은 붙이지 않는다 (사이드카 방지)",
       "--write-thumbnail" not in cmd_on)

print()
print("=== 2. 설정 기본값 ===")
cfg = load_config()
report("embed_thumbnail 기본값 False", cfg.get("embed_thumbnail") is False,
       f"{cfg.get('embed_thumbnail')!r}")

print()
print("=== 3. 실제 다운로드: 켬 ===")
tmp = Path(tempfile.mkdtemp(prefix="thumb_"))
try:
    t = make(tmp, True)
    logs = []
    t.progress.connect(lambda u, p: logs.append(p.get("log", "")))
    done = {}
    t.finished.connect(lambda u, ok, path, meta: done.update(ok=ok, path=path))
    loop = QEventLoop(); t.finished.connect(lambda *a: loop.quit())
    t.start(); loop.exec(); t.wait()

    files = sorted(p.name for p in tmp.rglob("*") if p.is_file())
    video = Path(done.get("path") or "")
    ok = done.get("ok") and video.exists()
    report("다운로드 성공", bool(ok), f"파일={files}")

    streams = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries",
         "stream=index,codec_type,codec_name:stream_disposition=attached_pic",
         "-of", "csv=p=0", str(video)],
        capture_output=True, text=True).stdout.strip()
    has_cover = any(line.strip().endswith(",1") for line in streams.splitlines())
    report("mp4 안에 표지 스트림이 들어갔다", has_cover, streams.replace("\n", " | "))

    leftovers = [f for f in files if f.lower().endswith((".webp", ".png", ".jpg", ".jpeg"))]
    report("표지 이미지 파일이 남지 않는다", not leftovers, f"찌꺼기={leftovers}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
print("=== 4. 임베드 실패 감지 (_parse_line) ===")
t = make("D:/out", True)
report("초기값 False", t._thumbnail_embed_failed is False)
t._parse_line("ERROR: Postprocessing: Supported filetypes for thumbnail embedding are: mp3, mkv/mka, ogg/opus/flac, m4a/mp4/m4v/mov")
report("실제 yt-dlp 오류 문구를 잡는다", t._thumbnail_embed_failed is True)

for line in ("[download] 100% of 246.27KiB",
             "[Merger] Merging formats into \"v.mp4\"",
             "[EmbedThumbnail] mutagen: Adding thumbnail to \"v.mp4\"",
             "[info] Downloading video thumbnail 38 ..."):
    t2 = make("D:/out", True)
    t2._parse_line(line)
    ok = t2._thumbnail_embed_failed is False
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  정상 출력은 오탐 안 함: {line[:52]}")

t3 = make("D:/out", True)
t3._parse_line("WARNING: unable to embed the thumbnail using ffprobe & ffmpeg")
report("경고형 실패 문구도 잡는다", t3._thumbnail_embed_failed is True)

print()
print("=== 5. 임베드 실패 시 남은 이미지 정리 ===")
tmp = Path(tempfile.mkdtemp(prefix="clean_"))
try:
    video = tmp / "アメトーーク 第1話.mp4"
    video.write_bytes(b"video")
    for suffix in (".webp", ".png"):
        video.with_suffix(suffix).write_bytes(b"img")
    keep = tmp / "다른영상.webp"; keep.write_bytes(b"img")

    t = make(tmp, True)
    t._final_filepath = str(video)
    logs = []
    t.progress.connect(lambda u, p: logs.append(p.get("log", "")))
    t._cleanup_thumbnail_sidecars()

    after = sorted(p.name for p in tmp.iterdir())
    ok = after == ["アメトーーク 第1話.mp4", "다른영상.webp"]
    report("짝이 되는 이미지만 지우고 영상과 무관한 파일은 둔다", ok, f"남은 파일={after}")
    print(f"        로그: {[l for l in logs if l]}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
print("ALL PASS" if all(results) else "SOME FAILED")
sys.exit(0 if all(results) else 1)
