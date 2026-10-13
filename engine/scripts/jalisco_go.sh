#!/bin/bash
# Relanza el harvest de Jalisco vía CDP (a prueba de typos).
# Detiene cualquier instancia previa de Chrome, abre la del perfil CDP
# con el puerto de depuración, y lanza el descargador.
echo "Cerrando Chrome..."
killall "Google Chrome" 2>/dev/null
sleep 3
echo "Abriendo Chrome CDP (perfil copiado, puerto 9222)..."
open -a "Google Chrome" --args \
  --user-data-dir="$HOME/ChromeCDP-profile" \
  --remote-debugging-port=9222 \
  --no-first-run --no-default-browser-check
sleep 8
if ! curl -s -m 5 http://localhost:9222/json/version > /dev/null; then
  echo "ERROR: el puerto 9222 no respondió"; exit 1
fi
echo "Chrome CDP OK — lanzando descargador (Ctrl+C para detener; reanuda igual)"
cd "$(dirname "$0")/.." || exit 1
exec python3 scripts/harvest_jalisco_cdp.py
