# Componente: API Producto (FastAPI)

**Qué es**: el engine — todas las rutas que no son el chat.
**Vive en**: `engine/ai_justicia/api/` → deploy `/opt/aijusticia/engine` en 162 (systemd `aijusticia-engine`, uvicorn ×2, :8000, nginx :6234 al frente).

## Rutas
`/dossiers/` (expedientes compartidos), `/auth/`, `/abogados/registro`, `/admin/`,
`/jobs/`, `/documentos/`, `/query/` (pipeline clásico), `/corpus/status`,
`/tts`, `/email`, `/chat/stream` (ver izel.md).

## Dependencias
- DB prod (local 162) vía `ai_justicia.corpus.store.get_conn`.
- LLM: `LMSTUDIO_BASE_URL` (env var — hoy MiniMax cloud).
- El frontend es same-origin (`NEXT_PUBLIC_API_URL=""`).

## Deploy
```bash
rsync -az --exclude .env --exclude .venv --exclude data/ --exclude __pycache__ \
  engine/ root@162.35.113.166:/opt/aijusticia/engine/
ssh root@162.35.113.166 "systemctl restart aijusticia-engine"
```
(El repo ahora llama `engine/` a esta unidad de deploy; docs la refieren como "API producto".)

## Nota de esquema
El schema de la DB de producción difiere del histórico: ver `components/bases-de-datos.md`.
`python-multipart` y `curl_cffi` instalados a mano en el .venv de 162.
