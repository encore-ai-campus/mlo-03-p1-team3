#!/bin/bash
# Nginx VM: 설치 → deploy/nginx.conf의 HAProxy 주소를 VM IP로 바꿔 넣기 → 문법 확인 → 재시작.
# 프론트 빌드 결과(dist)는 /var/www/podobank 에 넣는다.
# 사용: sudo bash deploy/vm/nginx.sh
source "$(dirname "$0")/common.sh"
require_root
check_ubuntu_2404
load_env HAPROXY_IP

WEB_ROOT=/var/www/podobank
NGINX_TLS_ENABLED="${NGINX_TLS_ENABLED:-auto}"
NGINX_SERVER_NAME="${NGINX_SERVER_NAME:-www.podobank.kro.kr}"
NGINX_TLS_DIRECTORY="${NGINX_TLS_DIRECTORY:-/etc/nginx/ssl/podobank}"
[[ "$NGINX_TLS_ENABLED" =~ ^(auto|true|false)$ ]] || die "NGINX_TLS_ENABLED must be auto, true or false."
[[ "$NGINX_SERVER_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*[A-Za-z0-9]$ ]] || die "Invalid NGINX_SERVER_NAME."
[[ "$NGINX_TLS_DIRECTORY" =~ ^/[A-Za-z0-9_./-]+$ ]] || die "Invalid NGINX_TLS_DIRECTORY."
TLS_ACTIVE=false
if [ "$NGINX_TLS_ENABLED" = true ] || { [ "$NGINX_TLS_ENABLED" = auto ] && [ -d "$NGINX_TLS_DIRECTORY" ]; }; then
  for file in certificate.crt ca_bundle.crt private.key; do
    [ -s "$NGINX_TLS_DIRECTORY/$file" ] || die "TLS file missing: $file"
  done
  openssl verify -CApath /etc/ssl/certs -untrusted "$NGINX_TLS_DIRECTORY/ca_bundle.crt" \
    -verify_hostname "$NGINX_SERVER_NAME" "$NGINX_TLS_DIRECTORY/certificate.crt" >/dev/null \
    || die "TLS certificate chain, validity or hostname verification failed."
  cert_public=$(openssl x509 -in "$NGINX_TLS_DIRECTORY/certificate.crt" -pubkey -noout) \
    || die "Cannot read certificate public key."
  key_public=$(openssl pkey -in "$NGINX_TLS_DIRECTORY/private.key" -passin pass: -pubout 2>/dev/null) \
    || die "Cannot read TLS private key."
  [ "$cert_public" = "$key_public" ] || die "Certificate and private key do not match."
  cat "$NGINX_TLS_DIRECTORY/certificate.crt" "$NGINX_TLS_DIRECTORY/ca_bundle.crt" > "$NGINX_TLS_DIRECTORY/fullchain.pem"
  chown root:root "$NGINX_TLS_DIRECTORY" "$NGINX_TLS_DIRECTORY/private.key"
  chmod 0700 "$NGINX_TLS_DIRECTORY"
  chmod 0600 "$NGINX_TLS_DIRECTORY/private.key"
  TLS_ACTIVE=true
fi

log "Nginx 설치"
apt-get update -q
apt_install nginx

config_candidate=$(mktemp /etc/nginx/conf.d/.podobank.conf.XXXXXX)
previous_config=$(mktemp)
had_previous=false
if [ -f /etc/nginx/conf.d/podobank.conf ]; then
  cp /etc/nginx/conf.d/podobank.conf "$previous_config"
  had_previous=true
fi
trap 'rm -f "$config_candidate" "$previous_config"' EXIT

log "설정 넣기 (/api → HAProxy ${HAPROXY_IP}:8000, 화면 → ${WEB_ROOT})"
install -d -m 0755 "$WEB_ROOT"
sed -e "s#proxy_pass http://127.0.0.1:8000;.*#proxy_pass http://${HAPROXY_IP}:8000;#" \
    -e "s#root /usr/share/nginx/html;.*#root ${WEB_ROOT};#" \
    "$DEPLOY_DIR/nginx.conf" > "$config_candidate"
if [ "$TLS_ACTIVE" = true ]; then
  # Retain the LAN HTTP route and add a domain redirect plus the same routes over TLS.
  cat >> "$config_candidate" <<EOF

server {
    listen 80;
    server_name ${NGINX_SERVER_NAME};
    return 308 https://${NGINX_SERVER_NAME}\$request_uri;
}
EOF
  sed -e 's/listen 80;/listen 443 ssl;/' \
      -e "s#server_name _;#server_name ${NGINX_SERVER_NAME};\\n    ssl_certificate ${NGINX_TLS_DIRECTORY}/fullchain.pem;\\n    ssl_certificate_key ${NGINX_TLS_DIRECTORY}/private.key;\\n    ssl_protocols TLSv1.2 TLSv1.3;\\n    proxy_cookie_flags ~ secure;#" \
      -e "s#proxy_pass http://127.0.0.1:8000;.*#proxy_pass http://${HAPROXY_IP}:8000;#" \
      -e "s#root /usr/share/nginx/html;.*#root ${WEB_ROOT};#" \
      "$DEPLOY_DIR/nginx.conf" >> "$config_candidate"
fi
grep -q "proxy_pass http://${HAPROXY_IP}:8000;" "$config_candidate" || die "proxy_pass를 바꾸지 못했습니다."
rm -f /etc/nginx/sites-enabled/default   # 기본 화면이 80번을 차지하지 않게
install -m 0644 "$config_candidate" /etc/nginx/conf.d/podobank.conf
if ! nginx -t; then
  if [ "$had_previous" = true ]; then
    install -m 0644 "$previous_config" /etc/nginx/conf.d/podobank.conf
  else
    rm -f /etc/nginx/conf.d/podobank.conf
  fi
  die "Nginx configuration validation failed; previous configuration restored."
fi

systemctl enable nginx
systemctl reload-or-restart nginx
[ -f "$WEB_ROOT/index.html" ] || log "아직 화면 파일이 없습니다. 프론트 dist 내용을 ${WEB_ROOT}에 넣으세요."
log "완료. 확인: curl http://127.0.0.1/api/v1/health"

printf 'HTTPS_ENABLED=%s\n' "$TLS_ACTIVE"
if [ "$TLS_ACTIVE" = true ]; then
  printf 'HTTPS_DOMAIN=%s\n' "$NGINX_SERVER_NAME"
fi
