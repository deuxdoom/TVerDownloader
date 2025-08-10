![TVer Application](./main.png)
<h1>
  <img src="./logo.png" alt="TVer Downloader Logo" width="60" style="vertical-align: middle;">
  티버 다운로더 (TVer Downloader)
</h1>
[![GitHub release](https://img.shields.io/github/release/deuxdoom/TVerDownloader?logo=github&style=for-the-badge)](https://github.com/deuxdoom/TVerDownloader/releases/latest)
[![GitHub downloads latest](https://img.shields.io/github/downloads/deuxdoom/TVerDownloader/latest/total?logo=github&style=for-the-badge)](https://github.com/deuxdoom/TVerDownloader/releases/latest)
[![GitHub downloads total](https://img.shields.io/github/downloads/deuxdoom/TVerDownloader/total?logo=github&style=for-the-badge)](https://github.com/deuxdoom/TVerDownloader/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/platform-Windows%20x64-blue?style=for-the-badge&logo=windows)](https://github.com/deuxdoom/TVerDownloader)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/PyQt-6-green?style=for-the-badge)](https://pypi.org/project/PyQt6/)
[![Made with yt-dlp](https://img.shields.io/badge/made%20with-yt--dlp-orange?style=for-the-badge)](https://github.com/yt-dlp/yt-dlp)
[![Made with FFmpeg](https://img.shields.io/badge/made%20with-FFmpeg-black?style=for-the-badge&logo=ffmpeg)](https://ffmpeg.org/)

---

## 📜 간단 소개

**TVer Downloader**는 일본 TVer 플랫폼의 지역 제한을 우회해 동영상을 다운로드하고 관리할 수 있도록 도와주는 GUI 도구입니다.  
PyQt6 기반의 직관적인 인터페이스와 yt-dlp/FFmpeg 자동 업데이트 등의 기능을 갖추고 있습니다.

---

## 💻 시스템 요구 사항

- Windows 10 / 11 (x64)
- Python 3.8 이상 (실행용 EXE 포함)
- 인터넷 연결 및 일본 VPN 필요
- 설치 전 필수: [Microsoft Visual C++ 재배포 가능 패키지 (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe)

---

## ✨ 주요 기능 (v2.3.2 기준)

- 최신 **yt-dlp** 및 **FFmpeg** 자동 업데이트
- **단일 및 다중 다운로드** (시리즈 URL 자동 분해 지원)
- **파일명 자유 커스터마이징** 및 순서 설정 지원
- **화질 선택** (최상 / 1080p / 720p / 오디오 전용)
- **썸네일 클릭 확대**, **완료 목록 더블클릭 재생**
- **트레이 알림**, **항상 위**, **진행률 표시 및 로그 강화**
- **히스토리 및 즐겨찾기 자동 백업**
- **다운로드 후 폴더 열기 / 시스템 종료 등 후속 작업 지원**
- **가볍고 직관적인 UI** — 불필요한 기능 최소화, UX 중심 설계

---

## 🚀 설치 및 사용 방법

1. TVer 영상 *URL*을 입력 창에 붙여넣기
2. **설정** 메뉴에서 저장 폴더, 화질, 동시 다운로드 수, 파일명 규칙 등 조정
3. **다운로드 시작** 버튼 클릭
4. 진행률·로그·썸네일로 실시간 상태 확인
5. **완료된 목록** 더블 클릭으로 영상재생

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
