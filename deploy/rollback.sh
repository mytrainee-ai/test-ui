#!/usr/bin/env bash
set -euo pipefail

base=/opt/math-page-ci
previous=$(readlink -f "$base/previous" || true)
if [[ ! $previous =~ ^/opt/math-page-ci/releases/[0-9a-f]{40}$ ]]; then
  echo 'No previous release is available' >&2
  exit 1
fi

exec /usr/local/sbin/math-page-activate "${previous##*/}"
