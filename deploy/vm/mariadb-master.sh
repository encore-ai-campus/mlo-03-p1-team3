#!/bin/bash
# MariaDB 마스터 VM: 설치 → 외부 접속·복제 설정 → podobank DB·계정, 복제 계정 생성.
# 사용: sudo bash deploy/vm/mariadb-master.sh
source "$(dirname "$0")/common.sh"
require_root
check_ubuntu_2404
load_env MARIADB_PASSWORD MARIADB_REPL_PASSWORD MARIADB_REPLICA_IP API1_IP API2_IP
check_password MARIADB_PASSWORD
check_password MARIADB_REPL_PASSWORD

install_mariadb

log "마스터 설정 (외부 접속, 복제 로그)"
cat > /etc/mysql/mariadb.conf.d/60-podobank.cnf <<'EOF'
[mariadb]
bind-address = 0.0.0.0
server_id = 1
log_bin = mysql-bin
binlog_format = ROW
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
EOF
systemctl enable mariadb
systemctl restart mariadb

log "DB·계정 생성 (api VM 2대만 접속 허용, 복제 계정은 슬레이브만)"
mariadb <<SQL
CREATE DATABASE IF NOT EXISTS podobank CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'podobank'@'${API1_IP}' IDENTIFIED BY '${MARIADB_PASSWORD}';
CREATE USER IF NOT EXISTS 'podobank'@'${API2_IP}' IDENTIFIED BY '${MARIADB_PASSWORD}';
ALTER USER 'podobank'@'${API1_IP}' IDENTIFIED BY '${MARIADB_PASSWORD}';
ALTER USER 'podobank'@'${API2_IP}' IDENTIFIED BY '${MARIADB_PASSWORD}';
GRANT ALL PRIVILEGES ON podobank.* TO 'podobank'@'${API1_IP}';
GRANT ALL PRIVILEGES ON podobank.* TO 'podobank'@'${API2_IP}';
CREATE USER IF NOT EXISTS 'repl'@'${MARIADB_REPLICA_IP}' IDENTIFIED BY '${MARIADB_REPL_PASSWORD}';
ALTER USER 'repl'@'${MARIADB_REPLICA_IP}' IDENTIFIED BY '${MARIADB_REPL_PASSWORD}';
GRANT REPLICATION SLAVE ON *.* TO 'repl'@'${MARIADB_REPLICA_IP}';
FLUSH PRIVILEGES;
SQL

log "확인"
mariadb -N -e "SELECT @@server_id, @@log_bin, @@bind_address, VERSION();"
log "완료. 테이블은 api-1에서 migrate로 만듭니다."
