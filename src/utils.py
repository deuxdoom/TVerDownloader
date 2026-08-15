import json
import os
import re
import sys
import traceback
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from PyQt6.QtCore import QLocale
from PyQt6.QtWidgets import QMessageBox

from src.shortcuts import defaults as default_shortcuts

APP_NAME_FALLBACK = "TVer Downloader"
APP_NAME_BY_LANGUAGE = {
    QLocale.Language.Korean: "티버 다운로더",
    QLocale.Language.Japanese: "TVer ダウンローダー",
}


def localized_app_name(language: QLocale.Language | None = None) -> str:
    """OS 표시 언어에 맞는 앱 이름을 돌려준다. 모르는 언어면 영문 이름.

    language를 넘기면 그 언어로 계산한다(검증용). 평소에는 시스템 언어를 쓴다.
    """
    if language is None:
        language = QLocale.system().language()
    return APP_NAME_BY_LANGUAGE.get(language, APP_NAME_FALLBACK)


CONFIG_FILE = "downloader_config.json"
DEFAULT_PARALLEL = 5
PARALLEL_MIN = 1
PARALLEL_MAX = 20
FILENAME_TITLE_MAX_LENGTH = 80

NO_AUDIO_STATUS = "음성 없음"
"""내려받기는 끝났지만 음성 트랙이 빠진 상태.

파일은 남아 있으니 실패는 아니지만 그대로 두면 안 되는 결과다. 재다운로드
대상으로 삼으려고 ERROR_STATUSES에 넣지만, 색만은 따로 구분한다.
"""

ERROR_STATUSES = {"오류", "취소됨", "실패", "중단", "변환 오류", NO_AUDIO_STATUS}

FINISHED_STATUSES = {"완료", NO_AUDIO_STATUS}
"""파일이 손에 남는 종료 상태. 재생·폴더 열기 버튼을 띄울지 판단한다."""


TVER_URL_RE = re.compile(
    r"^https?://(?:www\.)?tver\.jp/(?:episodes|series)/[A-Za-z0-9_-]+(?:[/?#]\S*)?$",
    re.IGNORECASE)
"""클립보드에서 받아들일 TVer 주소.

에피소드와 시리즈만 본다. 전체 일치를 요구해서, 주소가 섞인 긴 글을 복사했을 때
멋대로 반응하지 않게 한다. 뒤에 붙는 물음표나 조각(#) 부분은 허용한다.
"""


def match_tver_url(text: str) -> Optional[str]:
    """텍스트가 TVer 주소면 다듬어 돌려주고, 아니면 None."""
    candidate = (text or "").strip()
    return candidate if TVER_URL_RE.match(candidate) else None


MEDIA_URL_RE = re.compile(
    r"^https?://[^\s/?#]+\.[^\s/?#]+(?:[/?#]\S*)?$", re.IGNORECASE)
"""yt-dlp에 넘겨 볼 만한 주소인지 가르는 최소 조건.

yt-dlp가 다루는 사이트는 천 곳이 넘어 목록으로 가릴 수 없다. 여기서 거르려는 것은
'어느 사이트인가'가 아니라 '애초에 주소가 아닌 것'이다. 잘못 붙여넣은 문장이나
낱말, 파일 경로가 그대로 넘어가면 카드가 하나 생겼다가 오류로 끝난다.

체계(scheme)를 반드시 요구한다. 없이도 받아 주면 'memo.txt'나 '3.14' 같은 것까지
점이 든 호스트로 보여 거르는 의미가 없어진다. 호스트에 점을 요구하는 것도 같은
이유이고, 덕분에 사이트 판단은 여전히 yt-dlp가 한다.
"""


def is_media_url(text: str) -> bool:
    """yt-dlp에 넘겨 볼 만한 주소인지."""
    return bool(MEDIA_URL_RE.match((text or "").strip()))


def resolve_ffprobe_path(ffmpeg_path: str):
    """ffmpeg 경로에서 짝이 되는 ffprobe 경로를 찾는다. 없으면 None.

    같은 폴더에 함께 설치되므로 이름만 바꿔 본다. 확장자가 붙은 경우를 먼저
    시도해야 'ffmpeg'가 경로 중간에 들어간 설치본에서 엉뚱한 치환을 피할 수 있다.
    """
    if not ffmpeg_path:
        return None
    for candidate in (ffmpeg_path.replace("ffmpeg.exe", "ffprobe.exe"),
                      ffmpeg_path.replace("ffmpeg", "ffprobe")):
        if os.path.exists(candidate):
            return candidate
    return None

RATE_LIMIT_STATUSES = (403, 429)


def github_api_headers(user_agent: str) -> Dict[str, str]:
    """GitHub API 호출에 붙이는 공통 헤더.

    User-Agent가 없으면 GitHub이 403으로 막는다. 호출 주체별로 다른 이름을 주면
    할당량이 어디서 소모됐는지 응답 헤더로 되짚을 수 있다.
    """
    return {"Accept": "application/vnd.github+json", "User-Agent": user_agent}


def is_rate_limited(response) -> bool:
    """호출 한도에 걸린 응답인지 판별한다.

    403은 권한 문제로도 오고 429는 일시적 과부하로도 온다. 둘 다 기다린다고
    풀리는 게 아니라서, 남은 호출 수가 0이라고 명시된 경우만 한도 초과로 본다.
    """
    if response.status_code not in RATE_LIMIT_STATUSES:
        return False
    return response.headers.get("X-RateLimit-Remaining") == "0"


