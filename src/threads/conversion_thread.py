# src/threads/conversion_thread.py
# 수정:
# - _get_video_encoder_args: 로그 메시지에 실제 품질 값(CRF/CQ)을 표시하도록 변경

import os
import subprocess
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
        quality_val_str = "" # ✅ 로그 출력용 품질 값 문자열
        
        # 2. 설정에 따라 인코더 및 품질 옵션 선택
        if self.hw_encoder_setting == "nvidia" and encoders[0]:
            encoder_name = encoders[0]
            q_val = self.quality_cfg.get("gpu_cq", 30)
            quality_val_str = f"CQ={q_val}"
            args = ['-c:v', encoder_name, '-cq', str(q_val), '-preset', 'p5'] # p5: medium

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
            # 3. CPU 또는 Fallback
            encoder_name = encoders[3]
            if not encoder_name:
                return ['-c:v', 'copy']
            
            if encoder_name == 'libsvtav1': # AV1 (CPU)
                q_val = self.quality_cfg.get("cpu_av1_crf", 41)
                quality_val_str = f"CRF={q_val}"
                args = ['-c:v', encoder_name, '-crf', str(q_val), '-preset', '8']
            elif encoder_name == 'libvpx-vp9': # VP9 (CPU)
                q_val = self.quality_cfg.get("cpu_vp9_crf", 36)
                quality_val_str = f"CRF={q_val}"
                args = ['-c:v', encoder_name, '-crf', str(q_val), '-b:v', '0']
            elif encoder_name == 'libx265': # H.265 (CPU)
                q_val = self.quality_cfg.get("cpu_h265_crf", 31)
                quality_val_str = f"CRF={q_val}"
                args = ['-c:v', encoder_name, '-crf', str(q_val), '-preset', 'medium']
            else: # H.264 (CPU)
                q_val = self.quality_cfg.get("cpu_h264_crf", 26)
                quality_val_str = f"CRF={q_val}"
                args = ['-c:v', encoder_name, '-crf', str(q_val), '-preset', 'medium']

        # ✅ 로그 메시지에 실제 품질 값 표시
        self.log.emit(f"사용할 인코더: {encoder_name} (설정: {self.hw_encoder_setting}, 품질: {quality_val_str})")
        return args

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
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            
            proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                  startupinfo=get_startupinfo(), creationflags=flags)
            
            if proc.returncode == 0:
                self.log.emit(f"파일 변환 성공: '{output_path.name}'")
                if self.delete_original and self.input_path.exists():
                    try:
                        self.input_path.unlink()
                        self.log.emit(f"원본 파일 삭제: '{self.input_path.name}'")
                    except OSError as e:
                        self.log.emit(f"[오류] 원본 파일 삭제 실패: {e}")
                self.finished.emit(True, self.url, str(output_path))
            else:
                self.log.emit(f"[오류] 파일 변환 실패: {proc.stderr}")
                if output_path.exists(): output_path.unlink()
                self.finished.emit(False, self.url, "")
        except Exception as e:
            self.log.emit(f"[오류] 파일 변환 중 예외 발생: {e}")
            self.finished.emit(False, self.url, "")