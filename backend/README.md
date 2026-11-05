# 백엔드 개발 실행

전체 설명(아키텍처, ERD, API 명세서)은 루트 `README.md`에 있습니다. 이 파일은 팀원이 직접 띄워 볼 때 쓰는 명령만 적습니다. Docker는 쓰지 않습니다.

## 0. 준비

- Python 3.14, MariaDB 11.4, MongoDB 7, Nginx, HAProxy를 설치합니다.
- MariaDB에 DB와 계정을 만듭니다.

```sql
CREATE DATABASE podobank CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'podobank'@'%' IDENTIFIED BY 'change-me';
GRANT ALL ON podobank.* TO 'podobank'@'%';
```

```bash
cd backend
python3.14 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # 처음 한 번. 비밀번호와 KAKAO_* 값을 채웁니다
set -a; source .env; set +a # 셸에 환경 변수를 불러옵니다
```

## 1. 테이블 만들기

```bash
.venv/bin/python -m app.db.migrate
```

## 2. FastAPI 2대 띄우기

같은 코드, 같은 DB를 쓰고 포트·서버 이름·이벤트 로그 파일만 다릅니다.

```bash
INSTANCE_NAME=api-1 EVENT_LOG_PATH=./var/log/api-1.log \
  .venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001
INSTANCE_NAME=api-2 EVENT_LOG_PATH=./var/log/api-2.log \
  .venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8002
```

| 구성 | 하는 일 | 설정 |
|---|---|---|
| Nginx | 화면과 `/api/`를 한 주소로 묶음. `/api/`는 HAProxy로 넘김 | `deploy/nginx.conf` |
| HAProxy (8000) | `/api/` 요청을 api-1(8001), api-2(8002)에 번갈아 보냄. 2초마다 `/api/v1/health`로 상태 확인, 죽은 서버는 뺌 | `deploy/haproxy.cfg` |
| api-1, api-2 | FastAPI 2대. 커밋 뒤 이벤트를 MongoDB와 자기 파일(`api-1.log`, `api-2.log`)에 씀. 이벤트의 `instance` 칸에 서버 이름이 들어감 | 환경 변수 |

- 확인: `curl http://127.0.0.1:8001/api/v1/health` → `{"mariadb":"ok","mongodb":"ok"}`
- FastAPI를 다른 서버에 두면 `deploy/haproxy.cfg`의 `server` 두 줄을 그 서버 주소로 바꿉니다.
- 대시보드(Alloy·Loki·Prometheus·Grafana)는 들어 있지 않습니다. 붙일 때 `api-1.log`, `api-2.log`를 모두 읽으면 됩니다(한 줄에 이벤트 JSON 1개).

## 3. 직원 계정 만들기

```bash
.venv/bin/python -m app.db.migrate --seed-employee 01000000000 '직원비밀번호'
```

## 4. 배치 (지금은 필요할 때 직접 실행)

배치는 한 곳(api-1 쪽)에서만 돌립니다.

| 배치 | 명령 |
|---|---|
| 상환 (기준일까지 기한 된 회차, 연체 재시도) | `.venv/bin/python -m app.jobs.repayments --as-of-date 2027-01-03` |
| 일 마감 대사 | `.venv/bin/python -m app.jobs.reconcile` |

## 5. 테스트

테스트는 실제 MariaDB·MongoDB를 씁니다. 테스트가 테이블을 비우므로 **테스트 전용 DB**를 따로 만듭니다.

```sql
CREATE DATABASE podobank_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

```bash
export TEST_MARIADB_URL='mysql+pymysql://root:비밀번호@127.0.0.1:3306/podobank_test'  # 기본값: root:test@127.0.0.1:3306
export TEST_MONGODB_URL='mongodb://127.0.0.1:27017'                                  # MongoDB DB 이름은 podobank_test
.venv/bin/pytest tests
.venv/bin/ruff check app tests
```
