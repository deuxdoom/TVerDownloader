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
APP_NAME_BY_CODE = {
    "ko": "티버 다운로더",
    "jp": "TVer ダウンローダー",
}
"""i18n 언어 코드 -> 앱 이름. i18n.py를 여기서 최상단 import하면 순환(i18n.py가
이미 이 파일의 get_resource_path를 쓴다)이 생겨 함수 안에서 지연 import한다 -
titlelogo.py의 build_logo가 get_resource_path를 지연 import하는 것과 같은 이유다.
"""


def localized_app_name(language: QLocale.Language | None = None) -> str:
    """앱이 지금 쓰는 언어에 맞는 이름. language를 넘기면 그 OS 언어로 가정한다(검증용)."""
    from src import i18n
    code = (i18n.code_for_os_language(language)
           if language is not None else i18n.current_code())
    return APP_NAME_BY_CODE.get(code, APP_NAME_FALLBACK)


CONFIG_FILE = "downloader_config.json"
DEFAULT_PARALLEL = 5
PARALLEL_MIN = 1
PARALLEL_MAX = 20
FILENAME_TITLE_MAX_LENGTH = 80

MAX_TOTAL_CONNECTIONS = 20
"""동시 다운로드 수 × 조각 수의 상한. TVer에 한꺼번에 걸리는 연결 수다.

각자 범위 안이어도 곱하면 320까지 간다. 지역 제한 차단은 한번 걸리면 IP를 바꾸기 전까지
계속 막혀(yt-dlp #13888) 되돌리기 어려우므로 고르는 자리에서 아예 막는다. 설정 파일을
손으로 고친 경우는 어느 쪽을 줄여야 할지 근거가 없어 막지 않는다.
"""

DEFAULT_FRAGMENTS = 4
FRAGMENTS_MIN = 1
FRAGMENTS_MAX = 16
"""영상 하나에서 한꺼번에 받을 조각 수(yt-dlp의 -N).

TVer은 HLS라 조각이 수백 개인데 yt-dlp 기본값 1은 그것을 하나씩 받아 회선을 다 쓰지
못한다. 기본값 4는 동시 다운로드 수와 곱해지기 때문이고(4 × 5 = 20), 상한 16 위로는
회선이 아니라 서버 쪽에서 막히기 시작한다.
"""

HARDWARE_ENCODERS = ("cpu", "nvidia")
"""고를 수 있는 코덱 변환 가속.

3.4.0에서 Intel(QSV)·AMD(AMF)를 뺐다 - 확인해 본 적 없는 선택지를 띄워 두면 고른
사람만 조용히 다른 품질을 받는다.
"""

PREFERRED_CODECS = ("original", "avc", "hevc")
"""고를 수 있는 재인코딩 코덱.

3.4.0에서 VP9·AV1을 뺐다 - CPU 인코딩이 한 편에 몇 시간이고 그 파일을 편집 도구가
대부분 읽지 못해, 호환성이라는 목적과 반대로 갔다.
"""

RETIRED_HARDWARE_ENCODERS = {"intel": "cpu", "amd": "cpu"}
RETIRED_PREFERRED_CODECS = {"vp9": "original", "av1": "original"}
"""이제 없는 값이 설정 파일에 남아 있을 때 대신 쓸 값.

말없이 바꾸지 않는다 - retired_option_notes()가 로그에 남길 문장을 만든다.
"""

STATUS_QUEUED = "queued"
STATUS_DOWNLOADING = "downloading"
STATUS_CANCELING = "canceling"
STATUS_CONVERTING = "converting"
STATUS_SUBTITLE_CONVERTING = "subtitle_converting"
STATUS_MERGING = "merging"
STATUS_EMBEDDING_SUBS = "embedding_subs"
STATUS_DONE = "done"
STATUS_ERROR = "error"
STATUS_CANCELED = "canceled"
STATUS_CONVERT_ERROR = "convert_error"
"""내부에서 주고받는 상태 코드(영어). 화면 문구가 곧 비교값이던 3.6.0까지의 방식을
버렸다 - widgets.py가 이 코드를 t()로 번역해서 보여준다. queue.json/urlhistory.json
에는 이 값이 저장되지 않으므로(전수 확인) 파일 마이그레이션은 필요 없다.
"""

NO_AUDIO_STATUS = "no_audio"
"""내려받기는 끝났지만 음성 트랙이 빠진 상태.

파일은 남으니 실패는 아니다. 재다운로드 대상이라 ERROR_STATUSES에 넣되 색은 따로 구분한다.
"""

def item_percent(percent, previous: int) -> int:
    """항목 하나의 진행률(0~100)을 정리한다. 값이 없으면 이전 값을 지킨다.

    **여기 오는 percent는 이미 항목 전체 기준이다** - 조각 수를 아는 DownloadThread가
    환산을 끝내고 보낸다. 값이 없을 때마다 0으로 떨어뜨리면 눈금이 깜빡이고, 카드와
    트레이가 같은 값을 보여야 하므로 이 정리는 여기 한 곳에서만 한다.
    """
    if percent is None:
        return previous
    try:
        value = float(percent)
    except (TypeError, ValueError):
        return previous
    return int(max(0.0, min(100.0, value)))


