# AWS 단일 EC2 Docker 배포 가이드

## 1. 배포 구조

MVP는 AWS EC2 한 대에서 세 컨테이너를 실행한다.

```text
CloudFront 기본 HTTPS 주소
  -> EC2:80
     -> frontend (React 정적 파일 + Nginx)
        -> /api/* -> backend:8000 (FastAPI)
                       -> db:5432 (PostgreSQL)
```

- 사용자에게 공개되는 주소는 `https://dxxxxxxxx.cloudfront.net`이다.
- EC2에는 `80`만 공개하고 `8000`, `5432`는 Docker 내부 네트워크에서만 사용한다.
- Daily 영상·음성은 브라우저와 Daily 사이에서 직접 전달되므로 EC2를 통과하지 않는다.
- PostgreSQL 데이터는 `global-meeting_postgres_data` Docker named volume에 보존된다.

## 2. 서버 권장 사양

- Region: `ap-northeast-2` (서울)
- OS: Ubuntu 24.04 LTS x86_64
- Instance: 2 vCPU / 2 GiB (`t3.small`)
- EBS: gp3 15 GiB
- 고정 주소: Elastic IP 1개

현재 단일 서버 구성은 `t3.small`에 맞춰 PostgreSQL 512 MiB, FastAPI 768 MiB,
Nginx 128 MiB로 메모리 한도를 설정하고 Uvicorn worker를 1개만 사용한다. 서버에는
메모리 부족에 대비해 2 GiB swap을 설정한다.

두 저장소는 반드시 같은 상위 디렉터리 아래에 둔다.

```text
~/likelion14-team5/
  backend/
  frontend/
```

`backend/docker-compose.production.yml`이 `../frontend`를 빌드 컨텍스트로 사용하기 때문이다.

## 3. 보안 그룹

초기 점검 중에는 다음 규칙만 사용한다.

| 포트 | 소스 | 용도 |
|---|---|---|
| 22 | 운영자 본인 공인 IP `/32` | SSH |
| 80 | 운영자 본인 공인 IP `/32` | CloudFront 연결 전 HTTP 점검 |

CloudFront 연결 후 `80`의 소스를 AWS 관리 prefix list
`com.amazonaws.global.cloudfront.origin-facing`으로 교체한다. `8000`, `5432`는 인바운드
규칙을 만들지 않는다. EC2의 `443`도 CloudFront가 HTTPS를 종료하므로 필요하지 않다.

## 4. 운영 환경변수

EC2의 `backend/.env`를 직접 작성한다. 이 파일은 Git과 Docker 이미지에 포함되지 않는다.

```env
DATABASE_URL=postgresql+psycopg://meeting_app:URL_SAFE_PASSWORD@db:5432/meeting_mvp
POSTGRES_DB=meeting_mvp
POSTGRES_USER=meeting_app
POSTGRES_PASSWORD=URL_SAFE_PASSWORD
HTTP_PORT=80
IMAGE_TAG=first-deploy

FRONTEND_ORIGIN=http://EC2_PUBLIC_DNS
PUBLIC_APP_URL=http://EC2_PUBLIC_DNS

DAILY_API_KEY=실제_Daily_서버키
DAILY_API_BASE_URL=https://api.daily.co/v1
DAILY_DOMAIN=실제팀.daily.co
DAILY_ROOM_TTL_MINUTES=180
DAILY_TOKEN_TTL_MINUTES=120
DAILY_REQUEST_TIMEOUT_SECONDS=5

OPENAI_API_KEY=실제_OpenAI_서버키
OPENAI_MODEL=gpt-4o-mini
OPENAI_REQUEST_TIMEOUT_SECONDS=8
OPENAI_MAX_RETRIES=3
SQL_ECHO=false
```

`POSTGRES_PASSWORD`는 Compose가 DB URL에 삽입하므로 영문자, 숫자, `_`, `-`로 만든 32자
이상의 값을 권장한다.

```bash
openssl rand -hex 32
```

