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

    정상이면 0.1초 안에 끝난다(실측). 넉넉히 두는 것은 네트워크 드라이브에 받아 둔 경우다.
    """

    def __init__(self, url: str, input_path: str, ffmpeg_path: str,
                 target_codec: str, delete_original: bool,
                 hw_encoder_setting: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.input_path = Path(input_path)
        self.ffmpeg_path = ffmpeg_path
        self.target_codec = target_codec
        self.delete_original = delete_original
        self.hw_encoder_setting = hw_encoder_setting
        self.process = None
        self._stop_flag = False
        self._process_lock = threading.Lock()
        self.command_text = ""
        self.plan_notes: List[str] = []
        """어떤 인자로 무엇을 만들었는지. **성공하면 로그에 내보내지 않는다.**

        잘 끝난 변환에서 이 줄들을 읽는 사람은 없고 로그만 밀어낸다. 검사도 여기를 읽는다.
        """

    def stop(self):
        """변환을 중단한다.

        terminate()는 스레드를 임의 지점에서 죽여 ffmpeg가 고아로 남는다. 자식을 끝내
        run()이 스스로 빠져나오게 한다. _spawn과 자물쇠를 함께 쓰는 것은, 시작 직후의
        중단은 죽일 프로세스가 아직 없어 플래그만 선 채 변환이 끝까지 돌기 때문이다.
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

        stop()과 같은 자물쇠를 써서 어느 쪽이 먼저 들어와도 결과가 하나다.
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

        ffmpeg는 첫 프레임부터 목적지에 직접 써서, 끊기면 재생되지 않는 파일이 이름만
        멀쩡하게 남는다. 지우지 못했으면 조용히 넘기지 않는다 - 알아야 손으로 지운다.
        """
        if not output_path.exists():
            return
        try:
            output_path.unlink()
        except OSError as e:
            self.log.emit(f"[오류] 중단된 파일을 지우지 못했습니다 ('{output_path.name}'): {e}")

    def _run_ffprobe(self, args: List[str]) -> Optional[str]:
        """ffprobe를 한 번 돌리고 표준 출력을 돌려준다. 실패하면 None.

        실패를 로그에 남기지 않는다 - 부르는 쪽이 안전한 값으로 물러서므로 손댈 것이 없다.
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

        값이 'N/A'인 항목은 담지 않는다. 담으면 한 곳만 빠뜨려도 그 문자열이 숫자로 넘어간다.
        """
        fields: Dict[str, str] = {}
        for line in (text or "").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and value and value != "N/A":
                fields[key] = value
        return fields

    def _probe_video(self) -> Dict[str, Any]:
        """재인코딩에 필요한 영상 속성을 읽는다. 못 읽은 것은 None으로 남는다.

        fps는 avg_frame_rate를 먼저 본다. r_frame_rate는 가변 프레임률에서 실제보다 크게
        나와 level이 한 단계 높게 잡힌다.
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

        비트레이트가 안 나오면 패킷을 세어 직접 잰다 - mkv·webm이 그 경우이고, yt-dlp가
        유튜브의 AV1+Opus를 병합하면 나오는 것이 그 컨테이너다(mp4 120,080bps, mkv N/A).
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

        앞부분만 읽는다. 전체를 훑어도 값은 같은데 파일이 길수록 기다린다(20분짜리에서
        0.205초 대 0.068초, 값은 159,998bps로 동일).
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
        """영상을 다시 만들 때 붙일 인자 전부. 오디오도 여기서 함께 정한다.

        예전에는 부르는 쪽이 -c:a copy를 붙여, AV1+Opus를 AVC로 옮기면 영상만 h264가 되고
        소리는 Opus로 남았다. 둘을 갈라 두면 한쪽만 고치는 일이 또 생긴다.
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
        """변환으로 파일명이 바뀌면 별도 자막이 짝을 잃는다. 원본을 지우면 옮기고, 남기면 복사한다."""
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
        if not self.target_codec:
            self.log.emit("[오류] 변환할 코덱이 지정되지 않았습니다.")
            self.finished.emit(False, self.url, ""); return

        output_path = self.input_path.with_name(f"{self.input_path.stem}_{self.target_codec}.mp4")
        command = [self.ffmpeg_path, '-i', str(self.input_path), '-y']

        try:
            command.extend(self._reencode_args(output_path))
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

        실패는 인자가 원인인 경우가 많아 명령줄이 없으면 재현할 방법이 없다.
        """
        for note in self.plan_notes:
            self.log.emit(note)
        if self.command_text:
            self.log.emit(f"ffmpeg 명령: {self.command_text}")
