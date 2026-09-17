#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$(readlink -f "$0")")"
mkdir -p data

exec 9>data/.pipeline.lock
flock -n 9 || {
    echo "A pipeline run or update is active. Retry after it finishes."
    exit 1
}

if [[ -n "$(git status --porcelain)" ]]; then
    echo "Commit or resolve local repository changes before updating."
    exit 1
fi

git pull --ff-only
docker compose config --quiet
docker compose build api web
docker compose up -d --wait api web
docker compose ps