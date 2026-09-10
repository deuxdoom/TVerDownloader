"""새 버전 확인과 그 자리에서의 업데이트.

예전에는 알리고 브라우저만 열어 줬는데, 어느 파일을 남겨야 하는지가 분명하지 않아 bin이나
설정까지 함께 지우는 일이 생겼다. **다만 교체 자체는 여기서 하지 않는다** - 실행 중인 exe는
자기를 덮어쓸 수 없어 받아 놓기까지만 하고 나머지는 배치에 넘긴다(src/self_update.py).

소스로 돌릴 때는 확인만 하고 버튼을 내준다. 개발 중인 폴더를 릴리스로 덮으면 고치던 것이 날아간다.
"""
from __future__ import annotations

import re
import webbrowser

from src import self_update
from src.i18n import t
from src.message import confirm, confirm_single, confirm_with_link, notify
from src.utils import github_api_headers, is_rate_limited, rate_limit_message

API_URL = "https://api.github.com/repos/deuxdoom/TVerDownloader/releases/latest"
RELEASE_PAGE_URL = "https://github.com/deuxdoom/TVerDownloader/releases/latest"

CHECK_TIMEOUT = 10
"""새 버전을 물어보는 데 주는 시간(초). 실패하면 다음 실행 때 다시 확인하면 된다."""


def _norm(tag: str) -> tuple[int, int, int]:
    """버전 태그를 비교 가능한 튜플로 바꾼다. ('v2.3.1' -> (2, 3, 1))"""
    if not tag: return (0, 0, 0)
    t = tag.strip()
    if t.lower().startswith("v"): t = t[1:]
    t = t.split('-', 1)[0].split('+', 1)[0]
    nums = re.findall(r'\d+', t)[:3]
    parts = [int(x) for x in nums] + [0] * (3 - len(nums))
    return tuple(parts[:3])


def _newer(cur: str, latest: str) -> bool:
    """최신 버전 태그가 현재 버전보다 높은지."""
    return _norm(latest) > _norm(cur)


def fetch_latest(log=print) -> dict | None:
    """최신 릴리스 정보를 받아 온다. 실패하면 None. 부가 기능이라 재시도하지 않는다."""
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
        log(t("log.update_rate_limited", message=rate_limit_message(response)))
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

    시작할 때 도는 확인이라 **새 버전이 없으면 조용히 지나간다** - 눌러서 하는 확인은
    그러면 안 되므로 정보 창 쪽은 prompt_and_update를 직접 쓴다. pending_downloads가
    있으면 앱을 껐다 켜는 일이라 먼저 물어본다.
    """
    release = fetch_latest(log)
    if not release or not has_newer(release, current_version):
        return
    prompt_and_update(parent, release, log, pending_downloads=pending_downloads)


def prompt_and_update(parent, release: dict, log=print, *,
                      pending_downloads: int = 0, single_button: bool = False) -> None:
    """새 버전 안내창을 띄우고, 받겠다고 하면 끝까지 진행한다.

    시작할 때의 확인과 정보 창의 확인이 같은 흐름을 쓰도록 여기 하나로 모았다. **단추
    구성만 다르다** - 시작할 때 뜨는 것은 묻지도 않았는데 나온 창이라 둘을 주고, 정보
    창에서 눌러 들어온 쪽은 이미 받겠다고 누른 것이라 하나면 된다(single_button).
    """
    latest_tag = release_tag(release)
    html_url = release.get("html_url") or RELEASE_PAGE_URL
    theme = _theme_of(parent)
    asset = self_update.pick_asset(release.get("assets"))

    if not self_update.supported() or asset is None:
        _offer_browser(parent, latest_tag, html_url, theme, asset is None)
        return

    body = t("update.available_body", tag=latest_tag)

    def open_release_page():
        """무엇이 바뀌었는지 브라우저로 보여 준다. 창은 닫히고 받지는 않는다."""
        log(t("log.update_open_release", url=html_url))
        try:
            webbrowser.open(html_url)
        except Exception:
            pass

    if single_button:
        accepted = confirm_single(parent, t("update.check_title"), body,
                                  ok_text=t("update.auto_update"),
                                  icon_name="download", theme=theme)
    else:
        accepted = confirm_with_link(parent, t("update.check_title"), body,
                                     yes_text=t("update.now"),
                                     link_text=t("update.changelog"),
                                     on_link=open_release_page,
                                     icon_name="download", theme=theme)
    if not accepted:
        log(t("log.update_later", tag=latest_tag))
        return

    if pending_downloads and not confirm(
            parent, t("update.pending_title"),
            t("update.pending_body", count=pending_downloads),
            icon_name="download", color_key="danger", theme=theme,
            yes_text=t("update.pending_yes"), no_text=t("common.cancel")):
        log(t("log.update_pending_canceled"))
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

    소스로 돌리는 중이거나 릴리스에 zip이 붙어 있지 않을 때다. **물어보지 않는다** -
    단추는 갈 자리 하나뿐이고, 그만두려면 창을 닫으면 된다.
    """
    reason = (t("update.no_asset_reason") + "\n") if no_asset else ""
    if confirm_single(parent, t("update.check_title"),
                      t("update.browser_body", tag=latest_tag, reason=reason),
                      ok_text=t("update.open_release_page"),
                      icon_name="download", theme=theme):
        try:
            webbrowser.open(html_url)
        except Exception:
            pass


def start_update(parent, asset: dict, latest_tag: str, log=print,
                 theme: str = "light") -> None:
    """받아서 준비하고, 다 되면 배치에 넘기고 앱을 끝낸다.

    준비가 끝나기 전까지는 지금 쓰는 버전에 아무 일도 일어나지 않는다.
    """
    from src.ui.update_dialog import UpdateProgressDialog

    work = self_update.prepare_workspace()
    if work is None:
        notify(parent, t("update.cannot_title"), t("update.cannot_body"),
               icon_name="info", color_key="warn", theme=theme)
        log(t("log.update_no_write"))
        return

    log(t("log.update_start", tag=latest_tag))
    dialog = UpdateProgressDialog(asset.get("browser_download_url", ""), work,
                                  latest_tag, parent, theme)
    ok = dialog.exec()

    if not ok:
        self_update.cleanup_workspace()
        reason = dialog.failure_reason
        if reason:
            log(t("log.update_failed", reason=reason))
            notify(parent, t("update.failed_title"),
                   t("update.failed_body", reason=reason),
                   icon_name="info", color_key="warn", theme=theme)
        else:
            log(t("log.update_user_canceled"))
        return

    log(t("log.update_ready"))
    if not self_update.launch_updater(work):
        self_update.cleanup_workspace()
        notify(parent, t("update.failed_title"), t("update.launch_failed_body"),
               icon_name="info", color_key="warn", theme=theme)
        log(t("log.update_launch_failed"))
        return

    quit_app = getattr(parent, "quit_application", None)
    if callable(quit_app):
        quit_app()
