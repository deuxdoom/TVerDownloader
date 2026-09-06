"""트레이 아이콘과 창의 드나듦, 종료를 맡는다 - 창이 보이지 않을 때의 앱을 책임지는 덩이다.

**갱신은 1초에 한 번으로 묶는다**(TRAY_SYNC_INTERVAL_MS). 진행률이 초당 여러 줄 오는데
그때마다 손대면 아이콘 여덟 장을 다시 그리는 일과 셸 호출이 따라붙는다.

값을 계산하는 곳(refresh_status)과 반영하는 곳(_sync)을 나눈 것은, 개수는 queue_changed가
진행률은 progress_updated가 물어 오는데 둘이 오는 시점이 달라서다.
"""

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
from PyQt6.QtCore import QTimer
from PyQt6.QtNetwork import QLocalServer

from src import app_restart
from src.utils import localized_app_name
from src.i18n import t
from src.message import confirm


class TrayController:
    """트레이 표시와 창 드나듦, 종료를 맡는 조작 묶음."""

    TRAY_SYNC_INTERVAL_MS = 1000
    """트레이를 다시 그리는 최소 간격.

    진행률이 초당 여러 줄 온다. 툴팁도 같이 묶는 것은 setToolTip이 글자만 바꾸는 것처럼
    보여도 트레이 영역을 다시 등록하는 셸 호출이기 때문이다.
    """

    def __init__(self, window):
        self.window = window
        self._queue_counts = (0, 0)
        self._tray_state = (0, 0, None)
        self._tray_shown = None
        self._timer = QTimer(window)
        self._timer.setInterval(self.TRAY_SYNC_INTERVAL_MS)
        self._timer.timeout.connect(self._sync)

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
        if active:
            if not self._timer.isActive():
                self._timer.start()
                self._sync()
            return
        self._timer.stop()
        self._sync()

    def _sync(self):
        """계산해 둔 값을 트레이에 실제로 넣는다. 달라진 것이 없으면 손대지 않는다."""
        if self._tray_state == self._tray_shown:
            return
        self._tray_shown = self._tray_state
        self.window.ui.update_tray_status(*self._tray_state)

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
        """최소화를 트레이로 내려가는 동작으로 바꾼다.

        Qt의 최소화 상태로 남으면 대화상자가 그 창을 부모로 삼을 때 자리 계산이 되지 않는다.
        """
        window = self.window
        window.hide()
        window.tray_icon.showMessage(localized_app_name(), t("dialog.tray_minimized"),
                                     window.windowIcon(), 2000)

    def handle_close(self, event):
        """닫기 단추를 설정에 맞게 처리한다.

        force_quit은 우리가 스스로 끝내는 중이라는 뜻이라 묻지 않고 보낸다.
        """
        window = self.window
        if window.force_quit: event.accept(); return
        if window.config.get("close_action", "exit") == "tray":
            event.ignore(); window.hide()
            window.tray_icon.showMessage(localized_app_name(), t("dialog.tray_minimized"),
                                         window.windowIcon(), 2000)
            return
        if confirm(window, t("dialog.quit_title"), t("dialog.quit_body"),
                   icon_name="cancel", color_key="danger",
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
        window.stop_region_check()
        stopped = window.download_manager.stop_all()
        if stopped:
            window.append_log(t("log.queue_stopped", count=stopped))
        window.force_quit = True; window.tray_icon.hide(); QApplication.instance().quit()

    def restart_for_language_change(self) -> bool:
        """언어를 바꾼 뒤 앱을 다시 띄운다. 성공 여부를 돌려준다.

        **되돌릴 수 있는 일(소켓 비우기)을 먼저 하고, 되돌릴 수 없는 정리는 새 프로세스가
        확실히 뜬 뒤에만 한다.** 새 프로세스가 뜨는 시점에 소켓 자리가 이미 비어 있으므로
        PID가 죽기를 기다릴 필요가 없고, spawn이 실패해도 소켓을 되살려 그대로 계속 쓴다 -
        '새것도 못 띄우고 기존 것도 잃는' 상황이 설계적으로 나오지 않는다.
        """
        server = getattr(self.window, "_local_server", None)
        if server is not None:
            server.close()
            QLocalServer.removeServer(app_restart.SOCKET_NAME)
        if not app_restart.spawn_new_instance():
            if server is not None:
                server.listen(app_restart.SOCKET_NAME)
            return False
        self.quit_application()
        return True
