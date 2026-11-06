#!/bin/bash
# FastAPI VM(api-1, api-2 공용): Python 3.14 → 코드 → 패키지 → 환경 변수 → 서비스 등록·시작.
# api-1에서만 MIGRATE=1로 테이블을 만든다(DB VM이 먼저 떠 있어야 함).
# 사용: sudo INSTANCE_NAME=api-1 MIGRATE=1 bash deploy/vm/api.sh
#       sudo INSTANCE_NAME=api-2 bash deploy/vm/api.sh
source "$(dirname "$0")/common.sh"
require_root
check_ubuntu_2404
load_env REPO_URL REPO_REF MARIADB_MASTER_IP MONGODB_IP MARIADB_PASSWORD COOKIE_SECURE
check_password MARIADB_PASSWORD
INSTANCE_NAME="${INSTANCE_NAME:-}"
[[ "$INSTANCE_NAME" =~ ^api-[0-9]+$ ]] || die "INSTANCE_NAME=api-1 처럼 서버 이름을 주세요."

APP_DIR=/opt/podobank
LOG_DIR=/var/log/podobank
ENV_FILE=/etc/podobank/api.env

log "Python 3.14 설치 (deadsnakes PPA)"
apt-get update -q
apt_install software-properties-common git curl
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update -q
apt_install python3.14 python3.14-venv

log "실행 계정·폴더"
id podobank >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin podobank
install -d -o podobank -g podobank "$LOG_DIR"
install -d -m 0750 -o root -g podobank /etc/podobank

log "로그 로테이션 설치"
bash "$VM_DIR/logrotate.sh"

log "코드 받기 (${REPO_URL} ${REPO_REF})"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch -q origin "$REPO_REF"
  git -C "$APP_DIR" checkout -q -B "$REPO_REF" "origin/$REPO_REF"
else
  git clone -q --branch "$REPO_REF" "$REPO_URL" "$APP_DIR"
fi
# Ansible may supply the current workspace backend without committing it to Git.
if [ -n "${BACKEND_SOURCE_DIR:-}" ]; then
  [ -f "$BACKEND_SOURCE_DIR/app/main.py" ] || die "BACKEND_SOURCE_DIR에 백엔드 소스가 없습니다."
  cp -a "$BACKEND_SOURCE_DIR/." "$APP_DIR/backend/"
fi
chown -R podobank:podobank "$APP_DIR"

log "패키지 설치"
sudo -u podobank python3.14 -m venv "$APP_DIR/backend/.venv"
sudo -u podobank "$APP_DIR/backend/.venv/bin/pip" install -q --upgrade pip
sudo -u podobank "$APP_DIR/backend/.venv/bin/pip" install -q -r "$APP_DIR/backend/requirements.txt"

log "환경 변수 (${ENV_FILE}, 값은 출력하지 않음)"
umask 027
cat > "$ENV_FILE" <<EOF
MARIADB_URL=mysql+pymysql://podobank:${MARIADB_PASSWORD}@${MARIADB_MASTER_IP}:3306/podobank
MONGODB_URL=mongodb://podobank:${MARIADB_PASSWORD}@${MONGODB_IP}:27017/podobank?authSource=podobank
MONGODB_DB=podobank
INSTANCE_NAME=${INSTANCE_NAME}
EVENT_LOG_PATH=${LOG_DIR}/${INSTANCE_NAME}.events.log
APP_LOG_PATH=${LOG_DIR}/${INSTANCE_NAME}.app.log
COOKIE_SECURE=${COOKIE_SECURE}
KAKAO_CLIENT_ID=${KAKAO_CLIENT_ID:-}
KAKAO_CLIENT_SECRET=${KAKAO_CLIENT_SECRET:-}
KAKAO_REDIRECT_URI=${KAKAO_REDIRECT_URI:-}
EOF
chown root:podobank "$ENV_FILE"
chmod 0640 "$ENV_FILE"

run_app() {  # api.env를 넣고 앱 명령을 podobank 계정으로 실행
  sudo -u podobank bash -c "set -a; . '$ENV_FILE'; set +a; cd '$APP_DIR/backend' && .venv/bin/python $*"
}

if [ "${MIGRATE:-0}" = "1" ]; then
  log "테이블 만들기 (migrate)"
  run_app "-m app.db.migrate"
  if [ -n "${EMPLOYEE_PHONE:-}" ] && [ -n "${EMPLOYEE_PASSWORD:-}" ]; then
    log "직원 계정 만들기"
    run_app "-m app.db.migrate --seed-employee '${EMPLOYEE_PHONE}' '${EMPLOYEE_PASSWORD}'" >/dev/null
  fi
fi

log "서비스 등록·시작 (포트 8000)"
install -m 0644 "$VM_DIR/podobank-api.service" /etc/systemd/system/podobank-api.service
systemctl daemon-reload
systemctl enable podobank-api
systemctl restart podobank-api

for _ in $(seq 1 30); do
  curl -fsS http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS http://127.0.0.1:8000/api/v1/health || die "헬스 체크 실패. journalctl -u podobank-api 로 확인하세요."
echo
log "완료. 이벤트 로그: ${LOG_DIR}/${INSTANCE_NAME}.events.log / 애플리케이션 로그: ${LOG_DIR}/${INSTANCE_NAME}.app.log"