def format_duration(seconds) -> str:
    """재생 시간을 '45분'으로 만든다. 알 수 없으면 빈 문자열 - 부르는 쪽이 라벨을 숨긴다.

    분으로 적는 것은 카드에서 재생·폴더 단추 옆 좁은 자리를 쓰기 때문이다. **1분이 안
    되는 것만 '45초'로 적는다** - 드물지만 그때 '1분'으로 올리면 실제보다 길게 보인다.
    """
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    from src.i18n import t
    total = round(value)
    if total < 60:
        return t("card.duration_seconds", value=max(1, total))
    return t("card.duration_minutes", value=round(total / 60))


ERROR_STATUSES = {STATUS_ERROR, STATUS_CANCELED, STATUS_CONVERT_ERROR, NO_AUDIO_STATUS}

FINISHED_STATUSES = {STATUS_DONE, NO_AUDIO_STATUS}
"""파일이 손에 남는 종료 상태. 재생·폴더 열기 버튼을 띄울지 판단한다."""


TVER_URL_RE = re.compile(
    r"^https?://(?:www\.)?tver\.jp/(?:episodes|series)/[A-Za-z0-9_-]+(?:[/?#]\S*)?$",
    re.IGNORECASE)
"""클립보드에서 받아들일 TVer 주소.

에피소드와 시리즈만, 전체 일치로 본다 - 주소가 섞인 긴 글에 멋대로 반응하지 않게.
"""


def match_tver_url(text: str) -> Optional[str]:
    """텍스트가 TVer 주소면 다듬어 돌려주고, 아니면 None."""
    candidate = (text or "").strip()
    return candidate if TVER_URL_RE.match(candidate) else None


TVER_ID_RE = re.compile(
    r"^https?://(?:www\.)?tver\.jp/(episodes|series)/([A-Za-z0-9_-]+)", re.IGNORECASE)
"""TVer 주소에서 종류와 ID만 뽑는다. 뒤에 붙은 쿼리·프래그먼트는 보지 않는다."""


def canonical_url(text: str) -> str:
    """중복을 가릴 때 쓸 주소. TVer면 종류와 ID만 남기고, 아니면 그대로 둔다.

    같은 회차라도 공유 경로에 따라 `?utm_source=...`나 `#comment`가 붙어 오는데, 주소를
    글자 그대로 견주면 **같은 영상이 대기열에 둘 서고 이미 받은 것도 다시 받는다.** 만들어질
    파일 이름은 메타데이터에서 나와 같으므로, `--force-overwrites`와 겹치면 두 프로세스가
    한 파일을 함께 쓴다.

    **TVer가 아닌 곳은 절대 손대지 않는다.** 유튜브처럼 쿼리에 영상 ID가 든 곳이 있어
    (`youtube.com/watch?v=...`), 떼면 아예 다른 영상을 가리키거나 주소가 깨진다.
    """
    url = (text or "").strip()
    matched = TVER_ID_RE.match(url)
    if not matched:
        return url
    return f"https://tver.jp/{matched.group(1).lower()}/{matched.group(2)}"


MEDIA_URL_RE = re.compile(
    r"^https?://[^\s/?#]+\.[^\s/?#]+(?:[/?#]\S*)?$", re.IGNORECASE)
"""yt-dlp에 넘겨 볼 만한 주소인지 가르는 최소 조건.

사이트는 가리지 않는다(yt-dlp가 다루는 곳이 천 곳을 넘는다). 여기서 보는 것은 '애초에
주소인가'뿐이다. 체계(scheme)를 반드시 요구하지 않으면 'memo.txt'나 '3.14'까지 점이 든
호스트로 보여 거르는 의미가 없어진다.
"""


def is_media_url(text: str) -> bool:
    """yt-dlp에 넘겨 볼 만한 주소인지."""
    return bool(MEDIA_URL_RE.match((text or "").strip()))


def resolve_ffprobe_path(ffmpeg_path: str):
    """ffmpeg 경로에서 짝이 되는 ffprobe 경로를 찾는다. 없으면 None.

    확장자가 붙은 경우를 먼저 본다 - 'ffmpeg'가 경로 중간에 든 설치본에서 엉뚱한 치환을 피한다.
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

    User-Agent가 없으면 GitHub이 403으로 막는다. 주체별로 다른 이름을 주면 할당량을 되짚을 수 있다.
    """
    return {"Accept": "application/vnd.github+json", "User-Agent": user_agent}


def is_rate_limited(response) -> bool:
    """호출 한도에 걸린 응답인지 판별한다.

    403은 권한 문제로도, 429는 과부하로도 온다. 남은 호출 수가 0이라고 명시된 경우만 본다.
    """
    if response.status_code not in RATE_LIMIT_STATUSES:
        return False
    return response.headers.get("X-RateLimit-Remaining") == "0"


