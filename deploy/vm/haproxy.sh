#!/bin/bash
# HAProxy VM: 설치 → deploy/haproxy.cfg의 api 주소를 VM IP로 바꿔 넣기 → 문법 확인 → 재시작.
# 사용: sudo bash deploy/vm/haproxy.sh
source "$(dirname "$0")/common.sh"
require_root
check_ubuntu_2404
load_env API1_IP API2_IP

log "HAProxy 설치"
apt-get update -q
apt_install haproxy

log "설정 넣기 (api-1 ${API1_IP}:8000, api-2 ${API2_IP}:8000)"
render_haproxy() {  # 원본의 server 줄(한 컴퓨터용)을 VM IP 줄로 바꾼다
  awk -v a1="$API1_IP" -v a2="$API2_IP" '
    /^[[:space:]]*#.*한 대/ { next }
    /^[[:space:]]*server api-1 / { print "    server api-1 " a1 ":8000 check"; next }
    /^[[:space:]]*server api-2 / { print "    server api-2 " a2 ":8000 check"; next }
    { print }
  ' "$DEPLOY_DIR/haproxy.cfg"
}
render_haproxy > /etc/haproxy/haproxy.cfg
haproxy -c -f /etc/haproxy/haproxy.cfg

systemctl enable haproxy
systemctl restart haproxy
log "완료. 상태: curl http://127.0.0.1:8000/api/v1/health"
