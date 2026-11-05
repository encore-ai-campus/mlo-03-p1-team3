# 모든 VM 설치 스크립트가 불러 쓰는 공통 함수. 직접 실행하지 않는다.
set -euo pipefail

VM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$VM_DIR")"

log() { echo "[$(date +%H:%M:%S)] $*"; }
die() { echo "[오류] $*" >&2; exit 1; }

require_root() {
  [ "$(id -u)" -eq 0 ] || die "sudo로 실행하세요: sudo bash $0"
}

# vm.env를 읽고, 이 스크립트에 필요한 값이 비었는지 확인한다.
load_env() {
  local file="${VM_ENV:-$VM_DIR/vm.env}"
  [ -f "$file" ] || die "$file 이 없습니다. vm.env.example을 복사해서 채우세요."
  set -a
  # shellcheck disable=SC1090
  . "$file"
  set +a
  local name
  for name in "$@"; do
    [ -n "${!name:-}" ] || die "vm.env에 $name 값이 비었습니다."
  done
}

# SQL·URL에 그대로 넣으므로 비밀번호는 영문·숫자·_·- 만 허용한다.
check_password() {
  [[ "${!1}" =~ ^[A-Za-z0-9_-]+$ ]] || die "$1 에는 영문·숫자·_·- 만 쓸 수 있습니다."
}

apt_install() {
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q "$@"
}

check_ubuntu_2404() {
  . /etc/os-release
  [ "${ID:-}" = "ubuntu" ] && [ "${VERSION_ID:-}" = "24.04" ] || die "Ubuntu 24.04 기준 스크립트입니다 (지금: ${PRETTY_NAME:-알 수 없음})."
}

# MariaDB 11.4 공식 저장소에서 설치한다(테스트를 11.4로 돌렸다). 마스터·슬레이브 공용.
install_mariadb() {
  log "MariaDB 11.4 설치"
  apt-get update -q
  apt_install curl ca-certificates gnupg
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://mariadb.org/mariadb_release_signing_key.pgp -o /etc/apt/keyrings/mariadb-keyring.pgp
  echo "deb [signed-by=/etc/apt/keyrings/mariadb-keyring.pgp] https://deb.mariadb.org/11.4/ubuntu noble main" \
    > /etc/apt/sources.list.d/mariadb.list
  apt-get update -q
  apt_install mariadb-server mariadb-client
}
