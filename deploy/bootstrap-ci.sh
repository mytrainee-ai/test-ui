#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 || $# -ne 1 || ! -f $1 ]]; then
  echo 'Run as root with the Actions public key file as the only argument' >&2
  exit 2
fi

if ! id mathdeploy >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash --gid mathpage mathdeploy
fi

install -d -m 700 -o mathdeploy -g mathpage /home/mathdeploy/.ssh
printf 'restrict %s\n' "$(cat "$1")" > /home/mathdeploy/.ssh/authorized_keys
chown mathdeploy:mathpage /home/mathdeploy/.ssh/authorized_keys
chmod 600 /home/mathdeploy/.ssh/authorized_keys

install -d -m 2750 -o mathdeploy -g mathpage /opt/math-page-ci
install -d -m 2750 -o mathdeploy -g mathpage /opt/math-page-ci/releases

install -m 755 -o root -g root /tmp/math-page-ci-deploy.sh /usr/local/bin/math-page-deploy
install -m 755 -o root -g root /tmp/math-page-activate.sh /usr/local/sbin/math-page-activate
install -m 755 -o root -g root /tmp/math-page-rollback.sh /usr/local/sbin/math-page-rollback

cat > /etc/sudoers.d/math-page-deploy <<'EOF'
Cmnd_Alias MATH_PAGE_DEPLOY = /usr/local/sbin/math-page-activate *, /usr/local/sbin/math-page-rollback
mathdeploy ALL=(root) NOPASSWD: MATH_PAGE_DEPLOY
EOF
chmod 440 /etc/sudoers.d/math-page-deploy
visudo -cf /etc/sudoers.d/math-page-deploy
