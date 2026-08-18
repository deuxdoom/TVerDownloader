"""새 버전 확인과 그 자리에서의 업데이트.

예전에는 알리기만 하고 브라우저를 열어 줬다. 그 뒤로는 사용자가 zip을 받아
exe와 _internal을 손으로 덮어써야 했는데, 어느 파일을 지우고 어느 것을 남겨야
하는지가 분명하지 않아 bin이나 설정까지 함께 지우는 일이 생겼다.

이제 `지금 업데이트`를 누르면 여기서 끝까지 한다. 다만 **교체 자체는 여기서
하지 않는다** — 실행 중인 exe는 자기를 덮어쓸 수 없어서, 받아 놓기까지만 하고
나머지는 배치에 넘긴다(src/self_update.py).

**소스로 돌릴 때는 확인만 하고 버튼을 내준다.** 바꿀 exe가 없고, 개발 중인 작업
폴더를 릴리스 내용으로 덮어쓰면 고치던 것이 날아간다. autostart가 같은 이유로
같은 판단을 한다.
"""
from __future__ import annotations

import re
import webbrowser

from src import self_update
from src.message import confirm, confirm_single, confirm_with_link, notify
from src.utils import github_api_headers, is_rate_limited, rate_limit_message

API_URL = "https://api.github.com/repos/deuxdoom/TVerDownloader/releases/latest"
RELEASE_PAGE_URL = "https://github.com/deuxdoom/TVerDownloader/releases/latest"

CHECK_TIMEOUT = 10
"""새 버전을 물어보는 데 주는 시간(초).

시작할 때 한 번 도는 부가 기능이라 오래 붙잡지 않는다. 실패하면 다음 실행 때
다시 확인하면 된다.
"""


def _norm(tag: str) -> tuple[int, int, int]:
    """버전 태그를 비교 가능한 튜플로 변환합니다. (예: 'v2.3.1' -> (2, 3, 1))"""
    if not tag: return (0, 0, 0)
    t = tag.strip()
    if t.lower().startswith("v"): t = t[1:]
    t = t.split('-', 1)[0].split('+', 1)[0]
    nums = re.findall(r'\d+', t)[:3]
    parts = [int(x) for x in nums] + [0] * (3 - len(nums))
    return tuple(parts[:3])


def _newer(cur: str, latest: str) -> bool:
    """최신 버전 태그가 현재 버전보다 높은지 비교합니다."""
    return _norm(latest) > _norm(cur)


def fetch_latest(log=print) -> dict | None:
    """최신 릴리스 정보를 받아 온다. 실패하면 None.

    시작 시 한 번만 부르는 부가 기능이라 재시도하지 않는다. 한 번 실패하면
    다음 실행 때 다시 확인하면 된다.
    """
    try:
        import requests
    except ImportError:
        return None

    try:
        response = requests.get(API_URL, headers=github_api_headers("TVerDownloader-UpdateCheck"),
                                timeout=CHECK_TIMEOUT)
    except requests.exceptions.RequestException:
        return None

    if is_rate_limited(response):
        log(f"[알림] 업데이트 확인을 건너뜁니다. {rate_limit_message(response)}")
        return None
    if response.status_code != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def release_tag(release: dict) -> str:
    """릴리스에서 버전 태그를 꺼낸다. 없으면 빈 문자열."""
    return release.get("tag_name") or release.get("name") or ""


def has_newer(release: dict, current_version: str) -> bool:
    """이 릴리스가 지금 쓰는 것보다 새것인지."""
    tag = release_tag(release)
    return bool(tag) and _newer(current_version, tag)


def maybe_show_update(parent, current_version: str, log=print, *,
                      pending_downloads: int = 0) -> None:
    """새 버전이 있으면 안내하고, 원하면 그 자리에서 갈아 끼운다.

    시작할 때 도는 확인이라 **새 버전이 없으면 조용히 지나간다.** 눌러서 하는
    확인은 그러면 안 되므로 정보 창 쪽은 prompt_and_update를 직접 쓴다.

    pending_downloads는 지금 받는 중이거나 기다리는 중인 항목 수다. 업데이트는
    앱을 껐다 켜는 일이라, 받던 것이 있으면 먼저 물어봐야 한다.
    """
    release = fetch_latest(log)
    if not release or not has_newer(release, current_version):
        return
    prompt_and_update(parent, release, log, pending_downloads=pending_downloads)


