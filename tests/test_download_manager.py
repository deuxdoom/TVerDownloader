"""대기열 상태와 그 전이.

**여기가 이 폴더에서 가장 값어치 있는 검사다.** 예전에 창 쪽 아홉 군데가
_active_threads·_active_conversions·_task_queue를 각자 다르게 조합해서, 다운로드가
끝나고 변환만 남은 항목이 '아무 일도 하지 않는 항목'으로 새어 나갔다. 종료할 때
안 멈춰 ffmpeg가 남고, 목록에서 지우면 카드만 사라진 채 변환이 계속 돌았다.

그래서 is_busy / is_queued / is_pending 셋이 **각 단계마다** 무엇을 답하는지를
표로 만들어 고정해 둔다. 자료구조를 직접 보지 않는 한 이 셋만 맞으면 된다.

진짜 yt-dlp나 ffmpeg는 절대 뜨지 않는다. fake_threads 픽스처가
src.download_manager 네임스페이스의 이름을 갈아 끼운다(conftest 참고).
"""

import pytest

from src.download_manager import DownloadManager

URL = "https://tver.jp/episodes/ep1"
URL2 = "https://tver.jp/episodes/ep2"


@pytest.fixture
def idle_manager(fake_threads, config_factory):
    """경로를 주지 않은 관리자. 넣은 작업이 대기열에 그대로 머문다.

    check_queue_and_start가 ytdlp_path 없이는 돌아 나오는 성질을 이용한다.
    시작 시점을 검사가 정할 수 있어야 '대기 중' 상태를 관찰할 수 있다.
    """
    return DownloadManager(config_factory(), None)


@pytest.fixture
def ready_manager(fake_threads, config_factory, tmp_path):
    """바로 시작할 수 있는 관리자."""
    manager = DownloadManager(config_factory(download_folder=str(tmp_path)), None)
    manager.set_paths("yt-dlp.exe", "ffmpeg.exe")
    return manager


class TestAddTask:
    def test_추가하면_대기열에_들어간다(self, idle_manager):
        assert idle_manager.add_task(URL) is True
        assert idle_manager.is_queued(URL) is True
        assert idle_manager.is_busy(URL) is False
        assert idle_manager.is_pending(URL) is True

    def test_같은_주소를_두_번_넣지_않는다(self, idle_manager):
        idle_manager.add_task(URL)
        assert idle_manager.add_task(URL) is False

    def test_빈_주소는_받지_않는다(self, idle_manager):
        assert idle_manager.add_task("") is False
        assert idle_manager.add_task("   ") is False

    def test_앞뒤_공백을_다듬어_담는다(self, idle_manager):
        idle_manager.add_task(f"  {URL}  ")
        assert idle_manager.is_queued(URL) is True

    def test_카드를_만들라고_알린다(self, idle_manager, recorder):
        added = recorder()
        idle_manager.item_added.connect(added)
        idle_manager.add_task(URL)
        assert added.calls == [URL]

    def test_대기_진행_개수를_알린다(self, idle_manager, recorder):
        counts = recorder()
        idle_manager.queue_changed.connect(counts)
        idle_manager.add_task(URL)
        assert counts.last == (1, 0)


class TestRemoveFromQueue:
    def test_대기_중인_것을_뺀다(self, idle_manager):
        idle_manager.add_task(URL)
        assert idle_manager.remove_task_from_queue(URL) is True
        assert idle_manager.is_queued(URL) is False
        assert idle_manager.is_pending(URL) is False

    def test_없는_것을_빼면_False(self, idle_manager):
        assert idle_manager.remove_task_from_queue("없는주소") is False

    def test_뺀_뒤에는_다시_넣을_수_있다(self, idle_manager):
        """_active_urls에서도 지워져야 한다. 안 지우면 영영 다시 못 넣는다."""
        idle_manager.add_task(URL)
        idle_manager.remove_task_from_queue(URL)
        assert idle_manager.add_task(URL) is True


class TestStartDownload:
    def test_경로가_준비되면_대기에서_진행으로_넘어간다(self, ready_manager):
        ready_manager.add_task(URL)
        assert ready_manager.is_queued(URL) is False
        assert ready_manager.is_busy(URL) is True
        assert ready_manager.is_pending(URL) is True

    def test_스레드를_실제로_시작시킨다(self, ready_manager, fake_threads):
        FakeDownload, _ = fake_threads
        ready_manager.add_task(URL)
        assert len(FakeDownload.created) == 1
        assert FakeDownload.created[0].started is True

    def test_동시_실행_개수를_지킨다(self, fake_threads, config_factory, tmp_path):
        FakeDownload, _ = fake_threads
        manager = DownloadManager(
            config_factory(download_folder=str(tmp_path), max_concurrent_downloads=2), None)
        manager.set_paths("yt-dlp.exe", "ffmpeg.exe")
        for i in range(5):
            manager.add_task(f"https://tver.jp/episodes/ep{i}")
        assert len(FakeDownload.created) == 2
        assert sum(manager.is_busy(f"https://tver.jp/episodes/ep{i}") for i in range(5)) == 2
        assert sum(manager.is_queued(f"https://tver.jp/episodes/ep{i}") for i in range(5)) == 3

    def test_다운로드_폴더가_없으면_시작하지_않는다(self, fake_threads, config_factory):
        FakeDownload, _ = fake_threads
        manager = DownloadManager(config_factory(download_folder=""), None)
        manager.set_paths("yt-dlp.exe", "ffmpeg.exe")
        manager.add_task(URL)
        assert FakeDownload.created == []
        assert manager.is_pending(URL) is False


