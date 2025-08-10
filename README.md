![TVer Application](./main.png)
# 티버 다운로더 (TVer Downloader)

![TVer Downloader Logo](./logo.png)

[![GitHub release](https://img.shields.io/github/release/deuxdoom/TVerDownloader?logo=github&style=for-the-badge)](https://github.com/deuxdoom/TVerDownloader/releases/latest)
[![GitHub downloads latest](https://img.shields.io/github/downloads/deuxdoom/TVerDownloader/latest/total?logo=github&style=for-the-badge)](https://github.com/deuxdoom/TVerDownloader/releases/latest)
[![GitHub downloads total](https://img.shields.io/github/downloads/deuxdoom/TVerDownloader/total?logo=github&style=for-the-badge)](https://github.com/deuxdoom/TVerDownloader/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/platform-Windows%20x64-blue?style=for-the-badge&logo=windows)](https://github.com/deuxdoom/TVerDownloader)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/PyQt-6-green?style=for-the-badge)](https://pypi.org/project/PyQt6/)
[![Made with yt-dlp](https://img.shields.io/badge/made%20with-yt--dlp-orange?style=for-the-badge)](https://github.com/yt-dlp/yt-dlp)
[![Made with FFmpeg](https://img.shields.io/badge/made%20with-FFmpeg-black?style=for-the-badge&logo=ffmpeg)](https://ffmpeg.org/)

📌 [**Repository**](https://github.com/deuxdoom/TVerDownloader)  
🐞 [**Issues**](https://github.com/deuxdoom/TVerDownloader/issues)  

--- 

**TVer Downloader**는 일본 TVer 플랫폼의 동영상을 다운로드하기 위한 오픈소스 도구입니다.  
PyQt6와 yt-dlp를 활용해 직관적인 GUI와 다양한 사용자 설정 기능을 제공합니다.

---

## 📦 시스템 요구 사항

- Windows 10 / 11 (x64)
- 인터넷 연결 (첫 실행 시 구성 요소 자동 준비), 일본 VPN 필수
- ⚠ [Microsoft Visual C++ 재배포 가능 패키지 (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe) 를 반드시 설치해야 합니다.

---

## 📝 개요

- **목적**: 티버(TVer)의 스트리밍 영상들을 일본VPN을 통해 다운로드하는 툴
- **릴리스**: [v2.3.2](https://github.com/deuxdoom/TVerDownloader/releases/tag/v2.3.2)
- **라이선스**: MIT
- **언어**: Python 3.8+

---

## ✨ 주요 기능

- 최신 버전 업데이트 지원
- 단일 및 다중 다운로드 지원
- 다운로드 엔진 yt-dlp + ffmpeg 자동 최신화
- 시리즈 즐겨찾기 등록을 통한 자동 다운로드
- 화질 선택 기능 (최상, 1080p, 720p, 오디오 전용)
- 파일명 커스터마이징 (시리즈명, 날짜 등)
- 후속 작업 지원 (폴더 열기, 시스템 종료 등)
- 썸네일 클릭 확대 및 완료 목록 더블 클릭시 재생 기능
- 로그 표시 강화 및 히스토리와 즐겨찾기 목록 상시 백업 
- 메인창 항상 위 가능 
- 최소화시 트레이로 감춤
 
---

## 🛠 사용 방법

1. **URL 추가** 하는 빈칸에 TVer 영상 링크 붙여넣기
2. **설정** 탭에서 저장 폴더 설정, 동시 다운 갯수, 파일명, 화질등을 조정
3. **다운로드 시작** 버튼 클릭
4. 진행바로 다운로드 상태 확인
5. 즐겁게 영상 감상!

---

## 🔧 개발 정보

- **GUI 프레임워크**: PyQt6
- **다운로드 엔진**: yt-dlp
- **설정 방식**: JSON 기반
- **제약 사항**: VPN 네트워크 의존

---

## 🤝 응원

- 유투브 구독으로 개발자를 응원해 주세요! [YouTube](https://www.youtube.com/@LE_SSERAFIM?sub_confirmation=1)

---

## 🗺️ 추가 기능 로드맵

- 여러분의 참신한 아이디어를 기다립니다!
- 기타 등등 생각만 많음 o_o;

---

## ❓ 자주 묻는 질문 (FAQ)

- **0%에서 멈춤/403** → 일본 **VPN**이 꺼져 있거나 연결 상태가 불안정할 때 발생합니다.
- **병합 실패 / 오디오 추출 실패** → FFmpeg 준비 완료 여부를 로그에서 확인 후 재시도하세요.
- **보안 경고** → 일부 보안/백신 프로그램이 악성코드 또는 트로이목마로 오진 할 수 있습니다.  
- **Windows의 PC보호** → 윈도우 서명하지 않은 파일이라는 스크린 차단 경고의 경우
  파이썬 소스코드를 빌드 exe파일이기에 뜨는 단순 화이트리스트 관련 경고이며 악성코드는 절대 없으니 안심하셔도 됩니다.
- **PyQt6 관련 오류** → 업데이트시 EXE 파일만 복붙한 경우로, EXE를 비롯한 _internal 폴더까지 같이 덮어 씌우시면 해결 됩니다.

---

## 📜 라이선스

- 오픈소스 사용 고지 및 링크는 앱 **정보(About)** 창에서 확인할 수 있습니다.