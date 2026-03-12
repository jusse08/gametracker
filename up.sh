#!/usr/bin/env bash
set -euo pipefail

read -r -p "Собрать GameTrackerAgent.exe перед запуском? [y/N]: " reply
reply="${reply,,}"

if [[ "$reply" == "y" || "$reply" == "yes" || "$reply" == "д" || "$reply" == "да" ]]; then
  echo "Собираю агент..."
  docker compose --profile build-agent run --rm agent-builder
fi

echo "Поднимаю backend + frontend..."
docker compose up -d backend frontend
