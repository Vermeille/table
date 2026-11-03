#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
  echo 'Created .env. Fill in the Hermes gateway key, Docker resource names, hostname, and a Table password; then run this script again.'
  exit 1
fi
# Compose validates substitution; secrets are never sourced as executable shell code.
docker compose --env-file .env config --quiet
docker build -t table:0.1.0 .
table_data_volume=$(docker compose --env-file .env config --format json | python3 -c 'import json,sys;print(json.load(sys.stdin)["volumes"]["table-data"]["name"])')
docker volume create "$table_data_volume" >/dev/null
docker compose --env-file .env up -d
printf '%s\n' 'Table started. Configure HTTPS routing, then open Connections to select/sign in to your model and install the four profiles.'
