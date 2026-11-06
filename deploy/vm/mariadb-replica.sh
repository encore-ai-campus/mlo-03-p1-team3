#!/bin/bash
# MariaDB 슬레이브 VM: 설치 → 읽기 전용 → 마스터 복제 시작. 마스터를 먼저 설치한 뒤 실행한다.
# 평소에는 대기용이고, 마스터가 죽으면 승격한다(read_only 끄고 api의 MARIADB_URL을 이 IP로).
# 사용: sudo bash deploy/vm/mariadb-replica.sh
source "$(dirname "$0")/common.sh"
require_root
check_ubuntu_2404
load_env MARIADB_MASTER_IP MARIADB_REPL_PASSWORD
check_password MARIADB_REPL_PASSWORD

install_mariadb

log "슬레이브 설정 (읽기 전용)"
cat > /etc/mysql/mariadb.conf.d/60-podobank.cnf <<'EOF'
[mariadb]
bind-address = 0.0.0.0
default_time_zone = "+09:00"
server_id = 2
log_bin = mysql-bin
relay_log = relay-bin
read_only = ON
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
EOF
systemctl enable mariadb
systemctl restart mariadb

log "마스터(${MARIADB_MASTER_IP}) 복제 시작"
mariadb <<SQL
STOP SLAVE;
CHANGE MASTER TO
  MASTER_HOST='${MARIADB_MASTER_IP}',
  MASTER_USER='repl',
  MASTER_PASSWORD='${MARIADB_REPL_PASSWORD}',
  MASTER_USE_GTID=slave_pos;
START SLAVE;
SQL

sleep 3
status="$(mariadb -e 'SHOW SLAVE STATUS\G')"
echo "$status" | grep -E "Slave_IO_Running|Slave_SQL_Running|Last_IO_Error|Last_SQL_Error|Seconds_Behind_Master"
echo "$status" | grep -q "Slave_IO_Running: Yes" || die "복제가 시작되지 않았습니다. 위 오류를 확인하세요."
log "완료."
