#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! $1 =~ ^[0-9a-f]{40}$ ]]; then
  echo 'Expected a 40-character commit SHA' >&2
  exit 2
fi

base=/opt/math-page-ci
release=$base/releases/$1
current=$base/current
previous=$base/previous

if [[ ! -d $release || -L $release || ! -x $release/.venv/bin/python || ! -f $release/app.py ]]; then
  echo 'Release is missing or incomplete' >&2
  exit 1
fi

old=$(readlink -f "$current" || true)
if [[ -n $old && $old != "$base/releases/"* ]]; then
  echo 'Current release path is invalid' >&2
  exit 1
fi

ln -sfn "$release" "$base/current.next"
mv -Tf "$base/current.next" "$current"
systemctl restart math-page-auth math-page-app

healthy=false
for _ in {1..20}; do
  if curl --noproxy '*' -fsS --max-time 3 http://127.0.0.1:8001/auth/login >/dev/null \
    && [[ $(curl -sS --max-time 3 -o /dev/null -w '%{http_code}' \
      --noproxy '*' \
      --resolve app.traineeserver.ru:443:127.0.0.1 \
      https://app.traineeserver.ru/) == 302 ]]; then
    healthy=true
    break
  fi
  sleep 2
done

if [[ $healthy == true ]]; then
  if [[ -n $old && $old != "$release" ]]; then
    ln -sfn "$old" "$base/previous.next"
    mv -Tf "$base/previous.next" "$previous"
  fi
  echo "Activated $1"
  exit 0
fi

echo 'Health check failed; restoring previous release' >&2
if [[ -n $old ]]; then
  ln -sfn "$old" "$base/current.next"
  mv -Tf "$base/current.next" "$current"
  systemctl restart math-page-auth math-page-app
fi
exit 1
