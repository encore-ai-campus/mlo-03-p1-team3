#!/bin/bash
# Nginx VM: 설치 → deploy/nginx.conf의 HAProxy 주소를 VM IP로 바꿔 넣기 → 문법 확인 → 재시작.
# 프론트 빌드 결과(dist)는 /var/www/podobank 에 넣는다.
# 사용: sudo bash deploy/vm/nginx.sh
source "$(dirname "$0")/common.sh"
require_root
check_ubuntu_2404
load_env HAPROXY_IP

WEB_ROOT=/var/www/podobank

log "Nginx 설치"
apt-get update -q
apt_install nginx

log "설정 넣기 (/api → HAProxy ${HAPROXY_IP}:8000, 화면 → ${WEB_ROOT})"
install -d -m 0755 "$WEB_ROOT"
sed -e "s#proxy_pass http://127.0.0.1:8000;.*#proxy_pass http://${HAPROXY_IP}:8000;#" \
    -e "s#root /usr/share/nginx/html;.*#root ${WEB_ROOT};#" \
    "$DEPLOY_DIR/nginx.conf" > /etc/nginx/conf.d/podobank.conf
grep -q "proxy_pass http://${HAPROXY_IP}:8000;" /etc/nginx/conf.d/podobank.conf || die "proxy_pass를 바꾸지 못했습니다."
rm -f /etc/nginx/sites-enabled/default   # 기본 화면이 80번을 차지하지 않게
nginx -t

systemctl enable nginx
systemctl restart nginx
[ -f "$WEB_ROOT/index.html" ] || log "아직 화면 파일이 없습니다. 프론트 dist 내용을 ${WEB_ROOT}에 넣으세요."
log "완료. 확인: curl http://127.0.0.1/api/v1/health"
