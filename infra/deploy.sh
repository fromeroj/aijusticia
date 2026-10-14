#!/bin/bash
# Deploy a producción con gate de salud. Uso: bash infra/deploy.sh [api|web|all]
set -euo pipefail
cd "$(dirname "$0")/.."
TARGET="${1:-all}"
PROD=root@162.35.113.166

echo "== deploy $TARGET → 162 =="
case "$TARGET" in
  api)
    rsync -az --exclude .env --exclude .venv --exclude data/ \
      --exclude __pycache__ --exclude "*.pyc" --exclude .pytest_cache \
      engine/ $PROD:/opt/aijusticia/engine/
    echo "-- restart engine…"
    ssh $PROD "systemctl restart aijusticia-engine"
    sleep 6
    ;;
  web)
    rsync -az --exclude node_modules --exclude .next/cache \
      apps/web/ $PROD:/opt/aijusticia/app/
    echo "-- build en server…"
    ssh $PROD "cd /opt/aijusticia/app && npm run build" \
      || { echo "build en server falló"; exit 1; }
    ssh $PROD "systemctl restart aijusticia-web"
    sleep 4
    ;;
  all)
    bash "$0" api
    bash "$0" web
    exit 0
    ;;
  *) echo "uso: deploy.sh [api|web|all]"; exit 1;;
esac

echo "== gate de salud =="
if python3 infra/salud.py > /tmp/salud_deploy.log 2>&1; then
  tail -2 /tmp/salud_deploy.log
  echo "✅ deploy OK"
else
  cat /tmp/salud_deploy.log
  echo "❌ salud en warn/fail tras el deploy — revisar antes de seguir"
  exit 1
fi
