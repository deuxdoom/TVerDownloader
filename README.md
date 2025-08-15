<p align="center">
  <img src="main.png" alt="TVerDownloader 메인 UI" width="830">
</p>

<h1>
  <img src="./logo.png" alt="TVer Downloader Logo" width="60" style="vertical-align: middle;">
  티버 다운로더 (TVer Downloader)
</h1>

<a href="https://refer-nordvpn.com/RRXwGuSQXTe">
  <img src="https://img.shields.io/badge/NORDVPN-3개월%20무료-0054a6?style=for-the-badge&logo=nordvpn&logoColor=black&labelColor=white" alt="NordVPN 3개월 무료">
</a>
<a href="https://toon.at/donate/deuxdoom">
  <img src="https://img.shields.io/badge/후원하기-투네이션-ff69b4?style=for-the-badge&logo=githubsponsors" alt="후원하기">
</a>

[![RELEASE](https://img.shields.io/github/release/deuxdoom/TVerDownloader?style=flat&logo=github&logoColor=white&label=RELEASE&labelColor=2f353a&color=0ea5e9)](https://github.com/deuxdoom/TVerDownloader/releases/latest)
[![Downloads Latest](https://img.shields.io/github/downloads/deuxdoom/TVerDownloader/latest/total?logo=github&style=flat&label=DOWNLOADS@LATEST)](https://github.com/deuxdoom/TVerDownloader/releases/latest)
[![Downloads Total](https://img.shields.io/github/downloads/deuxdoom/TVerDownloader/total?logo=github&style=flat&label=DOWNLOADS)](https://github.com/deuxdoom/TVerDownloader/releases)
[![LICENSE](https://img.shields.io/badge/LICENSE-MIT-f43f5e?style=flat&labelColor=2f353a)](https://opensource.org/licenses/MIT)<br>
[![Platform](https://img.shields.io/badge/PLATFORM-WINDOWS%20X64-blue?style=flat&logo=windows)](https://github.com/deuxdoom/TVerDownloader)
[![PYTHON](https://img.shields.io/badge/PYTHON-3.10%2B-3776ab?style=flat&logo=python&logoColor=white&labelColor=2f353a)](https://www.python.org/)
[![PYQT6](https://img.shields.io/badge/PYQT6-GUI-10b981?style=flat&logo=qt&logoColor=white&labelColor=2f353a)](https://pypi.org/project/PyQt6/)<br>
[![Made with yt-dlp](https://img.shields.io/badge/made%20with-yt--dlp-orange?style=plastic)](https://github.com/yt-dlp/yt-dlp)
[![Made with FFmpeg](https://img.shields.io/badge/made%20with-FFmpeg-black?style=plastic&logo=ffmpeg)](https://ffmpeg.org/)


---

## 📜 간단 소개

**TVer Downloader**는 일본 티버 스트리밍 플랫폼의 동영상을 다운로드하도록 도와주는 GUI 기반의 프로그램입니다.  
PyQt6 기반의 직관적인 인터페이스와 yt-dlp/FFmpeg 자동 업데이트 등의 기능을 갖추고 있습니다.<br>
기본적으로 TVer의 영상 다운로드가 주목적이지만, YouTube의 영상 역시 다운로드가 가능합니다.<br>

---

## 💻 시스템 요구 사항

- Windows 10 / 11 (x64)
- Python 3.10 이상
- 인터넷 연결 및 일본 VPN 필요
- 런타임 에러가 발생할 경우: [Microsoft Visual C++ 재배포 가능 패키지 (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe)

---

## ✨ 주요 기능

- 최신 **yt-dlp** 및 **FFmpeg** 자동 업데이트
- **단일 및 다중 다운로드** (시리즈 URL 자동 분해 지원)
- **파일명 자유 커스터마이징** 및 순서 설정 지원
- **화질 선택** (최상 / 1080p / 720p)
- **포맷 변환** MP4 to AVI & MOV 오디오 추출 지원
- **썸네일 클릭 확대**, **완료 목록 더블클릭 재생**
- **트레이 알림**, **항상 위**, **진행률 표시 및 로그 강화**
- **라이트 / 다크 테마 전환 기능** (기본값 라이트)
- **다운로드 한 영상 및 즐겨찾기 시리즈 목록 자동 백업**
- **다운로드 후 폴더 열기 / 시스템 종료 등 후속 작업 지원**
- **가볍고 직관적인 UI** — 불필요한 기능 최소화, UX 중심 설계

---

## 🚀 사용 방법

1. TVer 영상 *URL*을 입력 창에 붙여넣기
2. **설정** 메뉴에서 저장 폴더, 화질, 동시 다운로드 수, 파일명 규칙 등 조정
3. **다운로드 시작** 버튼 클릭
4. 진행률·로그·썸네일로 실시간 상태 확인
5. **완료된 목록** 더블 클릭으로 영상재생

---

## ❗ 주의 사항

- 본 프로그램은 **개인적인 아카이빙 목적**으로만 사용해야 하며, 상업적 이용이나 재배포는 금지됩니다.
- TVer는 일본 내 서비스이므로, **일본 VPN 환경**에서만 정상 동작합니다.
- 다운로드한 콘텐츠의 **저작권 및 이용 약관**을 반드시 준수하세요.
- **Windows에서 'PC 보호' 또는 '서명되지 않은 파일' 경고**가 표시될 수 있습니다.  
  이 프로그램은 직접 빌드한 오픈소스 프로젝트로, 악성코드가 없으니 안심하고 실행해도 됩니다.
- **업데이트 시** 반드시 `TVerDownloader.exe` **파일**과 `_internal` **폴더**를 **함께 덮어쓰기** 해야 합니다.

---

## 🔧 개발 정보

- **GUI**: PyQt6  
- **다운로드 엔진**: yt-dlp + FFmpeg (자동 최신화 포함)  
- **설정 저장**: JSON 기반(config/history)  
- **안정성**: 예외 발생 시 크래시 로그(`TVerDownloader_crash.log`) 저장

---

## 🤝 기여 및 응원

- 버그 제보 및 코드 기여: [Issues](https://github.com/deuxdoom/TVerDownloader/issues)  
- 개발자 응원: [YouTube 구독](https://www.youtube.com/@LE_SSERAFIM?sub_confirmation=1)  
- 별 ⭐을 눌러주시면 큰 힘이 됩니다!

---
