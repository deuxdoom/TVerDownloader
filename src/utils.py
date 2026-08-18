import json
import os
import re
import sys
import traceback
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
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

MAX_TOTAL_CONNECTIONS = 20
"""동시 다운로드 수 × 조각 수의 상한. TVer에 한꺼번에 걸리는 연결 수다.

두 값은 각자 범위 안에 있어도 곱하면 얼마든지 커진다(20 × 16 = 320). 그러면
지역 제한 차단에 걸리는데, **그 차단은 한번 걸리면 IP를 바꾸기 전까지 계속
막히는 성질이라 값을 되돌려도 곧바로 낫지 않는다**(yt-dlp #13888). 되돌리기
어려운 실패라서, 고르는 자리에서 아예 막는다(SettingsDialog._save_settings).

설정 파일을 손으로 고친 경우는 막지 않는다. 어느 쪽을 줄여야 할지 정할 근거가
없어서다 — 사용자가 고른 값을 말없이 바꾸는 것보다 그대로 쓰는 편이 낫다.
"""

DEFAULT_FRAGMENTS = 4
FRAGMENTS_MIN = 1
FRAGMENTS_MAX = 16
"""영상 하나에서 한꺼번에 받을 조각 수(yt-dlp의 -N).

TVer은 HLS라 영상이 수백 개 조각으로 나뉘어 있고, **yt-dlp 기본값은 1이라 그것을
한 개씩 차례로 받는다.** 조각 하나하나는 작아서 왕복 시간이 그대로 대기 시간이
되므로, 회선을 다 쓰지 못한 채 느려지는 원인이 여기다.

**기본값을 4로 잡은 것은 동시 다운로드 수와 곱해지기 때문이다.** 이 값이 N이고
동시 다운로드가 M이면 TVer에 걸리는 연결은 N×M이다. 기본값(M=5)에서 4면 20인데,
여기서 더 늘리면 지역 제한 차단에 걸릴 위험이 커진다. 그 차단은 한번 걸리면 IP를
바꾸기 전까지 계속 막히는 성질이라(yt-dlp #13888) 되돌리기가 어렵다.

상한을 16으로 둔 것은 그 위로는 조각을 더 벌려도 회선이 아니라 서버 쪽에서
막히기 시작해서다. 1로 두면 이 기능을 끈 것과 같다.
"""

HARDWARE_ENCODERS = ("cpu", "nvidia")
"""고를 수 있는 코덱 변환 가속.

3.4.0에서 Intel(QSV)과 AMD(AMF)를 뺐다. 둘 다 화면에는 있었지만 가진 사람이
드물어 실제로 어떤 결과가 나오는지 확인해 본 적이 없고, 확인하지 않은 선택지를
띄워 두면 고른 사람만 조용히 다른 품질을 받는다.
"""

PREFERRED_CODECS = ("original", "avc", "hevc")
"""고를 수 있는 재인코딩 코덱.

3.4.0에서 VP9와 AV1을 뺐다. 둘 다 CPU 인코딩이 실시간의 몇 분의 일이라 한 편에
몇 시간이 걸리고, 그렇게 만든 파일을 편집 도구가 대부분 읽지 못한다. 재인코딩을
쓰는 이유가 호환성인데 목적과 반대로 가는 선택지였다.
"""

RETIRED_HARDWARE_ENCODERS = {"intel": "cpu", "amd": "cpu"}
RETIRED_PREFERRED_CODECS = {"vp9": "original", "av1": "original"}
"""이제 없는 값이 설정 파일에 남아 있을 때 대신 쓸 값.

**말없이 바꾸지 않는다.** 고른 적 있는 설정이 사라진 것이라 화면만 보고는
언제 어떻게 달라졌는지 알 수 없다. retired_option_notes()가 로그에 남길 문장을
만들고, 창이 켜질 때 그것을 찍는다.
"""

NO_AUDIO_STATUS = "음성 없음"
"""내려받기는 끝났지만 음성 트랙이 빠진 상태.

파일은 남아 있으니 실패는 아니지만 그대로 두면 안 되는 결과다. 재다운로드
대상으로 삼으려고 ERROR_STATUSES에 넣지만, 색만은 따로 구분한다.
"""

def item_percent(percent, previous: int) -> int:
    """항목 하나의 진행률(0~100)을 정리한다. 값이 없으면 이전 값을 지킨다.

    **여기 오는 percent는 이미 항목 전체 기준이다.** yt-dlp는 영상과 소리를 따로
    받으면서 조각마다 0->100을 새로 세는데, 그 환산은 조각 수를 아는
    DownloadThread가 끝내고 보낸다. 사이트마다 조각 수가 달라(유튜브는 하나로
    주기도 한다) 화면 쪽에서는 알 수 없는 값이다.

    진행률이 없는 알림(상태만 바뀐 경우)에 이전 값을 돌려주는 이유는, 그때마다
    0으로 떨어지면 받는 중에 눈금이 깜빡이기 때문이다.

    카드와 트레이가 같은 값을 보여야 하므로 이 정리는 여기 한 곳에서만 한다.
    """
    if percent is None:
        return previous
    try:
        value = float(percent)
    except (TypeError, ValueError):
        return previous
    return int(max(0.0, min(100.0, value)))


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
        "concurrent_fragments": DEFAULT_FRAGMENTS,
        "filename_parts": {
            "series": True, "upload_date": True, "episode_number": True,
            "episode": True, "id": True,
        },
        "filename_order": ["series", "upload_date", "episode_number", "episode", "id"],
        "quality": "bv*+ba/b",
        "preferred_codec": "original",
        "auto_check_favorites_on_start": True,
        "auto_update_check": True,
        "always_on_top": False,
        "log_visible": True,
        "clipboard_watch": False,
        "conversion_format": "none",
        "delete_on_conversion": False,
        "series_exclude_keywords": ["予告", "SP", "ダイジェスト", "ナビ", "解説放送版"],
        "hardware_encoder": "cpu",
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


