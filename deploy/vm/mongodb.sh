#!/bin/bash
# MongoDB VM: 공식 저장소에서 설치 → 외부 접속 허용 → 시작. 컬렉션·인덱스는 FastAPI가 켜질 때 만든다.
# 사용: sudo bash deploy/vm/mongodb.sh
source "$(dirname "$0")/common.sh"
require_root
check_ubuntu_2404
load_env MONGODB_VERSION

log "MongoDB ${MONGODB_VERSION} 설치"
apt-get update -q
apt_install curl ca-certificates gnupg
curl -fsSL "https://pgp.mongodb.com/server-${MONGODB_VERSION}.asc" \
  | gpg --dearmor --yes -o "/usr/share/keyrings/mongodb-server-${MONGODB_VERSION}.gpg"
echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-${MONGODB_VERSION}.gpg ] https://repo.mongodb.org/apt/ubuntu noble/mongodb-org/${MONGODB_VERSION} multiverse" \
  > "/etc/apt/sources.list.d/mongodb-org-${MONGODB_VERSION}.list"
apt-get update -q
apt_install mongodb-org

log "외부 접속 허용 (bindIp)"
sed -i 's/^\(\s*bindIp:\).*/\1 0.0.0.0/' /etc/mongod.conf
grep -q "bindIp: 0.0.0.0" /etc/mongod.conf || die "/etc/mongod.conf의 bindIp를 바꾸지 못했습니다."
systemctl enable mongod
systemctl restart mongod

for _ in $(seq 1 20); do
  mongosh --quiet --eval 'db.runCommand({ping: 1}).ok' 2>/dev/null | grep -q 1 && break
  sleep 1
done
mongosh --quiet --eval 'db.runCommand({ping: 1}).ok' | grep -q 1 || die "MongoDB가 응답하지 않습니다."
log "완료. 인증 없이 열려 있으니 VM 네트워크 밖으로는 27017을 열지 마세요."
