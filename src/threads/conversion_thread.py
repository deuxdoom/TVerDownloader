# src/threads/conversion_thread.py
# 수정: 컨테이너 포맷 변환뿐만 아니라 비디오 코덱 재인코딩 기능 추가

import os
import subprocess
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from src.utils import get_startupinfo

class ConversionThread(QThread):
    finished = pyqtSignal(bool, str, str)
    log = pyqtSignal(str)

    def __init__(self, url: str, input_path: str, ffmpeg_path: str,
                 target_format: Optional[str], target_codec: Optional[str],
                 delete_original: bool, parent=None):
        super().__init__(parent)
        self.url = url
        self.input_path = Path(input_path)
        self.ffmpeg_path = ffmpeg_path
        self.target_format = target_format
        self.target_codec = target_codec
        self.delete_original = delete_original

    def run(self):
        # 출력 파일 경로 설정
        if self.target_codec:
            # 코덱 변환 시에는 확장자를 .mp4로 유지
            output_path = self.input_path.with_name(f"{self.input_path.stem}_{self.target_codec}.mp4")
        elif self.target_format:
            output_path = self.input_path.with_suffix(f".{self.target_format}")
        else:
            self.log.emit("[오류] 변환 목표(포맷 또는 코덱)가 지정되지 않았습니다.")
            self.finished.emit(False, self.url, ""); return

        command = [self.ffmpeg_path, '-i', str(self.input_path), '-y']
        
        if self.target_codec:
            # 비디오 코덱 재인코딩 (오디오는 복사하여 속도 향상 및 품질 보존)
            command.extend(['-c:v', self.target_codec, '-c:a', 'copy'])
        elif self.target_format == 'mp3':
            # 오디오 추출
            command.extend(['-vn', '-c:a', 'libmp3lame', '-q:a', '2'])
        elif self.target_format in ['avi', 'mov']:
            # 컨테이너만 변경 (remux)
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
                if output_path.exists(): output_path.unlink() # 실패 시 생성된 파일 삭제
                self.finished.emit(False, self.url, "")
        except Exception as e:
            self.log.emit(f"[오류] 파일 변환 중 예외 발생: {e}")
            self.finished.emit(False, self.url, "")