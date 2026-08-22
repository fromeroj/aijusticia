#!/bin/bash
# AI Justicia — Inicia todos los servicios
#
# Uso:
#   ./start.sh          # inicia todo
#   ./start.sh stop     # detiene todo
#   ./start.sh status   # muestra estado
#
# Servicios:
#   1. PostgreSQL + pgvector  (:5433)  — Docker
#   2. LM Studio              (:1234)  — embeddings (nomic-embed-text)
#   3. mlx_lm.server + LoRA   (:1235)  — LLM (Qwen3.6-35B + LoRA v3)
#   4. FastAPI                (:8000)  — API + SSE
#
# Requisitos:
#   - Docker corriendo
#   - LM Studio abierto con nomic-embed-text cargado
#   - Modelo Qwen3-30B-A3B-Instruct-2507-bf16 descargado en ~/.lmstudio/models/

set -e

ENGINE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ENGINE_DIR"

MODEL_PATH="${AIJ_MODEL_PATH:-$HOME/.lmstudio/models/mlx-community/Qwen3-30B-A3B-Instruct-2507-bf16}"
ADAPTER_PATH="data/lora_adapter_v5"
PID_DIR="/tmp/aij_pids"
mkdir -p "$PID_DIR"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

status() {
    echo "=== AI Justicia — Estado de servicios ==="
    echo ""

    # PostgreSQL
    if docker compose ps 2>/dev/null | grep -q "aijusticia-postgres.*Up"; then
        echo -e "  ${GREEN}✓${NC} PostgreSQL    :5433  (corriendo)"
    else
        echo -e "  ${RED}✗${NC} PostgreSQL    :5433  (detenido)"
    fi

    # LM Studio (embeddings) + guard: LLMs grandes NO deben vivir aquí
    if curl -s http://localhost:1234/v1/models 2>/dev/null | grep -q "nomic"; then
        echo -e "  ${GREEN}✓${NC} LM Studio     :1234  (nomic-embed-text cargado)"
        # Verificar que no haya LLMs grandes cargados en LM Studio (memoria)
        if command -v lms > /dev/null 2>&1; then
            BIG_MODELS=$(lms ps 2>/dev/null | awk '$4 ~ /GB/ && $4+0 >= 1 {print $1}')
            if [ -n "$BIG_MODELS" ]; then
                echo -e "  ${RED}⚠ ATENCIÓN:${NC} LLMs grandes cargados en LM Studio (desperdician RAM):"
                echo "$BIG_MODELS" | while read -r m; do
                    echo -e "      ${RED}✗${NC} $m — descárgalo con: lms unload $m"
                done
                echo "      (LM Studio debe tener SOLO nomic; el LLM lo sirve mlx_lm :1235)"
            fi
        fi
    else
        echo -e "  ${RED}✗${NC} LM Studio     :1234  (no responde o sin nomic)"
    fi

    # mlx_lm.server (LLM + LoRA)
    if curl -s http://localhost:1235/v1/models 2>/dev/null | grep -q "qwen\|Qwen\|bf16"; then
        echo -e "  ${GREEN}✓${NC} mlx_lm.server :1235  (Qwen3-30B + LoRA v5)"
    else
        echo -e "  ${RED}✗${NC} mlx_lm.server :1235  (detenido)"
    fi

    # FastAPI
    if curl -s http://localhost:8000/health 2>/dev/null | grep -q "ok"; then
        echo -e "  ${GREEN}✓${NC} FastAPI       :8000  (API lista)"
    else
        echo -e "  ${RED}✗${NC} FastAPI       :8000  (detenido)"
    fi
    echo ""
}

