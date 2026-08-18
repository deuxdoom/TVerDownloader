import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any

from PyQt6.QtCore import QThread, pyqtSignal

from src import encoding
from src.utils import get_startupinfo, resolve_ffprobe_path

class ConversionThread(QThread):
    finished = pyqtSignal(bool, str, str)
    log = pyqtSignal(str)

    PROBE_TIMEOUT = 20
    """ffprobe 한 번을 기다릴 시간(초).

    읽기만 하는 호출이라 정상이면 0.1초 안에 끝난다(실측). 넉넉히 두는 것은
    네트워크 드라이브에 받아 둔 경우를 위해서고, 그래도 안 오면 못 읽은 것으로
    보고 넘어간다 - 속성을 하나 못 읽었다고 변환 자체를 접을 이유는 없다.
    """

    def __init__(self, url: str, input_path: str, ffmpeg_path: str,
                 target_format: Optional[str], target_codec: Optional[str],
                 delete_original: bool, hw_encoder_setting: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.input_path = Path(input_path)
        self.ffmpeg_path = ffmpeg_path
        self.target_format = target_format
        self.target_codec = target_codec
        self.delete_original = delete_original
        self.hw_encoder_setting = hw_encoder_setting
        self.process = None
        self._stop_flag = False
        self._process_lock = threading.Lock()
        self.command_text = ""
        self.plan_notes: List[str] = []
        """어떤 인자로 무엇을 만들었는지. **성공하면 로그에 내보내지 않는다.**

        잘 끝난 변환에서 이 줄들을 읽는 사람은 없고, 한 편 받을 때마다 로그를
        서너 줄씩 밀어낸다. 실패했을 때는 반대로 이것이 없으면 짚을 것이 없어서,
        그때만 명령줄과 함께 내보낸다. 검사도 로그를 훑지 않고 여기를 읽는다.
        """

    def stop(self):
        """변환을 중단한다.

        QThread.terminate()는 실행 중인 스레드를 임의 지점에서 죽여 프로세스를
        통째로 날릴 수 있고, ffmpeg는 고아로 남는다. 자식 프로세스를 끝내서
        run()이 스스로 빠져나오게 한다.

        플래그를 세우는 일과 프로세스를 읽는 일을 자물쇠로 묶는다. 시작 직후에
        들어온 중단은 ffmpeg가 아직 뜨지 않아 죽일 대상이 없는데, 그 사이에
        _spawn이 프로세스를 띄우면 플래그만 선 채로 변환이 끝까지 돌아간다.
        """
        with self._process_lock:
            self._stop_flag = True
            proc = self.process
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.kill()
        except Exception:
            pass

    def _spawn(self, command: List[str]) -> Optional[subprocess.Popen]:
        """중단 요청과 겹치지 않게 ffmpeg를 띄운다. 이미 멈추라고 했으면 뜨지 않는다.

        stop()과 같은 자물쇠를 쓰므로 둘 중 어느 쪽이 먼저 들어와도 결과가 하나다.
        먼저면 여기서 뜨지 않고, 나중이면 이미 self.process가 채워져 있어 죽는다.
        """
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        with self._process_lock:
            if self._stop_flag:
                return None
            self.process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                startupinfo=get_startupinfo(), creationflags=flags)
            return self.process

    def _discard_output(self, output_path: Path) -> None:
        """쓰다 만 출력 파일을 지운다.

        ffmpeg는 첫 프레임부터 목적지에 직접 쓴다. 중간에 끊기면 재생되지 않는
        파일이 이름만 멀쩡하게 남아, 나중에 폴더를 열었을 때 제대로 받아 둔
        영상과 구별되지 않는다.

        지우지 못했으면 조용히 넘기지 않는다. 파일이 남았다는 것을 알아야
        손으로 지울 수 있다.
        """
        if not output_path.exists():
            return
        try:
            output_path.unlink()
        except OSError as e:
            self.log.emit(f"[오류] 중단된 파일을 지우지 못했습니다 ('{output_path.name}'): {e}")

    def _run_ffprobe(self, args: List[str]) -> Optional[str]:
        """ffprobe를 한 번 돌리고 표준 출력을 돌려준다. 실패하면 None.

        실패를 로그에 남기지 않는다. 부르는 쪽이 못 읽은 값마다 안전한 쪽으로
        물러서게 되어 있어서, 사용자가 손댈 것이 없는 줄만 쌓인다.
        """
        ffprobe_path = resolve_ffprobe_path(self.ffmpeg_path)
        if not ffprobe_path:
            return None
        command = [ffprobe_path, '-v', 'error'] + args + [str(self.input_path)]
        try:
            proc = subprocess.run(command, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  startupinfo=get_startupinfo(),
                                  timeout=self.PROBE_TIMEOUT)
        except (OSError, subprocess.SubprocessError):
            return None
        return proc.stdout if proc.returncode == 0 else None

    @staticmethod
    def _parse_fields(text: Optional[str]) -> Dict[str, str]:
        """ffprobe의 'key=value' 출력을 사전으로 바꾼다.

        값이 'N/A'인 항목은 아예 담지 않는다. 담아 두면 부르는 쪽마다 그 문자열을
        따로 걸러야 하는데, 한 곳에서 빠뜨리면 'N/A'가 숫자로 넘어간다.
        """
        fields: Dict[str, str] = {}
        for line in (text or "").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and value and value != "N/A":
                fields[key] = value
        return fields

    def _probe_video(self) -> Dict[str, Any]:
        """재인코딩에 필요한 영상 속성을 읽는다. 못 읽은 것은 None으로 남는다.

        fps는 avg_frame_rate를 먼저 본다. r_frame_rate는 컨테이너가 적어 둔
        기준 시간에서 나온 값이라 가변 프레임률 영상에서 실제보다 크게 나오고,
        그러면 level이 한 단계 높게 잡힌다.
        """
        text = self._run_ffprobe([
            '-select_streams', 'v:0', '-show_entries',
            'stream=width,height,avg_frame_rate,r_frame_rate,'
            'color_primaries,color_transfer,color_space',
            '-of', 'default=noprint_wrappers=1'])
        fields = self._parse_fields(text)
        fps = (encoding.parse_fps(fields.get("avg_frame_rate"))
               or encoding.parse_fps(fields.get("r_frame_rate")))
        return {
            "width": self._as_int(fields.get("width")),
            "height": self._as_int(fields.get("height")),
            "fps": fps,
            "primaries": fields.get("color_primaries"),
            "transfer": fields.get("color_transfer"),
            "space": fields.get("color_space"),
        }

    def _probe_audio(self) -> Dict[str, Any]:
        """오디오 코덱·비트레이트·채널 수를 읽는다.

        비트레이트가 안 나오면 패킷을 세어 직접 잰다. **mkv와 webm이 그 경우이고,
        yt-dlp가 유튜브의 AV1+Opus를 병합하면 나오는 것이 바로 그 컨테이너다**
        (실측: 같은 내용을 mp4에 담으면 120,080bps, mkv에 담으면 N/A).
        여기서 물러서면 이 기능이 정작 필요한 파일에서만 어림값을 쓰게 된다.
        """
        text = self._run_ffprobe([
            '-select_streams', 'a:0', '-show_entries',
            'stream=codec_name,bit_rate,channels',
            '-of', 'default=noprint_wrappers=1'])
        fields = self._parse_fields(text)
        codec_name = fields.get("codec_name")
        raw_bps = self._as_int(fields.get("bit_rate"))
        kbps = raw_bps / 1000.0 if raw_bps else None
        if codec_name and kbps is None:
            kbps = self._measure_audio_bitrate()
        return {"codec_name": codec_name, "kbps": kbps,
                "channels": self._as_int(fields.get("channels"))}

    def _measure_audio_bitrate(self) -> Optional[float]:
        """컨테이너가 비트레이트를 안 적어 두었을 때 패킷을 세어 직접 잰다.

        앞부분만 읽는다. 전체를 훑어도 값은 거의 같은데 파일이 길수록 그만큼
        기다리게 된다(실측: 20분짜리에서 전체 0.205초/패킷 60,001개 대 앞 2분
        0.068초/6,000개, 값은 159,998bps로 같다).
        """
        text = self._run_ffprobe([
            '-select_streams', 'a:0', '-show_entries', 'packet=pts_time,size',
            '-read_intervals', f'%+{encoding.AUDIO_PROBE_WINDOW_SECONDS}',
            '-of', 'csv=p=0'])
        if not text:
            return None
        rows = [line.strip().rstrip(',').split(',')
                for line in text.splitlines() if line.strip()]
        return encoding.bitrate_from_packets(rows)

    @staticmethod
    def _as_int(text: Optional[str]) -> Optional[int]:
        try:
            return int(text)
        except (TypeError, ValueError):
            return None

    def _reencode_args(self, output_path: Path) -> List[str]:
        """영상을 다시 만들 때 붙일 인자 전부.

        **오디오를 여기서 함께 정하는 것이 이 함수의 요점이다.** 예전에는
        영상 인자만 고르고 오디오는 부르는 쪽에서 -c:a copy 를 붙였는데,
        그래서 AV1+Opus 원본을 AVC로 옮기면 영상만 h264가 되고 소리는 Opus로
        남았다. 둘을 갈라 두면 한쪽만 고치는 일이 또 생긴다.
        """
        video = self._probe_video()
        audio = self._probe_audio()
        video_opts, video_summary = encoding.video_args(
            self.target_codec, self.hw_encoder_setting, video, output_path.suffix)
        audio_opts, audio_summary = encoding.audio_args(
            audio["codec_name"], audio["kbps"], audio["channels"])
        self.plan_notes = [f"영상 인코더: {video_summary}", f"오디오: {audio_summary}"]
        args = ['-vf', encoding.color_filter(
            video["primaries"], video["transfer"], video["space"])]
        args.extend(video_opts)
        args.extend(audio_opts)
        return args

    def _handle_sidecar_subtitles(self, old_path: Path, new_path: Path) -> None:
        """
        변환으로 파일명이 바뀌면 별도 자막 파일(.srt/.vtt)이 영상과 짝이 맞지 않게 된다.
        원본을 삭제하는 경우에는 자막도 새 이름으로 옮기고, 원본을 남기는 경우에는 복사한다.
        """
        if old_path.stem == new_path.stem:
            return

        prefix = old_path.stem + "."
        try:
            candidates = [p for p in old_path.parent.iterdir()
                          if p.is_file()
                          and p.name.startswith(prefix)
                          and p.suffix.lower() in (".srt", ".vtt")]
        except OSError as e:
            self.log.emit(f"[오류] 자막 파일 확인 실패: {e}")
            return

        for sub in candidates:
            target = sub.with_name(new_path.stem + sub.name[len(old_path.stem):])
            if target.exists():
                continue
            try:
                if self.delete_original:
                    sub.rename(target)
                    self.log.emit(f"자막 파일 이동: '{sub.name}' -> '{target.name}'")
                else:
                    shutil.copy2(sub, target)
                    self.log.emit(f"자막 파일 복사: '{sub.name}' -> '{target.name}'")
            except OSError as e:
                self.log.emit(f"[오류] 자막 파일 처리 실패 ({sub.name}): {e}")

    def run(self):
        if self.target_codec:
            output_path = self.input_path.with_name(f"{self.input_path.stem}_{self.target_codec}.mp4")
        elif self.target_format:
            output_path = self.input_path.with_suffix(f".{self.target_format}")
        else:
            self.log.emit("[오류] 변환 목표(포맷 또는 코덱)가 지정되지 않았습니다.")
            self.finished.emit(False, self.url, ""); return

        command = [self.ffmpeg_path, '-i', str(self.input_path), '-y']

        try:
            if self.target_codec:
                command.extend(self._reencode_args(output_path))
            elif self.target_format == 'mp3':
                command.extend(['-vn', '-c:a', 'libmp3lame', '-q:a', '2'])
            elif self.target_format in ['avi', 'mov']:
                command.extend(['-c', 'copy'])

            command.append(str(output_path))
            self.command_text = subprocess.list2cmdline(command)
            proc = self._spawn(command)
            if proc is None:
                self.log.emit("[알림] 사용자 요청으로 변환을 중단했습니다.")
                self.finished.emit(False, self.url, ""); return

            _, stderr_text = proc.communicate()
            returncode = proc.returncode

            if self._stop_flag:
                self.log.emit("[알림] 사용자 요청으로 변환을 중단했습니다.")
                self._discard_output(output_path)
                self.finished.emit(False, self.url, ""); return

            if returncode == 0:
                self.log.emit("파일 변환 성공")
                self._handle_sidecar_subtitles(self.input_path, output_path)
                if self.delete_original and self.input_path.exists():
                    try:
                        self.input_path.unlink()
                    except OSError as e:
                        self.log.emit(f"[오류] 원본 파일 삭제 실패: {e}")
                self.finished.emit(True, self.url, str(output_path))
            else:
                self.log.emit(f"[오류] 파일 변환 실패: {stderr_text}")
                self._log_plan()
                self._discard_output(output_path)
                self.finished.emit(False, self.url, "")
        except Exception as e:
            self.log.emit(f"[오류] 파일 변환 중 예외 발생: {e}")
            self._log_plan()
            self._discard_output(output_path)
            self.finished.emit(False, self.url, "")

    def _log_plan(self):
        """무엇을 어떤 인자로 만들려 했는지 남긴다. 실패했을 때만 부른다.

        실패한 변환은 인자가 원인인 경우가 많아서, 명령줄이 없으면 재현할 방법이
        없다. 반대로 성공했을 때는 아무도 읽지 않는 줄이라 내보내지 않는다.
        """
        for note in self.plan_notes:
            self.log.emit(note)
        if self.command_text:
            self.log.emit(f"ffmpeg 명령: {self.command_text}")
