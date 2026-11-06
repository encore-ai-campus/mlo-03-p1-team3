#!/bin/bash
# MongoDB VM: install, enable password authentication, and preserve data on reruns.
# The application user is limited to readWrite on the podobank database.
source "$(dirname "$0")/common.sh"
require_root
check_ubuntu_2404
load_env MONGODB_VERSION MARIADB_PASSWORD MONGODB_ADMIN_PASSWORD
check_password MARIADB_PASSWORD
check_password MONGODB_ADMIN_PASSWORD

log "MongoDB ${MONGODB_VERSION} 설치"
apt-get update -q
apt_install curl ca-certificates gnupg
curl -fsSL "https://pgp.mongodb.com/server-${MONGODB_VERSION}.asc" \
  | gpg --dearmor --yes -o "/usr/share/keyrings/mongodb-server-${MONGODB_VERSION}.gpg"
echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-${MONGODB_VERSION}.gpg ] https://repo.mongodb.org/apt/ubuntu noble/mongodb-org/${MONGODB_VERSION} multiverse" \
  > "/etc/apt/sources.list.d/mongodb-org-${MONGODB_VERSION}.list"
apt-get update -q
apt_install mongodb-org

MONGO_AUTH_ENABLED=false
if grep -qE '^security:[[:space:]]*$' /etc/mongod.conf \
  && grep -qE '^  authorization:[[:space:]]*enabled[[:space:]]*$' /etc/mongod.conf; then
  MONGO_AUTH_ENABLED=true
fi

MONGO_SETUP_FILE="$(mktemp /run/podobank-mongo-users.XXXXXX.js)"
chmod 0600 "$MONGO_SETUP_FILE"
trap 'rm -f "$MONGO_SETUP_FILE"' EXIT
cat > "$MONGO_SETUP_FILE" <<EOF
const admin = db.getSiblingDB("admin");
const adminName = "podobank-admin";
const adminPassword = "${MONGODB_ADMIN_PASSWORD}";
const appName = "podobank";
const appPassword = "${MARIADB_PASSWORD}";

if (process.env.PODOBANK_MONGO_AUTH_ENABLED === "true") {
  const auth = admin.auth(adminName, adminPassword);
  if (auth.ok !== 1) throw new Error("MongoDB deployment account authentication failed");
  admin.updateUser(adminName, {
    pwd: adminPassword,
    roles: [{ role: "userAdminAnyDatabase", db: "admin" }]
  });
} else {
  const existingAdmin = admin.getUser(adminName);
  if (existingAdmin) {
    admin.updateUser(adminName, {
      pwd: adminPassword,
      roles: [{ role: "userAdminAnyDatabase", db: "admin" }]
    });
  } else {
    admin.createUser({
      user: adminName,
      pwd: adminPassword,
      roles: [{ role: "userAdminAnyDatabase", db: "admin" }]
    });
  }
}

const appDb = db.getSiblingDB("podobank");
const existingApp = appDb.getUser(appName);
if (existingApp) {
  appDb.updateUser(appName, {
    pwd: appPassword,
    roles: [{ role: "readWrite", db: "podobank" }]
  });
} else {
  appDb.createUser({
    user: appName,
    pwd: appPassword,
    roles: [{ role: "readWrite", db: "podobank" }]
  });
}
if (appDb.runCommand({ ping: 1 }).ok !== 1) throw new Error("MongoDB ping failed");
EOF

log "MongoDB 사용자 설정 갱신 (비밀번호는 출력하지 않음)"
PODOBANK_MONGO_AUTH_ENABLED="$MONGO_AUTH_ENABLED" mongosh --quiet --file "$MONGO_SETUP_FILE" >/dev/null \
  || die "MongoDB 계정 설정에 실패했습니다. 인증 설정과 저장된 vm.env를 확인하세요."

log "외부 접속 주소 설정"
if grep -qE '^[[:space:]]*bindIp:' /etc/mongod.conf; then
  sed -i 's/^\([[:space:]]*bindIp:\).*/\1 0.0.0.0/' /etc/mongod.conf
else
  die "/etc/mongod.conf에서 bindIp 항목을 찾지 못했습니다."
fi

if grep -qE '^security:[[:space:]]*$' /etc/mongod.conf; then
  if grep -qE '^  authorization:' /etc/mongod.conf; then
    sed -i 's/^  authorization:.*/  authorization: enabled/' /etc/mongod.conf
  else
    sed -i '/^security:[[:space:]]*$/a\  authorization: enabled' /etc/mongod.conf
  fi
else
  printf '\nsecurity:\n  authorization: enabled\n' >> /etc/mongod.conf
fi

grep -qE '^  authorization:[[:space:]]*enabled[[:space:]]*$' /etc/mongod.conf \
  || die "/etc/mongod.conf에 MongoDB 인증 설정을 적용하지 못했습니다."
systemctl enable mongod
systemctl restart mongod

log "인증을 켠 상태에서 계정과 응답 확인"
for _ in $(seq 1 30); do
  if PODOBANK_MONGO_AUTH_ENABLED=true mongosh --quiet --file "$MONGO_SETUP_FILE" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
PODOBANK_MONGO_AUTH_ENABLED=true mongosh --quiet --file "$MONGO_SETUP_FILE" >/dev/null 2>&1 \
  || die "MongoDB 인증 확인에 실패했습니다."
log "완료. DB 데이터는 보존하고 podobank DB 사용자 설정만 갱신했습니다."