start() {
    echo "=== AI Justicia — Iniciando servicios ==="
    echo ""

    # 1. PostgreSQL
    echo -e "${YELLOW}1/4${NC} PostgreSQL..."
    docker compose up -d 2>/dev/null
    sleep 3
    echo -e "  ${GREEN}✓${NC} PostgreSQL en :5433"

    # 2. LM Studio check (must be started manually)
    echo -e "${YELLOW}2/4${NC} LM Studio (embeddings)..."
    if curl -s http://localhost:1234/v1/models 2>/dev/null | grep -q "nomic"; then
        echo -e "  ${GREEN}✓${NC} LM Studio ya corre con nomic en :1234"
    else
        echo -e "  ${RED}✗${NC} LM Studio no responde o no tiene nomic cargado."
        echo "     Abre LM Studio y carga: text-embedding-nomic-embed-text-v1.5"
        echo "     Presiona Enter cuando esté listo..."
        read -r
    fi

    # 3. mlx_lm.server (LLM + LoRA)
    echo -e "${YELLOW}3/4${NC} mlx_lm.server (LLM + LoRA)..."
    if curl -s http://localhost:1235/v1/models 2>/dev/null | grep -q "qwen\|Qwen\|bf16"; then
        echo -e "  ${GREEN}✓${NC} mlx_lm.server ya corre en :1235"
    else
        nohup python3 -u -m mlx_lm server \
            --model "$MODEL_PATH" \
            --adapter-path "$ADAPTER_PATH" \
            --host 0.0.0.0 \
            --port 1235 \
            > /tmp/aij_lora_server.log 2>&1 &
        echo $! > "$PID_DIR/mlx_lm.pid"
        echo -n "  Esperando modelo..."
        for i in $(seq 1 30); do
            if curl -s http://localhost:1235/v1/models 2>/dev/null | grep -q "qwen\|Qwen\|bf16"; then
                echo -e " ${GREEN}✓${NC} mlx_lm.server en :1235"
                break
            fi
            echo -n "."
            sleep 2
        done
        echo ""
    fi

    # 4. FastAPI
    echo -e "${YELLOW}4/4${NC} FastAPI..."
    if curl -s http://localhost:8000/health 2>/dev/null | grep -q "ok"; then
        echo -e "  ${GREEN}✓${NC} FastAPI ya corre en :8000"
    else
        nohup python3 -u -m uvicorn ai_justicia.api.main:app \
            --host 0.0.0.0 --port 8000 \
            > /tmp/aij_server.log 2>&1 &
        echo $! > "$PID_DIR/fastapi.pid"
        sleep 4
        echo -e "  ${GREEN}✓${NC} FastAPI en :8000"
    fi

    echo ""
    echo -e "${GREEN}=== AI Justicia listo ===${NC}"
    echo ""
    echo "  API:       http://localhost:8000/docs"
    echo "  Health:    http://localhost:8000/health"
    echo "  Admin:     http://localhost:8000/admin/sources"
    echo ""
}

stop() {
    echo "Deteniendo AI Justicia..."

    # FastAPI
    if [ -f "$PID_DIR/fastapi.pid" ]; then
        kill "$(cat "$PID_DIR/fastapi.pid")" 2>/dev/null && echo "  ✓ FastAPI detenido"
    fi
    # Also kill any uvicorn on 8000
    lsof -t -i :8000 2>/dev/null | xargs kill 2>/dev/null

    # mlx_lm.server
    if [ -f "$PID_DIR/mlx_lm.pid" ]; then
        kill "$(cat "$PID_DIR/mlx_lm.pid")" 2>/dev/null && echo "  ✓ mlx_lm.server detenido"
    fi
    lsof -t -i :1235 2>/dev/null | xargs kill 2>/dev/null

    # PostgreSQL
    docker compose down 2>/dev/null && echo "  ✓ PostgreSQL detenido"

    # LM Studio se deja corriendo (lo cierra el usuario manualmente)

    rm -f "$PID_DIR"/*.pid
    echo ""
    echo "Nota: LM Studio sigue corriendo (ciérralo manualmente si lo deseas)."
}

case "${1:-start}" in
    start)  start ;;
    stop)   stop ;;
    status) status ;;
    restart) stop; sleep 2; start ;;
    *) echo "Uso: $0 {start|stop|status|restart}"; exit 1 ;;
esac
