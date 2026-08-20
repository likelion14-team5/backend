# Global Meeting Backend

공유 링크로 2~4명이 프로필을 입력하고 Daily private room에 입장하는 화상회의 MVP 백엔드입니다. 회의·초대·참가자 프로필·Daily 미디어 세션·퇴장·종료에 더해 F-02(발언 전 추천)/F-03(발언 후 피드백) AI 엔드포인트가 참가자 토큰 인증, 회의 맥락 연동, DB 저장까지 포함된 형태로 구현되어 있습니다. STT API(음성→텍스트 자동 전송)는 아직 없습니다. 자세한 범위는 `docs/BACKEND_HANDOFF.md` 3.3.1절을 참고합니다.

## 기술 구성

- FastAPI, Pydantic v2
- SQLAlchemy 2.x 동기식, psycopg 3
- PostgreSQL 15+, Alembic
- HTTPX 동기식 Daily REST API 클라이언트
- 참가자 범위 opaque token (`X-Participant-Token`)

영상과 음성은 백엔드를 통과하지 않습니다. 백엔드는 Daily private room과 참가자별 단기 meeting token을 발급하며, 프론트엔드는 반환된 `room_url`과 `meeting_token`을 Daily Prebuilt에 전달합니다.

## 로컬 실행

Python 3.12와 Docker가 필요합니다.

AWS 단일 EC2에서 프론트엔드·백엔드·PostgreSQL을 Docker Compose로 배포하는 절차는
`docs/AWS_EC2_DOCKER_DEPLOYMENT.md`를 참고하세요.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d db
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

실행 설정은 항상 `backend/.env`에서 읽습니다. `.env.example`은 최초 `.env` 생성용 형식 예시일 뿐이며 애플리케이션이 직접 읽지 않습니다. 이미 `.env`가 있으면 복사 명령으로 덮어쓰지 마세요. `.env`의 `DAILY_API_KEY`를 실제 키로 설정해야 회의 생성과 미디어 세션 발급이 동작합니다. API 문서는 `http://localhost:8000/docs`에서 확인할 수 있습니다.

저장소에 포함된 로컬 테스트 프론트를 사용할 때는 위 FastAPI 터미널을 그대로 둔 채 **새 PowerShell 터미널**을 열어 다음 명령을 실행합니다.

```powershell
cd D:\Code\VScode-code\likelion14-team5\backend
.\.venv\Scripts\python.exe .local-video-check\serve.py
```

FastAPI `8000`과 테스트 프론트 `5173` 두 프로세스가 모두 실행 중이어야 합니다. `http://localhost:5173`에서 회의를 생성한 뒤 음성 분석 동의, 한국어/영어 선택, 음성 인식 시작, interim/final 문장, 초대 링크 입장과 회의 종료를 순서대로 확인합니다. 상세 절차는 `docs/BACKEND_HANDOFF.md`의 **14. 로컬 화상회의 테스트 프론트**를 참고합니다.

주요 환경변수:

| 이름 | 용도 |
|---|---|
| `DATABASE_URL` | PostgreSQL SQLAlchemy URL |
| `FRONTEND_ORIGIN` | CORS를 허용할 프론트엔드 origin |
| `PUBLIC_APP_URL` | 공유 링크를 만들 프론트엔드 주소 |
| `DAILY_API_KEY` | 서버에서만 사용하는 Daily API 키 |
| `DAILY_DOMAIN` | Daily room URL에 사용하는 팀 도메인 |
| `DAILY_ROOM_TTL_MINUTES` | Daily room 만료 시간 |
| `DAILY_TOKEN_TTL_MINUTES` | 참가자별 Daily token 만료 시간 |
| `OPENAI_API_KEY` | F-02/F-03 AI 엔드포인트에서 사용하는 OpenAI API 키 |
| `OPENAI_MODEL` | 사용할 OpenAI 모델 (기본값 `gpt-4o-mini`) |
| `OPENAI_MAX_RETRIES` | rate limit(429)·5xx·연결 오류 시 SDK 자동 재시도 횟수 (기본값 `3`) |

## 프론트엔드 연결 순서