def canonicalize_config_fragments(config: Dict[str, Any]) -> int:
    """설정 파일에서 온 조각 수를 쓸 수 있는 값으로 다듬는다.

    canonicalize_config_parallel과 달리 옛 키 이름을 찾지 않는다. 3.4.0에서
    처음 생긴 설정이라 다른 이름으로 저장된 적이 없다.
    """
    try:
        value = int(float(config.get("concurrent_fragments", DEFAULT_FRAGMENTS)))
    except (ValueError, TypeError):
        return DEFAULT_FRAGMENTS
    return max(FRAGMENTS_MIN, min(FRAGMENTS_MAX, value))


def _choice_value(raw: Any) -> Optional[str]:
    """설정 파일에서 온 선택지 값을 견줄 수 있는 문자열로 만든다.

    **문자열이 아닌 것은 전부 None으로 접는다.** 설정 파일은 손으로 고칠 수 있어
    목록이나 사전이 들어오기도 하는데, 그것을 그대로 사전 조회에 넘기면 해시가
    없어 TypeError로 터진다. 값을 다듬는 자리가 입력 때문에 죽으면 안 된다.
    """
    return raw.strip().lower() if isinstance(raw, str) else None


def _canonicalize_choice(raw: Any, allowed: tuple, retired: Dict[str, str],
                         default: str) -> str:
    """설정 파일에서 온 선택지 하나를 쓸 수 있는 값으로 다듬는다.

    canonicalize_config_parallel과 같은 자리에 있는 함수다. 다른 점은 자를 범위가
    아니라 고를 목록이 있다는 것뿐이라, 목록에 없으면 정해 둔 대체값으로 간다.
    """
    value = _choice_value(raw)
    if value in allowed:
        return value
    return retired.get(value, default)


def canonicalize_config_encoder(config: Dict[str, Any]) -> str:
    """설정 파일에서 온 코덱 변환 가속을 쓸 수 있는 값으로 다듬는다."""
    return _canonicalize_choice(config.get("hardware_encoder", "cpu"),
                                HARDWARE_ENCODERS, RETIRED_HARDWARE_ENCODERS, "cpu")


def canonicalize_config_codec(config: Dict[str, Any]) -> str:
    """설정 파일에서 온 선호 코덱을 쓸 수 있는 값으로 다듬는다."""
    return _canonicalize_choice(config.get("preferred_codec", "original"),
                                PREFERRED_CODECS, RETIRED_PREFERRED_CODECS, "original")


RETIRED_OPTION_LABELS = {
    "intel": "Intel (QSV)", "amd": "AMD (AMF)",
    "vp9": "VP9", "av1": "AV1",
}
"""로그에 적을 때 쓸 옛 값의 이름. 설정 화면에 있던 그대로 적어야 알아본다."""


def retired_option_notes(config: Dict[str, Any]) -> List[str]:
    """이제 없는 값을 쓰고 있었다면 그 사실을 알릴 문장들을 만든다.

    **load_config에서 값을 갈아 끼우지 않는 이유가 이것이다.** 거기서 고쳐 두면
    원래 무엇이었는지가 사라져 알릴 내용이 남지 않는다. 조각 수(-N)와 같은
    방식으로 읽는 자리에서 다듬고, 알리는 일은 창이 켜질 때 한 번만 한다.

    설정 파일에 되쓰지도 않는다. 사용자가 설정을 저장하는 순간 지금 값으로
    덮이고, 그때까지는 파일을 그대로 두는 편이 무엇을 골랐었는지 되짚기 좋다.
    """
    notes: List[str] = []
    for key, allowed, retired, kind in (
        ("hardware_encoder", HARDWARE_ENCODERS, RETIRED_HARDWARE_ENCODERS, "코덱 변환 가속"),
        ("preferred_codec", PREFERRED_CODECS, RETIRED_PREFERRED_CODECS, "선호 코덱"),
    ):
        raw = config.get(key)
        if raw is None:
            continue
        value = _choice_value(raw)
        if value in allowed:
            continue
        replacement = retired.get(value)
        was = RETIRED_OPTION_LABELS.get(value, str(raw))
        if replacement is None:
            notes.append(f"[설정] {kind} 설정값 '{was}'을(를) 알 수 없어 기본값으로 되돌립니다.")
        else:
            notes.append(f"[설정] {kind} '{was}'은(는) 더 이상 지원하지 않습니다. "
                         f"'{replacement}'(으)로 대신 진행합니다.")
    return notes


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
