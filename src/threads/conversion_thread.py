# src/threads/conversion_thread.py
# 수정: ffmpeg 실행 시 GUI 프로그램과의 충돌을 방지하기 위해
#       Windows에서 DETACHED_PROCESS creationflag를 사용하여 안정성 확보

import os
import subprocess
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from src.utils import get_startupinfo

class ConversionThread(QThread):
    # 시그널: (성공여부, 원본 URL, 변환된 파일 경로)
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
        
        # ffmpeg 명령어 구성
        command = [
            self.ffmpeg_path,
            '-i', str(self.input_path),
            '-y', # 덮어쓰기
        ]
        
        # 포맷별 변환 옵션
        if self.target_format == 'mp3':
            command.extend(['-vn', '-c:a', 'libmp3lame', '-q:a', '2'])
        elif self.target_format in ['avi', 'mov']:
            # 코덱을 그대로 복사하여 빠른 속도로 컨테이너만 변경 (remux)
            command.extend(['-c', 'copy'])
        
        command.append(str(output_path))

        try:
            self.log.emit(f"파일 변환 시작: '{self.input_path.name}' -> '{output_path.name}'")
            
            # --- 안정적인 프로세스 실행을 위한 플래그 설정 ---
            flags = 0
            if os.name == 'nt':
                # DETACHED_PROCESS는 부모 GUI와 완전히 독립된 세션에서 실행하여 충돌을 방지
                flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
            
            proc = subprocess.run(
                command,
                capture_output=True, text=True, encoding="utf-8",
                startupinfo=get_startupinfo(),
                creationflags=flags
            )
            
            if proc.returncode == 0:
                self.log.emit(f"파일 변환 성공: '{output_path.name}'")
                
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