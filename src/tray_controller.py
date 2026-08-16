"""트레이 아이콘과 창의 드나듦을 맡는다.

한 덩이로 묶은 것은 이들이 **창이 보이지 않을 때의 앱**을 함께 책임지기
때문이다. 최소화하면 창을 숨기고, 트레이를 두 번 누르면 되살리고, 그동안
진행 상황은 툴팁과 아이콘 고리로만 나간다. 끝내는 일까지 여기 둔 이유도
같다 — 트레이 메뉴가 유일한 종료 경로가 되는 순간이 있어서다.

**갱신은 1초에 한 번으로 묶는다**(TRAY_SYNC_INTERVAL_MS). yt-dlp가 진행률을
초당 여러 줄 뱉는데 그때마다 손대면 아이콘을 여덟 크기로 다시 그리는 일과
셸 호출이 그만큼 따라붙는다. setToolTip도 글자만 바꾸는 것처럼 보이지만
트레이 영역을 다시 등록하는 셸 호출이라 함께 묶는다.

값을 **계산하는 곳(refresh_status)과 반영하는 곳(_sync)을 나눈 이유**가 있다.
개수는 queue_changed가, 진행률은 progress_updated가 물어 오는데 둘이 오는
시점이 달라서, 마지막 값을 들고 있다가 어느 쪽이 와도 같은 자리를 채운다.

Qt가 창에 직접 보내는 changeEvent·closeEvent는 창에 남을 수밖에 없어, 창이
받아서 handle_minimized / handle_close로 넘긴다.
"""

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
from PyQt6.QtCore import QTimer

from src.utils import localized_app_name
from src.message import confirm


class TrayController:
    """트레이 표시와 창 드나듦, 종료를 맡는 조작 묶음."""

    TRAY_SYNC_INTERVAL_MS = 1000
    """트레이를 다시 그리는 최소 간격.

    yt-dlp는 진행률을 초당 여러 줄씩 뱉는다. 그때마다 손대면 아이콘을 다섯 크기로
    새로 그리는 일과 셸 호출이 그 횟수만큼 따라붙는다. 툴팁도 같이 묶는 이유가
    이것이다 — 글자 하나 바꾸는 일로 보이지만 setToolTip도 결국 트레이 영역을
    다시 등록하는 셸 호출이다.
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
        self.window.ui.queue_count_label.setText(f"{queued} 대기 / {active} 진행")
        self.refresh_status()

    def refresh_status(self):
        """트레이에 보여 줄 값을 다시 계산해 둔다. 실제 반영은 _sync가 한다.

        개수는 queue_changed가, 진행률은 progress_updated가 물어 온다. 둘이 오는
        시점이 달라서 마지막 값을 들고 있다가 어느 쪽이 와도 같은 자리를 채운다.

        진행률은 실제로 도는 것이 있을 때만 넘긴다. 대기만 걸려 있는 동안 고리를
        띄우면 아직 아무것도 받고 있지 않은데 받는 중처럼 보인다.

        도는 것이 있으면 타이머에 맡기고, 없으면 그 자리에서 되돌린다. 원래
        아이콘으로 돌아가는 일은 묶음당 한 번뿐이라 미룰 이유가 없고, 미루면
        다 끝난 뒤에도 고리가 최대 1초 더 남는다.
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
        window.append_log("모든 다운로드가 완료되었습니다.")
        window.tray_icon.showMessage("다운로드 완료", "모든 작업이 끝났습니다!", window.windowIcon(), 5000)

    def handle_minimized(self):
        """최소화를 트레이로 내려가는 동작으로 바꾼다.

        창이 Qt의 최소화 상태로 남으면 대화상자가 그 창을 부모로 삼을 때 자리
        계산이 되지 않는다. 숨겨 두고 트레이에서 되살리는 편이 경로가 하나다.
        """
        window = self.window
        window.hide()
        window.tray_icon.showMessage(localized_app_name(), "프로그램이 트레이로 이동했습니다.",
                                     window.windowIcon(), 2000)

    def handle_close(self, event):
        """닫기 단추를 설정에 맞게 처리한다.

        force_quit은 우리가 스스로 끝내는 중이라는 뜻이라 묻지 않고 보낸다.
        설정이 '트레이로'면 창만 숨기고 앱은 계속 돈다.
        """
        window = self.window
        if window.force_quit: event.accept(); return
        if window.config.get("close_action", "exit") == "tray":
            event.ignore(); window.hide()
            window.tray_icon.showMessage(localized_app_name(), "프로그램이 트레이로 이동했습니다.",
                                         window.windowIcon(), 2000)
            return
        if confirm(window, "종료 확인", "종료하시겠습니까?",
                   icon_name="cancel", color_key="danger",
                   theme=window.config.get("theme", "light")):
            self.quit_application(); event.accept()
        else:
            event.ignore()

    def quit_application(self):
        """진행 중인 일을 모두 멈추고 끝낸다.

        멈추는 일은 download_manager가 통째로 맡는다. 예전에는 여기서 다운로드
        스레드만 훑어서, 이미 다 받고 변환만 남은 항목이 걸리지 않았다. 창은
        닫혔는데 ffmpeg는 계속 돌고 절반만 쓰인 파일이 남았다.
        """
        window = self.window
        window.append_log("프로그램을 종료합니다...")
        self._timer.stop()
        stopped = window.download_manager.stop_all()
        if stopped:
            window.append_log(f"[대기열] 진행 중이던 작업 {stopped}개를 중지했습니다.")
        window.force_quit = True; window.tray_icon.hide(); QApplication.instance().quit()
