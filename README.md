# My Apps Hub

로그인 하나로 여러 미니 서비스를 이용할 수 있는 통합 웹 플랫폼입니다.

## 배포 주소
- 허브: https://1joooh2.duckdns.org/hub/
- 여행추천: https://1joooh2.duckdns.org/travel/
- 할일관리: https://1joooh2.duckdns.org/todo/
- 청첩장 편집: https://1joooh2.duckdns.org/invite-edit/

## 기술 스택
- Backend: Python, FastAPI, SQLAlchemy, WebSocket
- Database: PostgreSQL
- Auth: JWT (python-jose), bcrypt 비밀번호 해싱
- Frontend: HTML, CSS, JavaScript (Vanilla)
- 외부 API: 카카오 로컬/이미지/지도 API, OpenWeatherMap
- Infra: AWS EC2 (Ubuntu), Nginx (Reverse Proxy), Let's Encrypt (SSL), DuckDNS

## 프로젝트 구성

### 1. 허브 (frontend/hub/)
로그인/회원가입 후 각 서비스로 이동하는 진입점

### 2. 여행추천 (frontend/travel/)
- 지역 검색 - 음식점/카페/명소 카테고리별 검색 (세부 서브카테고리 포함)
- 거리순 정렬 + 도보 시간 계산
- 카카오맵 시각화 (마커, 경로선)
- 데이트 코스 자동 추천 (테마/예산/소요시간 반영, 날씨 기반 자동 추천)
- 찜하기 + 폴더 관리 + 폴더 내 동선/이동수단 추천
- 실시간 채팅 (WebSocket, 로그인 기반, 대화 기록 DB 저장)
- 장소 이미지 표시, 카카오톡/링크 공유

### 3. 할일관리 (frontend/todo/)
로그인 계정 기준 CRUD 투두리스트

### 4. 모바일 청첩장 (frontend/invite-edit/, frontend/invite/)
- 신랑신부 정보, 인사말, 예식 일시/장소(지도) 입력
- 사진 업로드 및 에디토리얼 스타일 갤러리
- 방명록 (비로그인 사용자도 작성 가능)
- 테마 색상/대표사진/배경음악 커스터마이징 (진행 중)

## 아키텍처
브라우저에서 Nginx(443, SSL)를 거쳐 FastAPI(8001, uvicorn) 백엔드와 PostgreSQL로 연결됩니다.
정적 파일은 /var/www/ 아래 travel, hub, todo, invite, invite-edit 폴더에서 서빙됩니다.

## 주요 Troubleshooting
- Certbot과 리버스 프록시 충돌: SSL 적용 시 Certbot이 생성한 서버 블록에 프록시 설정이 누락되어 발생. nginx -T로 전체 설정을 확인해 해결
- CSS 클래스 특이성 문제: .hidden 클래스가 특정 조합(.subcategories.hidden)에만 정의되어 있어 다른 요소에 적용 안 됨. 독립 클래스로 재정의하여 해결
- DB 스키마 변경 미반영: Base.metadata.create_all()은 기존 테이블에 새 컬럼을 추가하지 못함. ALTER TABLE로 직접 컬럼 추가
- WebSocket 404: uvicorn에 WebSocket 지원 라이브러리(uvicorn[standard])가 없어 발생. 재설치로 해결
- 긴 파일 편집 시 문자열 불일치: str_replace 방식이 반복적으로 실패하는 경우, head/tail/sed로 줄 번호 기반 정밀 편집이 훨씬 안전함을 체득

## 앞으로 개선하고 싶은 점
- 청첩장 테마 색상/음악/대표사진을 공개 페이지에 실제 반영
- 모바일 반응형 전체 점검
- 청첩장 RSVP, 계좌번호 기능 추가
- CI/CD 자동 배포 구축