def prompt_and_update(parent, release: dict, log=print, *,
                      pending_downloads: int = 0, single_button: bool = False) -> None:
    """새 버전 안내창을 띄우고, 받겠다고 하면 끝까지 진행한다.

    새 버전이 있다는 것은 부르는 쪽이 이미 확인한 상태다(has_newer). 시작할 때의
    확인과 정보 창의 확인이 같은 흐름을 쓰도록 여기 하나로 모았다.

    **단추 구성만 다르다.** 시작할 때 뜨는 것은 묻지도 않았는데 나온 창이라
    `지금 업데이트`와 `내역 확인` 둘을 준다. 정보 창에서 눌러 들어온 쪽은 이미
    받겠다고 누른 것이라 단추 하나면 된다(single_button). 어느 쪽이든 그만두려면
    창을 닫으면 된다.
    """
    latest_tag = release_tag(release)
    html_url = release.get("html_url") or RELEASE_PAGE_URL
    theme = _theme_of(parent)
    asset = self_update.pick_asset(release.get("assets"))

    if not self_update.supported() or asset is None:
        _offer_browser(parent, latest_tag, html_url, theme, asset is None)
        return

    body = (f"새 버전 {latest_tag}이(가) 나왔습니다.\n\n"
            "지금 받아서 바로 적용할 수 있습니다.\n"
            "적용할 때 프로그램이 한 번 꺼졌다 켜집니다.")

    def open_release_page():
        """무엇이 바뀌었는지 브라우저로 보여 준다. 창은 닫히고 받지는 않는다."""
        log(f"[업데이트] 릴리스 페이지를 엽니다: {html_url}")
        try:
            webbrowser.open(html_url)
        except Exception:
            pass

    if single_button:
        accepted = confirm_single(parent, "새 버전 확인", body,
                                  ok_text="자동 업데이트",
                                  icon_name="download", theme=theme)
    else:
        accepted = confirm_with_link(parent, "새 버전 확인", body,
                                     yes_text="지금 업데이트", link_text="내역 확인",
                                     on_link=open_release_page,
                                     icon_name="download", theme=theme)
    if not accepted:
        log(f"[업데이트] 새 버전 {latest_tag}을(를) 나중에 받기로 했습니다.")
        return

    if pending_downloads and not confirm(
            parent, "진행 중인 작업이 있습니다",
            f"받는 중이거나 기다리는 항목이 {pending_downloads}개 있습니다.\n\n"
            "업데이트하면 프로그램이 꺼지면서 이 작업들이 중단됩니다.\n"
            "받다 만 파일은 지워지지만, 목록은 다시 켤 때 대기 상태로 되살아납니다.\n"
            "그래도 계속할까요?",
            icon_name="cancel", color_key="danger", theme=theme,
            yes_text="중단하고 업데이트", no_text="취소"):
        log("[업데이트] 진행 중인 작업이 있어 업데이트를 취소했습니다.")
        return

    start_update(parent, asset, latest_tag, log, theme)


def _theme_of(parent) -> str:
    """부모 창이 쓰는 테마. 알 수 없으면 밝은 쪽."""
    config = getattr(parent, "config", None)
    if isinstance(config, dict):
        return config.get("theme", "light")
    return "light"


def _offer_browser(parent, latest_tag: str, html_url: str, theme: str,
                   no_asset: bool) -> None:
    """자동으로 갈아 끼울 수 없을 때 받으러 갈 자리만 알려 준다.

    소스로 돌리는 중이거나 릴리스에 zip이 붙어 있지 않을 때다. 두 경우 모두
    자동으로 할 수 있는 것이 없으므로 안내만 하고 사람에게 넘긴다.

    **물어보지 않는다.** 단추는 갈 자리 하나뿐이고, 그만두려면 창을 닫으면 된다.
    """
    reason = ("릴리스에서 내려받을 파일을 찾지 못했습니다.\n"
              if no_asset else "")
    if confirm_single(parent, "새 버전 확인",
                      f"새 버전 {latest_tag}이(가) 나왔습니다.\n{reason}"
                      "직접 받으시려면 릴리스 페이지를 열어 주세요.",
                      ok_text="릴리스 페이지 열기",
                      icon_name="download", theme=theme):
        try:
            webbrowser.open(html_url)
        except Exception:
            pass


def start_update(parent, asset: dict, latest_tag: str, log=print,
                 theme: str = "light") -> None:
    """받아서 준비하고, 다 되면 배치에 넘기고 앱을 끝낸다.

    준비가 끝나기 전까지는 지금 쓰는 버전에 아무 일도 일어나지 않는다. 어느
    단계에서 실패하든 그냥 안내하고 물러나면 된다.
    """
    from src.ui.update_dialog import UpdateProgressDialog

    work = self_update.prepare_workspace()
    if work is None:
        notify(parent, "업데이트할 수 없습니다",
               "프로그램 폴더에 쓸 수 없어 업데이트를 시작하지 못했습니다.\n\n"
               "프로그램을 쓰기 가능한 폴더(예: 바탕화면, D:\\ 등)로 옮긴 뒤\n"
               "다시 시도해 주세요.",
               icon_name="info", color_key="warn", theme=theme)
        log("[업데이트] 프로그램 폴더에 쓸 수 없어 중단했습니다.")
        return

    log(f"[업데이트] 새 버전 {latest_tag} 내려받기를 시작합니다.")
    dialog = UpdateProgressDialog(asset.get("browser_download_url", ""), work,
                                  latest_tag, parent, theme)
    ok = dialog.exec()

    if not ok:
        self_update.cleanup_workspace()
        reason = dialog.failure_reason
        if reason:
            log(f"[업데이트] 실패: {reason}")
            notify(parent, "업데이트하지 못했습니다",
                   f"{reason}\n\n지금 쓰는 버전은 그대로입니다.",
                   icon_name="info", color_key="warn", theme=theme)
        else:
            log("[업데이트] 사용자가 취소했습니다.")
        return

    log("[업데이트] 준비 완료. 프로그램을 다시 시작합니다.")
    if not self_update.launch_updater(work):
        self_update.cleanup_workspace()
        notify(parent, "업데이트하지 못했습니다",
               "교체를 시작하지 못했습니다. 지금 쓰는 버전은 그대로입니다.",
               icon_name="info", color_key="warn", theme=theme)
        log("[업데이트] 교체 프로그램을 띄우지 못했습니다.")
        return

    quit_app = getattr(parent, "quit_application", None)
    if callable(quit_app):
        quit_app()