`DATABASE_URL`과 `POSTGRES_PASSWORD`의 비밀번호는 동일해야 한다. Compose 실행 시 컨테이너의
`DATABASE_URL`은 DB 서비스 이름 `db`를 사용하도록 덮어쓴다.

## 5. 최초 배포와 빈 DB 초기화

다음 명령은 `backend` 디렉터리에서 실행한다.

```bash
docker compose -f docker-compose.production.yml config --quiet
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d db
docker compose -f docker-compose.production.yml run --rm backend alembic upgrade head
docker compose -f docker-compose.production.yml up -d backend frontend
```

최초 `up -d db`에서 빈 PostgreSQL 데이터 볼륨이 생성되고, Alembic 명령이 최신 스키마를
적용한다. 웹 컨테이너 시작 명령에는 마이그레이션을 넣지 않는다.

상태를 확인한다.

```bash
docker compose -f docker-compose.production.yml ps
docker compose -f docker-compose.production.yml logs --tail 100 backend frontend db
curl http://localhost/health
curl http://EC2_PUBLIC_DNS/health
```

세 서비스가 모두 `healthy`이고 `/health`가 `{"status":"ok"}`를 반환해야 한다.

## 6. CloudFront 기본 HTTPS 연결

CloudFront Distribution의 origin을 EC2의 **공인 DNS 이름**으로 지정한다. IP 주소를 origin
항목에 직접 입력하지 않는다.

Origin 설정:

- Origin domain: EC2 Public IPv4 DNS
- Protocol: HTTP only
- HTTP port: 80

기본 behavior 하나로 정적 페이지와 API를 함께 전달한다.

- Path: `Default (*)`
- Viewer protocol policy: Redirect HTTP to HTTPS
- Allowed methods: GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE
- Cache policy: 배포 초기에는 `CachingDisabled`
- Origin request policy: `AllViewerExceptHostHeader`

인증서는 `Default CloudFront Certificate (*.cloudfront.net)`를 사용한다. Distribution 배포가
완료되면 `https://dxxxxxxxx.cloudfront.net` 형식의 주소가 발급된다.

발급된 주소로 `backend/.env`를 수정한다.

```env
FRONTEND_ORIGIN=https://dxxxxxxxx.cloudfront.net
PUBLIC_APP_URL=https://dxxxxxxxx.cloudfront.net
```

백엔드 환경변수만 다시 적용한다.

```bash
docker compose -f docker-compose.production.yml up -d --force-recreate backend
curl https://dxxxxxxxx.cloudfront.net/health
```

프론트 API 주소는 빌드 시 `/api/v1` 상대경로로 고정되므로 CloudFront 주소가 바뀌어도 다시
빌드할 필요가 없다.

## 7. GitHub main 자동 배포

백엔드와 프론트엔드 저장소는 모두 `main` push에서 각자 CI를 실행한다. EC2는 systemd timer로
5분마다 두 공개 저장소의 최신 `main`과 GitHub Actions 결과를 조회한다. 두 최신 commit의 CI가
모두 성공한 경우에만 두 저장소를 함께 갱신하고 배포한다.

이 pull 기반 방식은 GitHub-hosted runner의 가변 IP 때문에 EC2 SSH를 인터넷 전체에 공개하는
문제를 피한다. GitHub에 EC2 개인키나 AWS credential을 저장할 필요도 없다. SSH 22번은 계속
운영자 IP `/32`만 허용한다.

EC2 배포 경로:

```text
/opt/global-meeting/
  backend/
  frontend/
```

두 디렉터리는 각각 GitHub 저장소의 `main` clone이어야 한다. 운영 `.env`는
`/opt/global-meeting/backend/.env`에만 두고 Git에 추가하지 않는다.

배포 명령과 CI poller, systemd unit을 설치한다.

