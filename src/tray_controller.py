"""트레이 아이콘과 창의 드나듦, 종료를 맡는다 - 창이 보이지 않을 때의 앱을 책임지는 덩이다.

트레이 메뉴·툴팁·진행률 아이콘도 여기서 그린다(예전에는 창 구성 쪽에 있어 계산과 그리기가 갈렸다).
**갱신은 1초에 한 번으로 묶는다**(TRAY_SYNC_INTERVAL_MS). 진행률이 초당 여러 줄 오는데
그때마다 손대면 아이콘 여덟 장을 다시 그리는 일과 셸 호출이 따라붙는다.

값을 계산하는 곳(refresh_status)과 반영하는 곳(_sync)을 나눈 것은, 개수는 queue_changed가
진행률은 progress_updated가 물어 오는데 둘이 오는 시점이 달라서다.
"""

import webbrowser

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction, QFont

from src import autostart
from src.appicon import app_icon_with_progress, get_app_icon
from src.utils import localized_app_name
from src.i18n import t
from src.message import confirm
from src.qtparts import RoundedMenu


class TrayController:
    """트레이 표시와 창 드나듦, 종료를 맡는 조작 묶음."""

    TRAY_SYNC_INTERVAL_MS = 1000
    """트레이를 다시 그리는 최소 간격.

    진행률이 초당 여러 줄 온다. 툴팁도 같이 묶는 것은 setToolTip이 글자만 바꾸는 것처럼
    보여도 트레이 영역을 다시 등록하는 셸 호출이기 때문이다.
    """

    GITHUB_URL = "https://github.com/deuxdoom/TVerDownloader"

    def __init__(self, window):
        self.window = window
        self._version = ""
        self._name = ""
        self._icon_percent = None
        """트레이에 마지막으로 그린 진행률. 개수만 바뀌었을 때 아이콘 여덟 장을 다시 그리지 않는다."""
        self.autostart_action = None
        self._queue_counts = (0, 0)
        self._tray_state = (0, 0, None)
        self._tray_shown = None
        self._timer = QTimer(window)
        self._timer.setInterval(self.TRAY_SYNC_INTERVAL_MS)
        self._timer.timeout.connect(self._sync)
        self._minimize_timer = QTimer(window)
        self._minimize_timer.setSingleShot(True)
        self._minimize_timer.timeout.connect(self._finish_minimized)
        self._notice_timer = QTimer(window)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.timeout.connect(self._notify_hidden)
        self._hide_notice_shown = False

    def setup(self, app_version: str):
        """트레이 아이콘과 우클릭 메뉴를 만든다.

        첫 항목은 '<앱 이름> 열기'다 - 이름만 적으면 제목처럼 읽혀 눌러도 되는 줄인지
        알기 어렵다. 구분선은 여는 일 / 설정 / 끝내는 일 세 덩이만 가른다. 시작 프로그램
        체크는 열 때마다 레지스트리를 다시 읽는다 - 밖에서 꺼 놓았을 수 있다.
        """
        tray_icon = self.window.tray_icon
        tray_icon.setIcon(get_app_icon())
        self._version = app_version
        self._name = f"{localized_app_name()} {app_version}"
        self.update_status(0, 0, None)
        tray_icon.setContextMenu(self._build_menu())
        tray_icon.show()

    def _build_menu(self) -> RoundedMenu:
        """트레이 메뉴 한 벌. 항목의 부모를 메뉴로 두어 메뉴를 헐면 함께 사라지게 한다."""
        window = self.window
        menu = RoundedMenu()

        restore_action = self._action(menu, t("tray.open", app_name=localized_app_name()),
                                      window.bring_to_front)
        bold = QFont(restore_action.font()); bold.setBold(True)
        restore_action.setFont(bold)
        menu.addAction(restore_action)
        menu.addSeparator()

        self.autostart_action = QAction(t("tray.autostart"), menu)
        self.autostart_action.setCheckable(True)
        self.autostart_action.toggled.connect(window.set_autostart)
        if not autostart.supported():
            self.autostart_action.setEnabled(False)
            self.autostart_action.setToolTip(t("tray.autostart_disabled_tooltip"))
        menu.addAction(self.autostart_action)

        menu.addAction(self._action(menu, t("tray.github"),
                                    lambda: webbrowser.open(self.GITHUB_URL)))

        menu.addAction(self._action(menu, t("tray.settings"), window.open_settings))
        menu.addSeparator()

        menu.addAction(self._action(menu, t("tray.quit"), window.quit_application))

        menu.aboutToShow.connect(self.sync_autostart_check)
        self.sync_autostart_check()
        return menu

    @staticmethod
    def _action(menu, text: str, handler) -> QAction:
        """누르면 handler를 부르는 항목. 부모를 메뉴로 두어 메뉴를 헐면 함께 사라진다."""
        action = QAction(text, menu)
        action.triggered.connect(handler)
        return action

    def update_status(self, queued: int, active: int, percent=None):
        """트레이 툴팁을 지금 상태로 바꾼다.

        커서를 올려야 보이는 자리라 평소에는 앱 이름만 두고, 받는 중일 때만 줄을 늘린다.
        진행률은 실제로 도는 것이 있을 때만 붙는다(percent가 None이면 뺀다). 늘 보이는
        아이콘 채움도 같은 값으로 바꾼다 - 둘이 다른 숫자를 말하면 어느 쪽을 믿을지 알 수 없다.
        """
        lines = [self._name]
        if queued or active:
            head = t("tray.status", queued=queued, active=active)
            lines.append(f"{head} · {percent}%" if percent is not None else head)
        tray_icon = self.window.tray_icon
        tray_icon.setToolTip("\n".join(lines))
        if percent != self._icon_percent:
            self._icon_percent = percent
            tray_icon.setIcon(app_icon_with_progress(percent))

    def sync_autostart_check(self):
        """레지스트리의 실제 상태로 체크를 맞춘다. toggled가 되돌아 또 쓰지 않게 잠시 끊는다."""
        if self.autostart_action is None:
            return
        self.autostart_action.blockSignals(True)
        self.autostart_action.setChecked(autostart.is_enabled())
        self.autostart_action.blockSignals(False)

    def on_queue_changed(self, queued: int, active: int):
        """대기·진행 개수가 바뀌면 화면 라벨과 트레이를 함께 맞춘다."""
        self._queue_counts = (queued, active)
        self.window.ui.queue_count_label.setText(t("download_tab.queue_count", queued=queued, active=active))
        self.refresh_status()

    def refresh_status(self):
        """트레이에 보여 줄 값을 다시 계산해 둔다. 실제 반영은 _sync가 한다.

        진행률은 실제로 도는 것이 있을 때만 넘긴다 - 대기만 걸려 있는데 고리를 띄우면
        받는 중처럼 보인다. 도는 것이 있으면 타이머에 맡기고, 없으면 그 자리에서 되돌린다
        (원래 아이콘으로 가는 일은 묶음당 한 번뿐이라 미루면 고리가 1초 더 남는다).
        """
        queued, active = self._queue_counts
        self._tray_state = (queued, active,
                            self.window.download_manager.overall_progress() if active else None)
        was_active = bool(self._tray_shown and self._tray_shown[1])
        if active:
            if not self._timer.isActive():
                self._timer.start()
                self._sync()
            return
        if was_active or self._tray_shown is None:
            self._timer.stop()
            self._sync()
            return
        if not self._timer.isActive():
            self._timer.start()

    def _sync(self):
        """계산해 둔 값을 트레이에 실제로 넣는다. 달라진 것이 없으면 손대지 않는다.

        쉬는 동안 대기 개수만 바뀐 것도 타이머로 묶는다 - 시리즈 예순 화를 넣으면 툴팁을
        예순 번 바꾸는 셸 호출이 창 스레드에서 줄지어 돌았다. 다 쉬고 나면 타이머를 멈춘다.
        """
        if not self._tray_state[1]:
            self._timer.stop()
        if self._tray_state == self._tray_shown:
            return
        self._tray_shown = self._tray_state
        self.update_status(*self._tray_state)

    def on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick: self.window.bring_to_front()

    def notify_all_finished(self):
        """묶음이 다 끝났음을 로그와 풍선 알림으로 알린다."""
        window = self.window
        window.append_log(t("log.all_finished"))
        window.tray_icon.showMessage(t("dialog.tray_message_title"),
                                     t("dialog.tray_message_body"),
                                     window.windowIcon(), 5000)

    def handle_minimized(self):
        """트레이로 바로 숨겨 Windows 최소화와 숨김이 연달아 창 상태를 바꾸지 않게 한다."""
        self._minimize_timer.stop()
        self.window.hide()
        if not self._hide_notice_shown:
            self._notice_timer.start(0)

    def schedule_minimized(self):
        """운영체제에서 온 최소화는 Qt의 상태 전환이 끝나야 안전하게 숨길 수 있다."""
        self._minimize_timer.start(0)

    def _finish_minimized(self):
        if self.window.isMinimized():
            self.handle_minimized()

    def _notify_hidden(self):
        """동기 셸 호출을 창 전환 밖으로 미루고 같은 안내를 실행 중 한 번만 보낸다."""
        window = self.window
        if not window.isHidden() or window.force_quit or self._hide_notice_shown:
            return
        self._hide_notice_shown = True
        window.tray_icon.showMessage(localized_app_name(), t("dialog.tray_minimized"),
                                     window.windowIcon(), 2000)

    def handle_close(self, event):
        """닫기 단추를 설정에 맞게 처리한다.

        force_quit은 우리가 스스로 끝내는 중이라는 뜻이라 묻지 않고 보낸다.
        """
        window = self.window
        if window.force_quit: event.accept(); return
        if window.config.get("close_action", "exit") == "tray":
            event.ignore()
            self.handle_minimized()
            return
        if confirm(window, t("dialog.quit_title"), t("dialog.quit_body"),
                   icon_name="power", color_key="danger",
                   theme=window.config.get("theme", "light")):
            self.quit_application(); event.accept()
        else:
            event.ignore()

    def quit_application(self):
        """진행 중인 일을 모두 멈추고 끝낸다.

        멈추는 일은 download_manager가 통째로 맡는다. 예전에는 여기서 다운로드 스레드만
        훑어서, 변환만 남은 항목이 걸리지 않아 창이 닫힌 뒤에도 ffmpeg가 계속 돌았다.
        """
        window = self.window
        window.append_log(t("log.app_quit"))
        self._timer.stop()
        window.region.stop()
        stopped = window.download_manager.stop_all()
        if stopped:
            window.append_log(t("log.queue_stopped", count=stopped))
        window.force_quit = True; window.tray_icon.hide(); QApplication.quit()

    def retranslate(self):
        """언어를 바꾼 뒤 트레이 메뉴를 새로 짜고, 개수 줄과 툴팁을 새 언어로 다시 쓴다.

        옛 메뉴는 헐어 낸다 - 트레이가 쥐고 있지 않다. 마지막으로 넣은 값과 같으면 _sync가
        건너뛰므로, 넣은 값을 잊게 하고 다시 넣는다.
        """
        tray_icon = self.window.tray_icon
        self._name = f"{localized_app_name()} {self._version}"
        old_menu = tray_icon.contextMenu()
        tray_icon.setContextMenu(self._build_menu())
        if old_menu is not None:
            old_menu.deleteLater()
        self.on_queue_changed(*self._queue_counts)
        self._tray_shown = None
        self._sync()
