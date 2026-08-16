"""주소가 앱으로 들어오는 길을 맡는다.

들어오는 자리는 셋이다 — 입력창에 직접 넣는 것, 클립보드에 복사된 것,
창으로 끌어다 놓는 것. 하는 일이 같아서 한 모듈에 둔다. **밖에서 온 글을
받아 주소인지 가리고, 아니면 어디가 틀렸는지 알리고, 맞으면 대기열이나 다중
추가 창으로 보낸다.**

**가리는 규칙이 두 갈래인 것은 일부러다.** 클립보드와 드롭은 match_tver_url()
전체 일치로 좁게 본다. 우리가 묻지도 않았는데 반응하는 자리라, 아닌 것을
집어 오면 방해가 된다. 입력창과 다중 추가는 is_media_url()로 넓게 본다.
사람이 직접 넣은 것이라 TVer가 아니어도 yt-dlp가 받을 수 있고, 판단은 그쪽에
넘긴다.

**어디로 보낼지에는 순서가 있다**(on_clipboard_changed). 다중 추가 창이 떠
있으면 그 창에, 입력창에 이미 TVer 주소가 있으면 둘을 모아 다중 추가 창으로,
비어 있으면 입력창에. 입력창에 주소가 아닌 글이 있으면 아무것도 하지 않는다 —
직접 적던 내용을 치우고 자리를 가져갈 이유가 없다.

받는 것까지 자동으로 하지는 않는다. 눈으로 보고 누르는 편이 낫고, 잘못 복사한
것이 곧바로 대기열에 들어가면 되돌리기 번거롭다.

Qt가 창에 직접 보내는 드래그 이벤트는 창에 남을 수밖에 없어, 창이 받아서
urls_from_mime / accept_dropped_urls로 넘긴다. 대기열에 넣는 일은 창의
_request_add_task 하나로 모은다 — 중복 확인 창이 그 안에 있다.
"""

from typing import List, Optional

from PyQt6.QtGui import QGuiApplication

from src.utils import is_media_url, match_tver_url
from src.message import notify
from src.bulk_dialog import BulkAddDialog


