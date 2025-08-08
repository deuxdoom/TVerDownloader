import os
import json
import requests
import zipfile
import shutil
import subprocess
import re
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal
from src.utils import get_startupinfo

class SetupThread(QThread):
    log = pyqtSignal(str)
    finished = pyqtSignal(bool, str, str)

    BIN_DIR = Path("bin")
    YTDLP_API_URL = "https://api.github.com/repos/yt-dlp/yt-dlp-nightly-builds/releases/latest"
    FFMPEG_API_URL = "https://api.github.com/repos/GyanD/codexffmpeg/releases/latest"
    FFMPEG_ASSET_KEYWORD = "essentials"
    FFMPEG_ASSET_EXTENSION = ".zip"

    def run(self):
        try:
            ytdlp_exe_path = self._update_ytdlp()
            ffmpeg_exe_path = self._update_ffmpeg()
            if ytdlp_exe_path and ffmpeg_exe_path:
                self.finished.emit(True, ytdlp_exe_path, ffmpeg_exe_path)
            else:
                self.finished.emit(False, "", "")
        except Exception as e:
            self.log.emit(f"[치명적 오류] 설정 중 예외 발생: {e}")
            self.finished.emit(False, "", "")

    def _get_api_info(self, url):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            self.log.emit(f"[오류] GitHub API 호출 실패: {e}")
            return None

    def _download_and_place(self, url, target_path):
        self.log.emit(f" -> 다운로드 시작: {url}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(target_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return True

    def _download_and_unzip(self, url, target_dir, file_name):
        target_dir.mkdir(parents=True, exist_ok=True)
        zip_path = target_dir / file_name
        self.log.emit(f" -> 다운로드 시작: {url}")
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(zip_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        self.log.emit(f" -> 압축 해제 중: {zip_path}")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(target_dir)
        os.remove(zip_path)
        return True

    def _update_ytdlp(self):
        self.log.emit("[1] yt-dlp.exe 최신 버전 확인 중...")
        ytdlp_exe_path = self.BIN_DIR / "yt-dlp.exe"
        version_file = self.BIN_DIR / "ytdlp_version.txt"
        release_info = self._get_api_info(self.YTDLP_API_URL)
        if not release_info:
            return None
        latest_version = release_info.get("tag_name")
        current_version = version_file.read_text().strip() if version_file.exists() else None
        if latest_version == current_version and ytdlp_exe_path.exists():
            self.log.emit(f" ... yt-dlp.exe가 이미 최신 버전입니다 ({latest_version}).")
        else:
            self.log.emit(f" ... 새 버전 발견: {latest_version} (현재: {current_version or '없음'})")
            asset = next((a for a in release_info["assets"] if a['name'] == 'yt-dlp.exe'), None)
            if not asset:
                self.log.emit("[오류] yt-dlp.exe 에셋을 찾을 수 없습니다.")
                return None
            if self._download_and_place(asset['browser_download_url'], ytdlp_exe_path):
                version_file.write_text(latest_version)
                self.log.emit(" ... yt-dlp.exe 업데이트 완료.")
        return str(ytdlp_exe_path)

    def _update_ffmpeg(self):
        self.log.emit("[2] FFmpeg 최신 버전 확인 중...")
        ffmpeg_exe_path = self.BIN_DIR / "ffmpeg.exe"
        version_file = self.BIN_DIR / "ffmpeg_version.txt"
        release_info = self._get_api_info(self.FFMPEG_API_URL)
        if not release_info:
            return None
        latest_version = release_info.get("tag_name")
        current_version = version_file.read_text().strip() if version_file.exists() else None
        if latest_version == current_version and ffmpeg_exe_path.exists():
            self.log.emit(f" ... FFmpeg가 이미 최신 버전입니다 ({latest_version}).")
        else:
            self.log.emit(f" ... 새 버전 발견: {latest_version} (현재: {current_version or '없음'})")
            asset = next((a for a in release_info["assets"] if self.FFMPEG_ASSET_KEYWORD in a['name'] and a['name'].endswith(self.FFMPEG_ASSET_EXTENSION)), None)
            if not asset:
                self.log.emit(f"[오류] FFmpeg .zip 에셋을 찾을 수 없습니다.")
                return None
            temp_ffmpeg_dir = self.BIN_DIR / "ffmpeg_temp"
            if temp_ffmpeg_dir.exists():
                shutil.rmtree(temp_ffmpeg_dir)
            if self._download_and_unzip(asset['browser_download_url'], temp_ffmpeg_dir, asset['name']):
                extracted_folder = next(temp_ffmpeg_dir.iterdir(), None)
                source_exe_path = None
                if extracted_folder and extracted_folder.is_dir() and (extracted_folder / "bin" / "ffmpeg.exe").exists():
                    source_exe_path = extracted_folder / "bin" / "ffmpeg.exe"
                if source_exe_path:
                    if ffmpeg_exe_path.exists():
                        os.remove(ffmpeg_exe_path)
                    shutil.move(str(source_exe_path), str(ffmpeg_exe_path))
                    self.log.emit(f" -> {ffmpeg_exe_path}로 이동 완료.")
                else:
                    self.log.emit("[오류] 압축 해제된 파일에서 ffmpeg.exe를 찾을 수 없습니다.")
                    shutil.rmtree(temp_ffmpeg_dir)
                    return None
                shutil.rmtree(temp_ffmpeg_dir)
                version_file.write_text(latest_version)
                self.log.emit(" ... FFmpeg 업데이트 완료.")
        return str(ffmpeg_exe_path) if ffmpeg_exe_path.exists() else None

class SeriesParseThread(QThread):
    log = pyqtSignal(str)
    finished = pyqtSignal(list)

    def __init__(self, series_url, ytdlp_exe_path):
        super().__init__()
        self.series_url = series_url
        self.ytdlp_exe_path = ytdlp_exe_path

    def run(self):
        self.log.emit(f"시리즈 URL 분석 중: {self.series_url}")
        try:
            command_get_info = [
                self.ytdlp_exe_path, self.series_url,
                '--flat-playlist', '--print', '%(original_url)s\t%(title)s',
                '--encoding', 'utf-8'
            ]
            startupinfo = get_startupinfo()
            process = subprocess.Popen(command_get_info, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                error_message = stderr.decode('utf-8', errors='replace')
                self.log.emit(f"[오류] 시리즈 분석 실패:\n{error_message}")
                self.finished.emit([])
                return
            output = stdout.decode('utf-8', errors='replace')
            all_episodes = [line.split('\t') for line in output.strip().split('\n') if '\t' in line]
            self.log.emit(f"시리즈에서 {len(all_episodes)}개의 에피소드를 찾았습니다. 예고편을 제외합니다...")
            final_urls = []
            for url, title in all_episodes:
                if "予告" not in title:
                    final_urls.append(url)
                else:
                    self.log.emit(f" -> 예고편 제외: {title}")
            self.log.emit(f"최종적으로 {len(final_urls)}개의 에피소드를 다운로드 목록에 추가합니다.")
            self.finished.emit(final_urls)
        except Exception as e:
            self.log.emit(f"[오류] 시리즈 분석 중 예외 발생: {e}")
            self.finished.emit([])

class DownloadThread(QThread):
    progress = pyqtSignal(str, dict)
    finished = pyqtSignal(str, bool)

    def __init__(self, url, download_folder, ytdlp_exe_path, ffmpeg_exe_path, filename_format, quality_format):
        super().__init__()
        self.url = url
        self.download_folder = download_folder
        self.ytdlp_exe_path = ytdlp_exe_path
        self.ffmpeg_exe_path = ffmpeg_exe_path
        self.filename_format = filename_format
        self.quality_format = quality_format
        self.process = None

    def run(self):
        try:
            self.progress.emit(self.url, {'status': '정보 분석 중...'})
            info_command = [
                self.ytdlp_exe_path, self.url,
                '--get-title', '--get-thumbnail', '--get-filename', '--no-warnings',
                '--encoding', 'utf-8',
                '-o', os.path.join(self.download_folder, '%(series)s', self.filename_format)
            ]
            startupinfo = get_startupinfo()
            info_process = subprocess.Popen(info_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
            stdout, stderr = info_process.communicate()
            if info_process.returncode == 0:
                output = stdout.decode('utf-8', errors='replace')
                lines = output.strip().split('\n')
                title = lines[0] if len(lines) > 0 else "제목을 찾을 수 없음"
                thumbnail_url = lines[1] if len(lines) > 1 else None
                final_filepath = lines[2] if len(lines) > 2 else None
                self.progress.emit(self.url, {'status': '대기 중', 'title': title, 'thumbnail_url': thumbnail_url, 'final_filepath': final_filepath})
            else:
                error_message = (stdout.decode('utf-8', errors='replace') + stderr.decode('utf-8', errors='replace')).strip()
                self.progress.emit(self.url, {'status': '오류', 'log': f"정보 가져오기 실패:\n{error_message}"})
                self.finished.emit(self.url, False)
                return
            output_template = os.path.join(self.download_folder, '%(series)s', self.filename_format)
            command = [
                self.ytdlp_exe_path, self.url,
                '--ffmpeg-location', os.path.dirname(self.ffmpeg_exe_path), '-o', output_template,
                '--retries', '10', '--fragment-retries', '10', '--buffer-size', '16K', '--force-overwrites',
                '--no-keep-fragments', '--no-check-certificate', '--no-mtime',
                '--windows-filenames', '--no-cache-dir', '--abort-on-error', '--no-continue',
                '--add-header', 'Accept-Language:ja-JP', '--console-title', '--progress',
                '--encoding', 'utf-8', '--newline',
                '--write-subs', '--sub-format', 'vtt', '--embed-subs'  # 자막 VTT로 고정 및 임베드
            ]
            if self.quality_format == "audio_only":
                command.extend(['-f', 'bestaudio', '-x', '--audio-format', 'mp3'])
            else:
                command.extend(['-f', self.quality_format, '--merge-output-format', 'mp4'])
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, startupinfo=startupinfo)
            current_component = "비디오"
            for line_bytes in iter(self.process.stdout.readline, b''):
                line = line_bytes.decode('utf-8', errors='replace').strip()
                if '[download] Destination:' in line:
                    if 'audio' in line.lower() or '.m4a' in line.lower():
                        current_component = "오디오"
                    else:
                        current_component = "비디오"
                progress_match = re.search(r'\[download\]\s+([0-9.]+)% of.*?at (.*?/s) ETA (.*)', line)
                if progress_match:
                    percent = float(progress_match.group(1))
                    speed = progress_match.group(2)
                    eta = progress_match.group(3)
                    status_text = f"다운로드 중 ({current_component})"
                    self.progress.emit(self.url, {'status': status_text, 'percent': percent, 'speed': speed, 'eta': eta, 'log': line})
                elif '[ffmpeg] Merging formats' in line or '[EmbedSubtitle] Embedding subtitles' in line or '[ExtractAudio] Destination' in line:
                    self.progress.emit(self.url, {'status': '후처리 중...', 'log': line})
                elif '[download] Writing subtitle file' in line:
                    self.progress.emit(self.url, {'status': '자막 처리 중...', 'log': line})
                else:
                    self.progress.emit(self.url, {'log': line})
            self.process.wait()
            if self.process.returncode == 0:
                self.progress.emit(self.url, {'status': '완료', 'percent': 100})
                self.finished.emit(self.url, True)
            else:
                if self.process.returncode != -1:
                    self.progress.emit(self.url, {'status': '오류', 'log': f"yt-dlp 프로세스가 오류 코드 {self.process.returncode}로 종료되었습니다."})
                self.finished.emit(self.url, False)
        except Exception as e:
            self.progress.emit(self.url, {'status': '오류', 'log': f"다운로드 프로세스 실행 중 오류 발생: {e}"})
            self.finished.emit(self.url, False)

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.progress.emit(self.url, {'status': '중단됨'})