class TestConversionState:
    """다운로드가 끝나고 변환만 남은 구간.

    새어 나가던 자리가 바로 여기다. _active_threads에는 없지만 ffmpeg는 돌고 있다.
    """

    @pytest.fixture
    def converting(self, fake_threads, config_factory, tmp_path):
        FakeDownload, FakeConversion = fake_threads
        video = tmp_path / "ep1.mp4"
        video.write_bytes(b"x")
        manager = DownloadManager(
            config_factory(download_folder=str(tmp_path), conversion_format="mp4"), None)
        manager.set_paths("yt-dlp.exe", "ffmpeg.exe")
        manager.add_task(URL)
        FakeDownload.created[0].finish(True, str(video))
        return manager, FakeConversion, video

    def test_변환_중인_항목은_진행_중으로_본다(self, converting):
        manager, FakeConversion, _ = converting
        assert len(FakeConversion.created) == 1
        assert manager.is_busy(URL) is True
        assert manager.is_queued(URL) is False
        assert manager.is_pending(URL) is True

    def test_변환이_끝나면_아무것도_남지_않는다(self, converting):
        manager, FakeConversion, video = converting
        FakeConversion.created[0].finish(True, str(video))
        assert manager.is_busy(URL) is False
        assert manager.is_pending(URL) is False

    def test_변환이_끝나면_완료를_알린다(self, converting, recorder):
        manager, FakeConversion, video = converting
        done = recorder()
        manager.task_finished.connect(done)
        FakeConversion.created[0].finish(True, str(video))
        assert done.last == (URL, True, str(video), {})

    def test_변환_실패도_대기열에서는_빠진다(self, converting):
        manager, FakeConversion, _ = converting
        FakeConversion.created[0].finish(False, "")
        assert manager.is_pending(URL) is False


class TestFinishWithoutConversion:
    def test_원본_유지면_변환하지_않고_끝낸다(self, ready_manager, fake_threads, tmp_path):
        FakeDownload, FakeConversion = fake_threads
        video = tmp_path / "ep1.mp4"
        video.write_bytes(b"x")
        ready_manager.add_task(URL)
        FakeDownload.created[0].finish(True, str(video))
        assert FakeConversion.created == []
        assert ready_manager.is_pending(URL) is False

    def test_실패하면_바로_정리된다(self, ready_manager, fake_threads):
        FakeDownload, _ = fake_threads
        ready_manager.add_task(URL)
        FakeDownload.created[0].finish(False, "")
        assert ready_manager.is_pending(URL) is False

    def test_파일이_없으면_성공이라도_실패로_친다(self, ready_manager, fake_threads, tmp_path):
        """yt-dlp가 0으로 끝나도 파일이 없으면 성공이 아니다."""
        FakeDownload, _ = fake_threads
        ready_manager.add_task(URL)
        FakeDownload.created[0].finish(True, str(tmp_path / "없는파일.mp4"))
        assert ready_manager.is_pending(URL) is False

    def test_다_끝나면_묶음_완료를_알린다(self, ready_manager, fake_threads, tmp_path, recorder):
        FakeDownload, _ = fake_threads
        video = tmp_path / "ep1.mp4"
        video.write_bytes(b"x")
        all_done = recorder()
        ready_manager.all_tasks_completed.connect(all_done)
        ready_manager.add_task(URL)
        FakeDownload.created[0].finish(True, str(video))
        assert len(all_done) == 1

    def test_하나가_끝나면_대기하던_것이_시작된다(self, fake_threads, config_factory, tmp_path):
        FakeDownload, _ = fake_threads
        video = tmp_path / "ep1.mp4"
        video.write_bytes(b"x")
        manager = DownloadManager(
            config_factory(download_folder=str(tmp_path), max_concurrent_downloads=1), None)
        manager.set_paths("yt-dlp.exe", "ffmpeg.exe")
        manager.add_task(URL)
        manager.add_task(URL2)
        assert manager.is_queued(URL2) is True
        FakeDownload.created[0].finish(True, str(video))
        assert manager.is_busy(URL2) is True


