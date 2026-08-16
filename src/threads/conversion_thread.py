import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional, List, Dict

from PyQt6.QtCore import QThread, pyqtSignal

from src.utils import get_startupinfo

class ConversionThread(QThread):
    finished = pyqtSignal(bool, str, str)
    log = pyqtSignal(str)

    def __init__(self, url: str, input_path: str, ffmpeg_path: str,
                 target_format: Optional[str], target_codec: Optional[str],
                 delete_original: bool, hw_encoder_setting: str,
                 quality_cfg: Dict[str, int], parent=None):
        super().__init__(parent)
        self.url = url
        self.input_path = Path(input_path)
        self.ffmpeg_path = ffmpeg_path
        self.target_format = target_format
        self.target_codec = target_codec
        self.delete_original = delete_original
        self.hw_encoder_setting = hw_encoder_setting
        self.quality_cfg = quality_cfg
        self.process = None
        self._stop_flag = False
        self._process_lock = threading.Lock()

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

    def _get_video_encoder_args(self) -> List[str]:
        """선호 코덱과 GPU/CPU 설정에 맞는 FFmpeg 인코더 및 품질 인자를 반환합니다."""
        if not self.target_codec:
            return []

        codec_map = {
            'h264': ('h264_nvenc', 'h264_qsv', 'h264_amf', 'libx264'),
            'hevc': ('hevc_nvenc', 'hevc_qsv', 'hevc_amf', 'libx265'),
            'vp9': (None, 'vp9_qsv', None, 'libvpx-vp9'),
            'av1': ('av1_nvenc', 'av1_qsv', 'av1_amf', 'libsvtav1')
        }

        if self.target_codec not in codec_map:
            return ['-c:v', 'copy']

        encoders = codec_map[self.target_codec]
        args: List[str] = []
        encoder_name: Optional[str] = None
        quality_val_str = ""

        if self.hw_encoder_setting == "nvidia" and encoders[0]:
            encoder_name = encoders[0]
            q_val = self.quality_cfg.get("gpu_cq", 30)
            quality_val_str = f"CQ={q_val}"
            args = ['-c:v', encoder_name, '-cq', str(q_val), '-preset', 'p5']

        elif self.hw_encoder_setting == "intel" and encoders[1]:
            encoder_name = encoders[1]
            q_val = self.quality_cfg.get("gpu_cq", 30)
            quality_val_str = f"CQ={q_val}"
            args = ['-hwaccel', 'auto', '-c:v', encoder_name, '-cq', str(q_val), '-preset', 'medium']

        elif self.hw_encoder_setting == "amd" and encoders[2]:
            encoder_name = encoders[2]
            q_val = self.quality_cfg.get("gpu_cq", 30)
            quality_val_str = f"CQP={q_val}"
            args = ['-c:v', encoder_name, '-rc', 'cqp', '-qp_i', str(q_val), '-qp_p', str(q_val), '-qp_b', str(q_val)]

        else:
            encoder_name = encoders[3]
            if not encoder_name:
                return ['-c:v', 'copy']

            if encoder_name == 'libsvtav1':
                q_val = self.quality_cfg.get("cpu_av1_crf", 41)
                quality_val_str = f"CRF={q_val}"
                args = ['-c:v', encoder_name, '-crf', str(q_val), '-preset', '8']
            elif encoder_name == 'libvpx-vp9':
                q_val = self.quality_cfg.get("cpu_vp9_crf", 36)
                quality_val_str = f"CRF={q_val}"
                args = ['-c:v', encoder_name, '-crf', str(q_val), '-b:v', '0']
            elif encoder_name == 'libx265':
                q_val = self.quality_cfg.get("cpu_h265_crf", 31)
                quality_val_str = f"CRF={q_val}"
                args = ['-c:v', encoder_name, '-crf', str(q_val), '-preset', 'medium']
            else:
                q_val = self.quality_cfg.get("cpu_h264_crf", 26)
                quality_val_str = f"CRF={q_val}"
                args = ['-c:v', encoder_name, '-crf', str(q_val), '-preset', 'medium']

        self.log.emit(f"사용할 인코더: {encoder_name} (설정: {self.hw_encoder_setting}, 품질: {quality_val_str})")
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

        if self.target_codec:
            encoder_args = self._get_video_encoder_args()
            command.extend(encoder_args)
            command.extend(['-c:a', 'copy'])
        elif self.target_format == 'mp3':
            command.extend(['-vn', '-c:a', 'libmp3lame', '-q:a', '2'])
        elif self.target_format in ['avi', 'mov']:
            command.extend(['-c', 'copy'])

        command.append(str(output_path))

        try:
            self.log.emit(f"파일 변환 시작: '{self.input_path.name}' -> '{output_path.name}'")
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
                self.log.emit(f"파일 변환 성공: '{output_path.name}'")
                self._handle_sidecar_subtitles(self.input_path, output_path)
                if self.delete_original and self.input_path.exists():
                    try:
                        self.input_path.unlink()
                        self.log.emit(f"원본 파일 삭제: '{self.input_path.name}'")
                    except OSError as e:
                        self.log.emit(f"[오류] 원본 파일 삭제 실패: {e}")
                self.finished.emit(True, self.url, str(output_path))
            else:
                self.log.emit(f"[오류] 파일 변환 실패: {stderr_text}")
                self._discard_output(output_path)
                self.finished.emit(False, self.url, "")
        except Exception as e:
            self.log.emit(f"[오류] 파일 변환 중 예외 발생: {e}")
            self._discard_output(output_path)
            self.finished.emit(False, self.url, "")