def rate_limit_reset_text(response) -> str:
    """X-RateLimit-Reset(에포크 초)을 사람이 읽을 수 있는 시각으로 바꾼다.

    헤더가 없거나 숫자가 아니면 빈 문자열을 돌려준다. 호출부는 시각 안내를
    생략하고 나머지 문구만 보이면 된다.
    """
    raw = response.headers.get("X-RateLimit-Reset", "")
    try:
        return datetime.fromtimestamp(int(raw)).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def rate_limit_message(response) -> str:
    """한도 초과 안내 문구. 리셋 시각을 알 수 있으면 함께 붙인다."""
    reset = rate_limit_reset_text(response)
    tail = f" 제한은 {reset} 이후에 풀립니다." if reset else ""
    return f"GitHub API 호출 한도를 초과했습니다(인증 없이 시간당 60회).{tail}"


def get_resource_path(relative_path) -> Path:
    """개발 실행과 PyInstaller 번들(onefile/onedir) 양쪽에서 리소스 경로를 돌려준다.

    PyInstaller는 두 모드 모두에서 sys._MEIPASS를 설정한다(onedir은 _internal 폴더).
    번들이 아닐 때는 현재 작업 디렉터리가 아니라 이 파일이 속한 프로젝트 루트를 쓴다.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = Path(__file__).resolve().parent.parent
    return Path(base) / relative_path


def load_config() -> Dict[str, Any]:
    """설정 파일 로드(없으면 기본값). dict 병합으로 부분 업데이트 허용."""
    config = {
        "theme": "light",
        "download_folder": "",
        "max_concurrent_downloads": DEFAULT_PARALLEL,
        "filename_parts": {
            "series": True, "upload_date": True, "episode_number": True,
            "episode": True, "id": True,
        },
        "filename_order": ["series", "upload_date", "episode_number", "episode", "id"],
        "quality": "bv*+ba/b",
        "preferred_codec": "original",
        "auto_check_favorites_on_start": True,
        "always_on_top": False,
        "log_visible": True,
        "clipboard_watch": False,
        "conversion_format": "none",
        "delete_on_conversion": False,
        "series_exclude_keywords": ["予告", "SP", "ダイジェスト", "ナビ", "解説放送版"],
        "hardware_encoder": "cpu",
        "quality_cpu_h264_crf": 26,
        "quality_cpu_h265_crf": 31,
        "quality_cpu_vp9_crf": 36,
        "quality_cpu_av1_crf": 41,
        "quality_gpu_cq": 30,
        "embed_thumbnail": False,
        "download_subtitles": True,
        "embed_subtitles": False,
        "subtitle_format": "vtt",
        "ignore_ssl_errors": False,
        "close_action": "exit",
        "shortcuts": default_shortcuts(),
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                for k, v in loaded.items():
                    if isinstance(v, dict) and k in config and isinstance(config[k], dict):
                        config[k].update(v)
                    else:
                        config[k] = v
        except (json.JSONDecodeError, IOError):
            pass

    config["max_concurrent_downloads"] = canonicalize_config_parallel(config)
    return config


def save_config(config: dict) -> bool:
    """설정을 저장하고 성공 여부를 반환합니다. (실패를 조용히 삼키지 않음)"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return True
    except (IOError, OSError, TypeError):
        return False


def construct_filename_template(config: Dict[str, Any]) -> str:
    parts_cfg = config.get("filename_parts", {})
    order = config.get("filename_order", [])
    key_map = {
        "series": "%(series)s",
        "upload_date": "%(upload_date>%Y-%m-%d)s",
        "episode_number": "%(episode_number)s",
        "episode": "%(title)s",
        "id": "[%(id)s]"
    }
    selected_parts = [key_map[key] for key in order if parts_cfg.get(key, False) and key in key_map]
    if parts_cfg.get("series"):
        return f"%(series,playlist_title)s/{' '.join(selected_parts)}.%(ext)s"
    else:
        return f"{' '.join(selected_parts)}.%(ext)s"


def canonicalize_config_parallel(config: Dict[str, Any]) -> int:
    def clamp(n: Any) -> int:
        try:
            val = int(float(n))
            return max(PARALLEL_MIN, min(PARALLEL_MAX, val))
        except (ValueError, TypeError):
            return DEFAULT_PARALLEL

    if "max_concurrent_downloads" in config:
        return clamp(config["max_concurrent_downloads"])

    legacy_keys = [
        "max_parallel", "max_parallel_downloads", "parallel_downloads",
        "concurrent_downloads", "max_concurrent", "concurrency"
    ]
    for key in legacy_keys:
        if key in config:
            return clamp(config[key])

    for container_key in ["downloads", "download", "settings", "general", "app"]:
        if isinstance(config.get(container_key), dict):
            nested_dict = config[container_key]
            for key in ["max_parallel", "parallel", "concurrent", "max"]:
                if key in nested_dict:
                    return clamp(nested_dict[key])
    return DEFAULT_PARALLEL


def get_startupinfo():
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return startupinfo
    return None


def open_file_location(filepath: str):
    try:
        if sys.platform == "win32":
            subprocess.run(["explorer", "/select,", os.path.normpath(filepath)])
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", filepath])
        else:
            subprocess.run(["xdg-open", os.path.dirname(filepath)])
    except Exception:
        pass


def handle_exception(exc_type, exc_value, exc_traceback):
    error_message = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    log_file = "TVerDownloader_crash.log"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(error_message)
    error_box = QMessageBox()
    error_box.setIcon(QMessageBox.Icon.Critical)
    error_box.setWindowTitle("오류")
    error_box.setText("치명적인 오류가 발생했습니다.")
    error_box.setInformativeText(f"오류 상세가 '{log_file}' 파일에 저장되었습니다.")
    error_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    error_box.exec()


def open_feedback_link():
    webbrowser.open("https://github.com/deuxdoom/TVerDownloader/issues")


def open_developer_link():
    webbrowser.open("https://www.youtube.com/@LE_SSERAFIM")