class TestStopAll:
    def test_대기와_진행을_모두_멈춘다(self, fake_threads, config_factory, tmp_path):
        FakeDownload, _ = fake_threads
        manager = DownloadManager(
            config_factory(download_folder=str(tmp_path), max_concurrent_downloads=1), None)
        manager.set_paths("yt-dlp.exe", "ffmpeg.exe")
        manager.add_task(URL)
        manager.add_task(URL2)
        stopped = manager.stop_all()
        assert stopped == 1
        assert FakeDownload.created[0].stopped is True
        assert manager.is_queued(URL2) is False

    def test_변환_중인_것도_함께_멈춘다(self, fake_threads, config_factory, tmp_path):
        """예전에는 다운로드 스레드만 훑어서 변환이 살아남았다."""
        FakeDownload, FakeConversion = fake_threads
        video = tmp_path / "ep1.mp4"
        video.write_bytes(b"x")
        manager = DownloadManager(
            config_factory(download_folder=str(tmp_path), conversion_format="mp4"), None)
        manager.set_paths("yt-dlp.exe", "ffmpeg.exe")
        manager.add_task(URL)
        FakeDownload.created[0].finish(True, str(video))
        assert manager.stop_all() == 1
        assert FakeConversion.created[0].stopped is True

    def test_멈춘_뒤에는_새로_시작하지_않는다(self, ready_manager, fake_threads):
        """_shutting_down이 서면 check_queue_and_start가 돌아 나가야 한다.

        멈춘 작업의 완료 신호가 도착하는 순간 다음 것을 새로 띄우면, 종료
        직전에 뜬 프로세스는 거둘 사람이 없다.
        """
        FakeDownload, _ = fake_threads
        ready_manager.add_task(URL)
        ready_manager.stop_all()
        before = len(FakeDownload.created)
        ready_manager.add_task(URL2)
        assert len(FakeDownload.created) == before

    def test_뒷정리를_기다린다(self, ready_manager, fake_threads):
        """wait를 부르지 않으면 쓰다 만 파일을 지우는 코드에 차례가 오지 않는다."""
        FakeDownload, _ = fake_threads
        ready_manager.add_task(URL)
        ready_manager.stop_all()
        assert FakeDownload.created[0].waited is True


class TestOverallProgress:
    """트레이 고리가 쓰는 묶음 전체 진행률."""

    def test_아무것도_없으면_None(self, idle_manager):
        assert idle_manager.overall_progress() is None

    def test_대기만_있으면_0(self, idle_manager):
        idle_manager.add_task(URL)
        assert idle_manager.overall_progress() == 0

    def test_대기_중인_것도_분모에_넣는다(self, fake_threads, config_factory, tmp_path):
        """진행 중인 것만 세면 항목이 끝날 때마다 진행률이 뒤로 간다."""
        FakeDownload, _ = fake_threads
        manager = DownloadManager(
            config_factory(download_folder=str(tmp_path), max_concurrent_downloads=1), None)
        manager.set_paths("yt-dlp.exe", "ffmpeg.exe")
        manager.add_task(URL)
        manager.add_task(URL2)
        FakeDownload.created[0].emit_progress({"percent": 50})
        assert manager.overall_progress() == 25

    def test_100을_넘지_않는다(self, ready_manager, fake_threads):
        FakeDownload, _ = fake_threads
        ready_manager.add_task(URL)
        FakeDownload.created[0].emit_progress({"percent": 100})
        assert ready_manager.overall_progress() == 100

    def test_멈추면_묵은_진행률이_남지_않는다(self, ready_manager, fake_threads):
        """stop_all은 _item_percent를 비운다. 50%에서 멈춘 값이 그대로 남으면
        다음 묶음이 절반부터 시작한 것처럼 보인다.

        _active_urls까지 비우지는 않는다. 그건 스레드가 finished를 보내고
        _on_download_finished가 정리하는 몫이라, 여기서는 0으로 떨어지는
        것까지가 보장이다.
        """
        FakeDownload, _ = fake_threads
        ready_manager.add_task(URL)
        FakeDownload.created[0].emit_progress({"percent": 50})
        assert ready_manager.overall_progress() == 50
        ready_manager.stop_all()
        assert ready_manager.overall_progress() == 0


class TestResetForRedownload:
    def test_다시_받을_수_있게_되돌린다(self, ready_manager, fake_threads, tmp_path):
        FakeDownload, _ = fake_threads
        video = tmp_path / "ep1.mp4"
        video.write_bytes(b"x")
        ready_manager.add_task(URL)
        FakeDownload.created[0].finish(True, str(video))
        ready_manager.reset_for_redownload(URL)
        assert ready_manager.add_task(URL) is True

    def test_빈_주소는_무시한다(self, ready_manager):
        ready_manager.reset_for_redownload("")