def rate_limit_reset_text(response) -> str:
    """X-RateLimit-Reset(에포크 초)을 읽을 수 있는 시각으로. 없거나 숫자가 아니면 빈 글."""
    raw = response.headers.get("X-RateLimit-Reset", "")
    try:
        return datetime.fromtimestamp(int(raw)).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def rate_limit_message(response) -> str:
    """한도 초과 안내 문구. 리셋 시각을 알 수 있으면 함께 붙인다.

    두 조각을 코드에서 이어 붙이는 것은 configparser가 값 앞의 공백을 지워, 뒷문장을
    ' 제한은...'처럼 띄어쓰기로 시작하게 적어 둘 수 없기 때문이다.
    """
    from src.i18n import t
    reset = rate_limit_reset_text(response)
    head = t("common.rate_limited")
    return f"{head} {t('common.rate_limit_reset', reset=reset)}" if reset else head


def get_resource_path(relative_path) -> Path:
    """개발 실행과 PyInstaller 번들(onefile/onedir) 양쪽에서 리소스 경로를 돌려준다.

    PyInstaller는 두 모드 모두 sys._MEIPASS를 설정한다(onedir은 _internal 폴더). 번들이
    아닐 때는 현재 작업 디렉터리가 아니라 이 파일이 속한 프로젝트 루트를 쓴다.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = Path(__file__).resolve().parent.parent
    return Path(base) / relative_path


def load_config() -> Dict[str, Any]:
    """설정 파일 로드(없으면 기본값). dict 병합으로 부분 업데이트 허용."""
    config = {
        "theme": "light",
        "language": "system",
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
        "auto_check_favorites_on_start": False,
        "auto_update_check": True,
        "always_on_top": False,
        "log_visible": True,
        "clipboard_watch": True,
        "series_exclude_keywords": ["予告", "ティザー", "ダイジェスト", "メイキング",
                                    "ナビ", "解説放送版"],
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
    """설정을 저장하고 성공 여부를 돌려준다. 실패를 조용히 삼키지 않는다.

    **임시 파일에 썼다가 바꿔치기한다.** 목적지를 바로 열면 쓰는 도중에 막혔을 때 잘린
    JSON이 그 이름으로 남고, 다음 실행에서 `load_config`가 그것을 못 읽어 **설정이 통째로
    기본값으로 돌아간다.** 저장소 쪽 세 곳(queue·favorites·history)이 모두 이렇게 쓴다.
    """
    target = Path(CONFIG_FILE)
    tmp = target.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(config, indent=4, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, target)
        return True
    except (OSError, TypeError, ValueError):
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
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
    """설정 파일에서 온 조각 수를 쓸 수 있는 값으로 다듬는다. 3.4.0에서 생겨 옛 키가 없다."""
    try:
        value = int(float(config.get("concurrent_fragments", DEFAULT_FRAGMENTS)))
    except (ValueError, TypeError):
        return DEFAULT_FRAGMENTS
    return max(FRAGMENTS_MIN, min(FRAGMENTS_MAX, value))


def _choice_value(raw: Any) -> Optional[str]:
    """설정 파일에서 온 선택지 값을 견줄 수 있는 문자열로 만든다.

    **문자열이 아닌 것은 전부 None으로 접는다** - 손으로 고친 설정에서 목록이나 사전이
    들어오는데, 그대로 사전 조회에 넘기면 해시가 없어 TypeError로 터진다.
    """
    return raw.strip().lower() if isinstance(raw, str) else None


def _canonicalize_choice(raw: Any, allowed: tuple, retired: Dict[str, str],
                         default: str) -> str:
    """설정 파일에서 온 선택지 하나를 다듬는다. 목록에 없으면 정해 둔 대체값으로 간다."""
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

    **load_config에서 갈아 끼우지 않는 이유가 이것이다** - 거기서 고치면 원래 무엇이었는지가
    사라져 알릴 내용이 남지 않는다. 설정 파일에 되쓰지도 않는다.
    """
    from src.i18n import t
    notes: List[str] = []
    for key, allowed, retired, kind in (
        ("hardware_encoder", HARDWARE_ENCODERS, RETIRED_HARDWARE_ENCODERS,
         t("log.retired_encoder_kind")),
        ("preferred_codec", PREFERRED_CODECS, RETIRED_PREFERRED_CODECS,
         t("log.retired_codec_kind")),
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
            notes.append(t("log.retired_unknown", kind=kind, was=was))
        else:
            notes.append(t("log.retired_replaced", kind=kind, was=was,
                           replacement=replacement))
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
    from src.i18n import t
    error_message = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    log_file = "TVerDownloader_crash.log"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(error_message)
    error_box = QMessageBox()
    error_box.setIcon(QMessageBox.Icon.Critical)
    error_box.setWindowTitle(t("dialog.crash_title"))
    error_box.setText(t("dialog.crash_text"))
    error_box.setInformativeText(t("dialog.crash_detail", path=log_file))
    error_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    error_box.exec()


def open_site_link():
    """공식 소개 페이지를 연다. 받는 법과 쓰는 법이 한자리에 정리된 곳이다."""
    webbrowser.open("https://deuxdoom.github.io/TVerDownloader/")


def open_developer_link():
    webbrowser.open("https://www.youtube.com/@LE_SSERAFIM")