class InputSources:
    """입력창·클립보드·드롭 세 경로를 맡는 조작 묶음."""

    BAD_URL_PREVIEW = 5
    """알림 창에 그대로 보여 줄 잘못된 줄 수. 나머지는 개수로만 줄인다.

    스무 줄을 통째로 붙여 놓으면 창이 화면을 넘고, 어차피 한 줄만 봐도 무엇을
    잘못 넣었는지 알 수 있다.
    """

    BAD_URL_ELIDE = 42
    """알림 창에 보여 줄 한 줄의 최대 길이. 넘으면 뒤를 줄인다."""

    def __init__(self, window):
        self.window = window
        self._clipboard_connected = False
        self._last_clipboard_url = ""
        self._bulk_dialog = None

    def apply_clipboard_watch(self, enabled: bool):
        """클립보드 감시를 켜거나 끈다.

        끄면 시그널 연결 자체를 끊는다. 콜백 안에서 그냥 돌아 나오게 두면 꺼 놓고도
        복사할 때마다 클립보드를 읽게 되는데, 이 기능을 꺼림칙해하는 쪽에서는
        그것부터가 문제다.
        """
        clipboard = QGuiApplication.clipboard()
        if enabled and not self._clipboard_connected:
            clipboard.dataChanged.connect(self.on_clipboard_changed)
            self._clipboard_connected = True
        elif not enabled and self._clipboard_connected:
            try:
                clipboard.dataChanged.disconnect(self.on_clipboard_changed)
            except TypeError:
                pass
            self._clipboard_connected = False

    def on_clipboard_changed(self):
        """복사된 TVer 주소를 받아 둘 자리를 정한다.

        받기까지 자동으로 하지는 않는다. 주소가 맞는지 눈으로 보고 누르는 편이
        낫고, 잘못 복사한 것이 곧바로 대기열에 들어가면 되돌리기 번거롭다.

        입력창은 한 칸이라 둘째 주소부터는 갈 곳이 없었다. 예전에는 그때 그냥
        돌아 나와서, 주소를 연달아 복사하면 감시가 꺼진 것처럼 보였다. 이제는
        이미 든 주소와 함께 다중 추가 창으로 옮기고, 그 창이 열려 있는 동안은
        복사할 때마다 한 줄씩 쌓는다.

        입력창에 TVer 주소가 아닌 글이 들어 있으면 예전처럼 아무것도 하지 않는다.
        직접 적던 내용을 치우고 그 자리를 가져갈 이유가 없다.

        시리즈 주소도 즐겨찾기 칸이 아니라 이 흐름으로 보낸다. 복사한 사람이
        지금 받고 싶은 것인지 즐겨찾기에 두고 싶은 것인지 알 수 없으므로, 손이
        가 있는 자리 하나로 모은다.
        """
        window = self.window
        url = match_tver_url(QGuiApplication.clipboard().text())
        if not url or url == self._last_clipboard_url:
            return
        if self._bulk_dialog is not None:
            self._last_clipboard_url = url
            if self._bulk_dialog.append_url(url):
                window.append_log(f"[클립보드] 다중 추가 창에 넣었습니다: {url}")
            return
        pending = match_tver_url(window.ui.url_input.text())
        if pending and pending != url:
            self._last_clipboard_url = url
            window.append_log("[클립보드] 주소가 하나 더 들어와 다중 추가 창으로 모읍니다.")
            window.ui.url_input.clear()
            if not self.open_bulk_add([pending, url]):
                window.ui.url_input.setText(pending)
            return
        if window.ui.url_input.text().strip():
            return
        self._last_clipboard_url = url
        window.ui.url_input.setText(url)
        window.append_log(f"[클립보드] 주소를 입력창에 넣었습니다: {url}")

    def urls_from_mime(self, mime) -> List[str]:
        """드롭된 데이터에서 TVer 주소만 순서대로 골라낸다.

        브라우저는 주소 하나를 끌어도 text/uri-list와 text/plain을 함께 실어 보낸다.
        양쪽을 다 보고 중복을 걷어내야 같은 주소가 두 번 들어오지 않는다. 판별은
        클립보드와 같은 전체 일치 규칙이라, 주소가 아닌 것을 끌어다 놓으면 창이
        아예 받지 않는다.
        """
        candidates: List[str] = []
        if mime.hasUrls():
            candidates.extend(url.toString() for url in mime.urls())
        if mime.hasText():
            candidates.extend(mime.text().splitlines())
        found: List[str] = []
        for candidate in candidates:
            url = match_tver_url(candidate)
            if url and url not in found:
                found.append(url)
        return found

    def accept_dropped_urls(self, urls: List[str]):
        """끌어다 놓은 주소를 개수에 따라 다른 흐름으로 넘긴다.

        하나면 입력창에 채우기만 한다. 클립보드와 달리 이미 들어 있는 내용을
        덮어쓰는데, 창을 겨냥해 끌어다 놓은 것은 지금 이걸 받겠다는 뜻이라
        직전에 적어 둔 것보다 나중 의사가 앞선다.

        여럿이면 다중 추가 창을 미리 채워서 연다. 곧바로 대기열에 넣지 않는 것은
        무엇이 들어왔는지 확인하고 지울 기회를 주기 위해서다.
        """
        window = self.window
        if len(urls) == 1:
            window.ui.url_input.setText(urls[0]); window.ui.url_input.setFocus()
            window.append_log(f"[드롭] 주소를 입력창에 넣었습니다: {urls[0]}")
            return
        window.append_log(f"[드롭] 주소 {len(urls)}개를 받았습니다. 다중 추가 창을 엽니다.")
        self.open_bulk_add(urls)

    def _notify_bad_url(self, title: str, lead: str, rejected: List[str]):
        """주소가 아닌 줄을 알린다.

        어느 줄이 걸렸는지 보여 준다. '주소가 아닙니다'만으로는 여러 줄을 넣었을 때
        어디를 고쳐야 할지 알 수 없다.
        """
        shown = [self._elide(text, self.BAD_URL_ELIDE)
                 for text in rejected[:self.BAD_URL_PREVIEW]]
        left = len(rejected) - len(shown)
        if left:
            shown.append(f"... 외 {left}개")
        body = "\n".join([lead, "", *shown, "",
                          "http:// 또는 https:// 로 시작하는",
                          "영상 페이지 주소를 넣어주세요."])
        notify(self.window, title, body, icon_name="info", color_key="warn",
               theme=self.window.config.get("theme", "light"))

    @staticmethod
    def _elide(text: str, limit: int) -> str:
        """긴 글을 앞부분만 남기고 줄인다."""
        return text if len(text) <= limit else text[:limit - 1] + "…"

    def process_input_url(self):
        """입력창의 주소를 받는다. 주소가 아니면 알리고 그대로 둔다.

        예전에는 무엇이 들었든 yt-dlp에 넘겼다. 문장이나 낱말을 잘못 붙여넣으면
        카드가 하나 생겼다가 오류로 끝나고, 왜 실패했는지는 로그를 봐야 알 수 있었다.

        입력칸을 비우지 않는 이유는, 여기까지 온 글은 대개 고쳐서 다시 쓸 것이기
        때문이다. 지워 버리면 붙여넣은 것을 다시 찾아와야 한다.
        """
        window = self.window
        url = window.ui.url_input.text().strip()
        if not url: return
        if not is_media_url(url):
            self._notify_bad_url("주소를 확인해주세요",
                                 "다운로드할 수 있는 주소가 아닙니다.", [url])
            return
        self.process_url(url); window.ui.url_input.clear()

    def process_url(self, url: str):
        window = self.window
        if not window.env_ready: window.append_log("[알림] 아직 프로그램 초기화가 완료되지 않았습니다. 잠시 후 다시 시도해주세요."); return
        if not window._ensure_download_folder(): window.append_log("[알림] 다운로드 폴더가 선택되지 않아 작업이 취소되었습니다."); return
        if "/series/" in url:
            window.append_log(f"[시리즈] 분석을 시작합니다: {url}")
            window.series_parser.parse('single', [url])
        else:
            window._request_add_task(url)

    def open_bulk_add(self, initial_urls: Optional[List[str]] = None) -> bool:
        """다중 추가 창을 연다. initial_urls를 주면 그 목록으로 채워서 연다.

        창을 실제로 띄웠는지 돌려준다. 클립보드에서 모아 넘길 때는 입력창을 비운
        뒤에 부르므로, 준비가 안 돼 돌아 나온 경우 호출부가 원래 주소를 되돌려
        놓아야 한다.

        떠 있는 동안 self._bulk_dialog에 자기를 걸어 둔다. exec()가 중첩 이벤트
        루프라서 그 사이에도 클립보드 감시가 계속 돌고, 새 주소를 이 창에 넣으려면
        어느 창이 열려 있는지 알아야 한다.
        """
        window = self.window
        if not window.env_ready:
            window.append_log("[알림] 아직 프로그램 초기화가 완료되지 않았습니다. 잠시 후 다시 시도해주세요.")
            return False
        if not window._ensure_download_folder():
            window.append_log("[알림] 다운로드 폴더가 선택되지 않아 작업이 취소되었습니다.")
            return False
        dialog = BulkAddDialog(window, initial_urls)
        self._bulk_dialog = dialog
        try:
            accepted = dialog.exec()
        finally:
            self._bulk_dialog = None
        if accepted:
            urls = dialog.get_urls()
            rejected = [u for u in urls if not is_media_url(u)]
            urls = [u for u in urls if is_media_url(u)]
            if rejected:
                window.append_log(f"[알림] 주소가 아닌 {len(rejected)}줄을 건너뜁니다.")
                self._notify_bad_url("건너뛴 줄이 있습니다",
                                     "주소가 아니어서 넣지 않은 줄입니다.", rejected)
            normal_urls = [u for u in urls if "/series/" not in u]
            series_urls = [u for u in urls if "/series/" in u]
            for url in normal_urls: window._request_add_task(url)
            if series_urls: window.series_parser.parse('bulk', series_urls)
        return True
