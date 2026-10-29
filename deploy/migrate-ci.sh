#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 || $# -ne 1 || ! $1 =~ ^[0-9a-f]{40}$ ]]; then
  echo 'Run as root with the prepared commit SHA' >&2
  exit 2
fi

base=/opt/math-page-ci
release=$base/releases/$1
[[ -x $release/.venv/bin/python && -f $release/app.py ]]

app_unit=/etc/systemd/system/math-page-app.service
auth_unit=/etc/systemd/system/math-page-auth.service
cp -n "$app_unit" "$app_unit.pre-ci"
cp -n "$auth_unit" "$auth_unit.pre-ci"

restore_old() {
  cp "$app_unit.pre-ci" "$app_unit"
  cp "$auth_unit.pre-ci" "$auth_unit"
  systemctl daemon-reload
  systemctl restart math-page-auth math-page-app
}
trap restore_old ERR

ln -sfn "$release" "$base/current"
install -m 644 /tmp/math-page-app-ci.service "$app_unit"
install -m 644 /tmp/math-page-auth-ci.service "$auth_unit"
systemctl daemon-reload
systemctl restart math-page-auth math-page-app

healthy=false
for _ in {1..20}; do
  if curl --noproxy '*' -fsS --max-time 3 http://127.0.0.1:8001/auth/login >/dev/null \
    && [[ $(curl --noproxy '*' -sS --max-time 3 -o /dev/null -w '%{http_code}' \
      --resolve app.traineeserver.ru:443:127.0.0.1 \
      https://app.traineeserver.ru/) == 302 ]]; then
    healthy=true
    break
  fi
  sleep 2
done

[[ $healthy == true ]]
trap - ERR
echo "Migrated services to $1"
