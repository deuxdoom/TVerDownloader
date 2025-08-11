# src/threads/conversion_thread.py
# 수정: 변환 성공 시 원본 파일을 삭제하는 옵션 추가

import os
import subprocess
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from src.utils import get_startupinfo

class ConversionThread(QThread):
    finished = pyqtSignal(bool, str, str)
    log = pyqtSignal(str)

    def __init__(self, url: str, input_path: str, target_format: str, 
                 ffmpeg_path: str, delete_original: bool, parent=None):
        super().__init__(parent)
        self.url = url
        self.input_path = Path(input_path)
        self.target_format = target_format
        self.ffmpeg_path = ffmpeg_path
        self.delete_original = delete_original

    def run(self):
        output_path = self.input_path.with_suffix(f".{self.target_format}")
        
        command = [self.ffmpeg_path, '-i', str(self.input_path), '-y']
        
        if self.target_format == 'mp3':
            command.extend(['-vn', '-c:a', 'libmp3lame', '-q:a', '2'])
        elif self.target_format in ['avi', 'mov']:
            command.extend(['-c', 'copy'])
        
        command.append(str(output_path))

        try:
            self.log.emit(f"파일 변환 시작: '{self.input_path.name}' -> '{output_path.name}'")
            proc = subprocess.run(
                command, capture_output=True, text=True, encoding="utf-8",
                startupinfo=get_startupinfo(),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if proc.returncode == 0:
                self.log.emit(f"파일 변환 성공: '{output_path.name}'")
                
                # 변환 성공 및 삭제 옵션 활성화 시 원본 파일 삭제
                if self.delete_original:
                    try:
                        self.input_path.unlink()
                        self.log.emit(f"원본 파일 삭제: '{self.input_path.name}'")
                    except OSError as e:
                        self.log.emit(f"[오류] 원본 파일 삭제 실패: {e}")

                self.finished.emit(True, self.url, str(output_path))
            else:
                self.log.emit(f"[오류] 파일 변환 실패: {proc.stderr}")
                self.finished.emit(False, self.url, "")

        except Exception as e:
            self.log.emit(f"[오류] 파일 변환 중 예외 발생: {e}")
            self.finished.emit(False, self.url, "")