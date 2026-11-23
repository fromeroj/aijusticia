#!/bin/bash
# Deploy a producción con gate de salud. Uso: bash infra/deploy.sh [api|web|all]
#
# El gate corre DESPUÉS de desplegar y usa infra/salud_ci.py: un fallo ya
# alertado (por el monitor cada 30 min) no vuelve a fallar el deploy. Sólo
# fallan los fallos nuevos, o los que persisten 12h tras el último aviso.
# La memoria de alertas es $SALUD_ESTADO (CI la guarda en la cache de Actions).
set -euo pipefail
cd "$(dirname "$0")/.."
TARGET="${1:-all}"
PROD=root@162.35.113.166
SALUD_ESTADO="${SALUD_ESTADO:-/tmp/aij-salud-alerta.json}"

gate_de_salud() {
  echo "== gate de salud (falla sólo con fallos nuevos o persistentes) =="
  if python3 infra/salud_ci.py --estado "$SALUD_ESTADO"; then
    echo "✅ deploy OK"
  else
    echo "❌ gate de salud: hay fallos nuevos o que persisten — ver arriba"
    exit 1
  fi
}

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
    # un solo gate, al final: los pasos individuales no gatean por separado
    SIN_GATE=1 bash "$0" api
    SIN_GATE=1 bash "$0" web
    ;;
  *) echo "uso: deploy.sh [api|web|all]"; exit 1;;
esac

if [ "${SIN_GATE:-0}" != "1" ]; then
  gate_de_salud
fi