```bash
sudo install -o root -g root -m 755 \
  /opt/global-meeting/backend/scripts/deploy-production.sh \
  /usr/local/bin/deploy-global-meeting
sudo install -o root -g root -m 755 \
  /opt/global-meeting/backend/scripts/poll-production.py \
  /usr/local/bin/poll-global-meeting
sudo install -o root -g root -m 644 \
  /opt/global-meeting/backend/deploy/systemd/global-meeting-deploy-poller.service \
  /etc/systemd/system/global-meeting-deploy-poller.service
sudo install -o root -g root -m 644 \
  /opt/global-meeting/backend/deploy/systemd/global-meeting-deploy-poller.timer \
  /etc/systemd/system/global-meeting-deploy-poller.timer
sudo systemctl daemon-reload
sudo systemctl enable --now global-meeting-deploy-poller.timer
```

OpenAI, Daily, PostgreSQL 비밀값은 GitHub에 등록하지 않고 EC2의 `.env`에만 보관한다. GitHub
Actions 상태 조회는 공개 저장소 API를 인증 없이 사용하며, 5분 주기라 비인증 rate limit 안에서
동작한다.

배포 스크립트는 다음 순서로 동작한다.

1. poller가 두 저장소 최신 `main` SHA와 해당 push의 CI 성공 여부를 확인한다.
2. 두 CI가 모두 성공하면 배포 스크립트가 tracked file 상태를 검사한다.
3. 두 저장소를 `git pull --ff-only origin main`으로 갱신한다.
4. 두 commit SHA를 조합한 고유 Docker image tag로 이미지를 빌드한다.
5. PostgreSQL을 실행하고 Alembic migration을 적용한다.
6. 백엔드와 프론트엔드를 교체하고 `/health`를 검사한다.
7. 성공한 두 SHA를 `.last-successful-deployment`에 기록한다. 실패하면 다음 timer에서 재시도한다.

상태와 로그를 확인한다.

```bash
systemctl status global-meeting-deploy-poller.timer
journalctl -u global-meeting-deploy-poller.service -n 100 --no-pager
```

## 8. 수동 업데이트와 롤백

배포마다 `IMAGE_TAG`를 고유하게 변경한다.

```env
IMAGE_TAG=20260820-1
```

```bash
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml run --rm backend alembic upgrade head
docker compose -f docker-compose.production.yml up -d
```

문제가 생기면 `.env`의 `IMAGE_TAG`를 이전 태그로 바꾸고 다시 `up -d`한다. DB 마이그레이션
다운그레이드는 데이터 손실 위험이 있으므로 백업 없이 실행하지 않는다.

## 9. PostgreSQL 백업과 초기화

백업:

```bash
mkdir -p backups
docker compose -f docker-compose.production.yml exec -T db \
  pg_dump -U meeting_app -d meeting_mvp -Fc > backups/meeting_mvp.dump
```

일반 종료는 볼륨을 보존한다.

```bash
docker compose -f docker-compose.production.yml down
```

다음 명령은 컨테이너와 PostgreSQL 볼륨을 모두 삭제한다. DB를 완전히 초기화하기로 명시적으로
결정한 경우에만 사용한다.

```bash
docker compose -f docker-compose.production.yml down --volumes
```

이후 5절의 `up -d db`와 Alembic 명령을 다시 실행하면 빈 운영 DB가 만들어진다.

## 10. 로컬 검증

로컬 전용 값은 Git에서 제외된 `backend/.env.docker.local`을 사용한다. 현재 PC에서는 다른
프로젝트가 `80`을 사용하므로 `8088`로 설정되어 있다.

```powershell
cd D:\Code\VScode-code\likelion14-team5\backend
docker compose --env-file .env.docker.local -f docker-compose.production.yml build
docker compose --env-file .env.docker.local -f docker-compose.production.yml up -d db
docker compose --env-file .env.docker.local -f docker-compose.production.yml run --rm backend alembic upgrade head
docker compose --env-file .env.docker.local -f docker-compose.production.yml up -d
```

접속 주소는 `http://localhost:8088`이다.
