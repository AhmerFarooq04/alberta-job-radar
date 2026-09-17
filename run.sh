#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$(readlink -f "$0")")"
mkdir -p data

exec 9>data/.pipeline.lock
flock -n 9 || {
    echo "Another run or update is active."
    exit 1
}

docker compose run --rm --no-deps -T worker "$@"