1. `POST /api/v1/meetings`로 회의와 HOST 프로필을 생성합니다.
2. 응답의 `participant_token`은 해당 탭의 `sessionStorage`에 저장하고 `share_url`을 공유합니다.
3. 초대받은 사용자는 `GET /api/v1/meetings/{meeting_id}/public`으로 입장 가능 여부를 확인합니다.
4. `POST /api/v1/meetings/{meeting_id}/participants`로 프로필과 동의를 제출하고 반환된 토큰을 저장합니다.
5. 회의 화면에서는 이후 요청에 `X-Participant-Token` 헤더를 넣습니다.
6. `POST /api/v1/meetings/{meeting_id}/media-session`의 `room_url`과 `meeting_token`으로 Daily Prebuilt에 입장합니다.
7. `GET /api/v1/meetings/{meeting_id}/participants`를 3초 간격으로 polling해 프로필 카드를 갱신합니다.
8. 일반 퇴장은 `/leave`, HOST의 전체 종료는 `/end`를 호출합니다.

Daily API 키, 참가자 원문 토큰, Daily meeting token을 프론트 번들·DB·로그에 넣으면 안 됩니다. 참가자 원문 토큰은 생성 또는 입장 응답에서 한 번만 전달되며 DB에는 SHA-256 해시만 저장됩니다.

## 현재 API

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/v1/meetings` | Daily 방, 회의, HOST 생성 |
| GET | `/api/v1/meetings/{meeting_id}/public` | 입장 전 공개 정보 |
| POST | `/api/v1/meetings/{meeting_id}/participants` | 프로필 입력 후 입장 |
| GET | `/api/v1/meetings/{meeting_id}` | 회의 초기 컨텍스트 |
| POST | `/api/v1/meetings/{meeting_id}/media-session` | Daily 단기 입장 토큰 |
| GET | `/api/v1/meetings/{meeting_id}/participants` | 현재 참가자 목록 |
| GET | `/api/v1/meetings/{meeting_id}/participants/{participant_id}` | 공개 프로필 상세 |
| PATCH | `/api/v1/meetings/{meeting_id}/participants/me/profile` | 내 프로필 수정 |
| POST | `/api/v1/meetings/{meeting_id}/leave` | 참가자 퇴장 |
| POST | `/api/v1/meetings/{meeting_id}/end` | HOST 회의 종료 및 세션 개인정보 삭제 |
| PATCH | `/api/v1/meetings/{meeting_id}/participants/me/voice-analysis` | F-03 음성 분석 ON/OFF |
| POST | `/api/v1/meetings/{meeting_id}/pre-speech` | F-02 한국어 문장을 상대방 프로필에 맞는 영어 표현으로 변환 |
| GET | `/api/v1/meetings/{meeting_id}/pre-speech/{request_id}` | 내 F-02 결과 조회 |
| POST | `/api/v1/meetings/{meeting_id}/pre-speech/{request_id}/regenerate` | F-02 재생성 |
| POST | `/api/v1/meetings/{meeting_id}/speech-feedback/analyze` | F-03 영어 발언의 오해·마찰 가능성 점검 |
| GET | `/api/v1/meetings/{meeting_id}/speech-feedback` | 내 F-03 피드백 목록 |
| PATCH | `/api/v1/meetings/{meeting_id}/speech-feedback/{feedback_id}` | 내 피드백 닫기 |

성공 단건은 `{"data": ...}`, 목록은 `{"data": [], "meta": {"count": ...}}`, 실패는 `{"error": {...}, "request_id": "uuid"}` 형식입니다. 퇴장과 종료 성공은 body 없는 `204 No Content`입니다.

## 테스트

Docker 테스트 DB를 사용하는 경우:

```powershell
docker compose --profile test up -d db_test
$env:TEST_DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5433/meeting_mvp_test'
$env:DATABASE_URL=$env:TEST_DATABASE_URL
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m alembic check
```

테스트는 전체 회의 수명주기, Daily 요청 계약, 토큰 격리, 공개 정보 제한, 프로필 수정, 이름 중복, HOST 권한, 종료 시 개인정보 삭제와 PostgreSQL `FOR UPDATE` 기반 동시 입장 정원 제한을 검증합니다.
