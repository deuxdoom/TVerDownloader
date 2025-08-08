\# TVer Downloader



!\[TVer Downloader Logo](./logo.png)  

\*\*\[GitHub Repository](https://github.com/deuxdoom/TVerDownloader)\*\* | \*\*\[Issues](https://github.com/deuxdoom/TVerDownloader/issues)\*\* | \*\*\[Releases](https://github.com/deuxdoom/TVerDownloader/releases)\*\*  



TVer Downloader는 일본 TVer 플랫폼의 동영상을 효율적으로 다운로드하기 위한 오픈소스 도구입니다. PyQt6 기반 GUI와 yt-dlp를 활용하여 사용자 맞춤형 다운로드 경험을 제공합니다.



\## 프로젝트 개요

| 항목            | 설명                                      |

|-----------------|-------------------------------------------|

| \*\*목적\*\*        | TVer의 지역 제한을 우회한 다운로드 지원    |

| \*\*버전\*\*        | v1.2.0                                    |

| \*\*최신 릴리스\*\* | \[v1.2.0](https://github.com/deuxdoom/TVerDownloader/releases/tag/v1.2.0) |

| \*\*라이선스\*\*    | MIT (변경 가능)                            |

| \*\*언어\*\*        | Python 3.8+                               |



\## 기능

\- \*\*다운로드 관리\*\*: 단일 URL 기반 다운로드.

\- \*\*품질 옵션\*\*: 최상, 1080p, 720p, 오디오 추출.

\- \*\*파일명 커스터마이징\*\*: 시리즈명, 날짜, 에피소드 번호 포함.

\- \*\*테마 지원\*\*: 라이트/다크 모드 전환.

\- \*\*후속 작업\*\*: 다운로드 완료 후 폴더 열기, 시스템 종료.



\## 사용 방법

1\. \*\*URL 입력\*\*: "URL 추가" 버튼으로 TVer 링크 입력.

2\. \*\*설정 조정\*\*: "설정" 메뉴에서 품질, 파일명 구조, 테마 선택.

3\. \*\*다운로드 시작\*\*: "다운로드 시작" 버튼 클릭.

4\. \*\*진행 모니터링\*\*: GUI 진행바로 상태 확인.



\## 개발 세부사항

\- \*\*프레임워크\*\*: PyQt6로 GUI 구현.

\- \*\*엔진\*\*: yt-dlp로 TVer 스트리밍 처리.

\- \*\*설정 저장\*\*: JSON 형식(downloader\_config.json).

\- \*\*제약\*\*: 다중 URL 미지원, 네트워크 안정성 의존.



\## 기여 및 지원

\- \*\*버그 보고\*\*: \[Issues](https://github.com/deuxdoom/TVerDownloader/issues)에서 상세히 제출.

\- \*\*코드 기여\*\*: 풀 리퀘스트 제출 전 로컬 테스트, 코드 스타일 준수.

\- \*\*문의\*\*: \[브런치](https://brunch.co.kr/@sashiko/8) 또는 \[YouTube](https://www.youtube.com/@LE\_SSERAFIM).



\## 로드맵

\- 자동 업데이트 체크 기능 추가.

\- 다중 파일 업로드 지원 검토.

\- 네트워크 상태 모니터링 구현.



\## 배지

\[!\[Build Status](https://img.shields.io/badge/build-passing-brightgreen)](https://github.com/deuxdoom/TVerDownloader/actions)

\[!\[License](https://img.shields.io/badge/license-MIT-blue)](https://opensource.org/licenses/MIT)

