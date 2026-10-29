#!/usr/bin/env bash
set -euo pipefail
umask 027

if [[ ( $# -ne 1 && $# -ne 2 ) || ! $1 =~ ^[0-9a-f]{40}$ || ( $# -eq 2 && $2 != --prepare-only ) ]]; then
  echo 'Expected a 40-character commit SHA and optional --prepare-only' >&2
  exit 2
fi

revision=$1
base=/opt/math-page-ci
repository=$base/repository
release=$base/releases/$revision

if [[ ! -d $repository/.git ]]; then
  git clone --no-checkout https://github.com/mytrainee-ai/test-ui.git "$repository"
fi

git -C "$repository" fetch --no-tags origin '+refs/heads/main:refs/remotes/origin/main'
git -C "$repository" cat-file -e "$revision^{commit}"
git -C "$repository" merge-base --is-ancestor "$revision" refs/remotes/origin/main

if [[ ! -d $release ]]; then
  git -C "$repository" worktree add --detach "$release" "$revision"
fi

if [[ ! -x $release/.venv/bin/python ]]; then
  python3 -m venv "$release/.venv"
fi

"$release/.venv/bin/python" -m pip install -q -r "$release/requirements.txt"
cd "$release"
.venv/bin/python -m unittest -q test_local test_auth

if [[ ${2:-} != --prepare-only ]]; then
  sudo /usr/local/sbin/math-page-activate "$revision"

  current=$(readlink -f "$base/current")
  previous=$(readlink -f "$base/previous" || true)
  keep=("$current")
  if [[ -n $previous && $previous != "$current" ]]; then
    keep+=("$previous")
  fi

  mapfile -t releases < <(find "$base/releases" -mindepth 1 -maxdepth 1 -type d \
    -printf '%T@ %p\n' | sort -nr | cut -d' ' -f2-)
  for candidate in "${releases[@]}"; do
    [[ $candidate =~ ^/opt/math-page-ci/releases/[0-9a-f]{40}$ ]] || continue
    preserved=false
    for selected in "${keep[@]}"; do
      if [[ $candidate == "$selected" ]]; then
        preserved=true
        break
      fi
    done
    if [[ $preserved == true ]]; then
      continue
    fi
    if (( ${#keep[@]} < 3 )); then
      keep+=("$candidate")
    elif ! git -C "$repository" worktree remove --force "$candidate"; then
      echo "Could not remove old release: $candidate" >&2
    fi
  done
fi
