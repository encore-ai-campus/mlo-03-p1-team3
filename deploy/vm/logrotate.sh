#!/bin/bash
# 기존 API VM에도 앱 재시작 없이 로테이션 설정만 적용할 수 있다.
source "$(dirname "$0")/common.sh"
require_root
check_ubuntu_2404

id podobank >/dev/null 2>&1 || die "API 설치로 podobank 계정을 먼저 만드세요."
apt_install logrotate
install -d -m 0750 -o podobank -g podobank /var/log/podobank
install -d -m 0755 /var/lib/logrotate

log "로그 교체 설정 검증·설치"
# 검증에 실패하면 현재 설정과 타이머는 건드리지 않는다.
/usr/sbin/logrotate --debug --state /dev/null "$VM_DIR/podobank-logrotate.conf"
install -m 0644 "$VM_DIR/podobank-logrotate.conf" /etc/logrotate-podobank.conf
install -m 0644 "$VM_DIR/podobank-logrotate.service" /etc/systemd/system/podobank-logrotate.service
install -m 0644 "$VM_DIR/podobank-logrotate.timer" /etc/systemd/system/podobank-logrotate.timer
systemctl daemon-reload
systemctl enable --now podobank-logrotate.timer
systemctl restart podobank-logrotate.timer
systemctl is-active --quiet podobank-logrotate.timer
log "로그 교체 조건을 매시간 확인합니다 (하루 1회 또는 100MB 초과, 최근 14개 보관)."
