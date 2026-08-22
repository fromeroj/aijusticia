# Runbook de Producción — AI Justicia

> Última actualización: 22 agosto 2026
> Estado: **LIVE** en https://aijusticia.mx y https://laley.com.mx

---

## 1. Arquitectura

```
                        INTERNET
                           │
        DNS: aijusticia.mx, www, laley.com.mx, www
        (aijusticia.com.mx pendiente de registro A)
                           │
                           ▼
┌─────────────────────────────────────────────────┐
│  RACKNERD — 192.227.167.147                     │
│  hostname: netmaker.konen.guru                  │
│  Ubuntu 20.04 · 1 vCPU · 729MB RAM              │
│                                                 │
│  Caddy (Docker, :80/:443)                       │
│  ├─ TLS Let's Encrypt automático                │
│  └─ reverse_proxy → 66.154.100.25:6234          │
│                                                 │
│  También corre: Netmaker VPN, smtp-proxy,       │
│  MQTT, CoreDNS (no tocar)                       │
└───────────────────────┬─────────────────────────┘
                        │ HTTP interno (sin TLS)
                        ▼
┌─────────────────────────────────────────────────┐
│  VPS APP — 66.154.100.25 (SSH puerto 22)        │
│  Ubuntu 22.04 · 3 vCPU · 2GB RAM · swap 2GB     │
│                                                 │
│  nginx :6234 (edge interno)                     │
│  ├─ /health /query/ /dossiers/ /auth/           │
│  │  /abogados/registro /admin/ /jobs/           │
│  │  /documentos/  → FastAPI :8000               │
│  └─ / (resto)     → Next.js :3000               │
│                                                 │
│  systemd:                                       │
│  ├─ aijusticia-engine.service (uvicorn ×2)      │
│  └─ aijusticia-web.service   (next start)       │
│                                                 │
│  Código: /opt/aijusticia/{engine,app}           │
│  También corre: vozclara :5050, biow :6128,     │
│  bandit (no tocar)                              │
└───────────────────────┬─────────────────────────┘
                        │ TÚNEL SSH REVERSO (autossh)
                        │ reenvía VPS 127.0.0.1:
                        │   :1235 → Mac :1235 (LLM)
                        │   :1234 → Mac :1234 (embeddings)
                        │   :5433 → Mac :5433 (PostgreSQL)
                        ▼
┌─────────────────────────────────────────────────┐
│  MAC STUDIO M3 Ultra — 275GB (casa)             │
│                                                 │
│  ├─ mlx_lm.server :1235                         │
│  │    Qwen3-30B-A3B-Instruct-2507-bf16 (57GB)   │
│  │    + LoRA v5 (rank 32, val loss 0.853)       │
│  ├─ LM Studio :1234                             │
│  │    nomic-embed-text-v1.5 (768 dim)           │
│  │    ⚠ SOLO nomic debe estar cargado           │
│  └─ PostgreSQL 16 + pgvector :5433 (Docker)     │
│       162,870 documentos · 17GB                 │
└─────────────────────────────────────────────────┘
```

**Regla de oro**: la Mac es la única con la IA y la base de datos. Si la Mac
se apaga, el sitio sigue arriba pero no genera respuestas.

---

## 2. Dominios y DNS

| Dominio | DNS | Estado |
|---------|-----|--------|
| aijusticia.mx | A → 192.227.167.147 | ✅ live |
| www.aijusticia.mx | A → 192.227.167.147 | ✅ live |
| laley.com.mx | A → 192.227.167.147 | ✅ live |
| www.laley.com.mx | A → 192.227.167.147 | ✅ live |
| aijusticia.com.mx | **sin registro** | ⚠ crear A → 192.227.167.147 (Caddy ya lo tiene listo) |
| aijusticia.com | Cloudflare (terceros) | no es nuestro |

El frontend es **same-origin** (`NEXT_PUBLIC_API_URL=""`) → funciona igual
por cualquier dominio que apunte al Caddy.

---

## 3. Configuración por servidor

### 3.1 RackNerd (192.227.167.147) — NO TOCAR Caddy salvo para agregar dominios

Caddyfile dentro del contenedor `caddy` (`docker exec caddy cat /etc/caddy/Caddyfile`):
```
# Aijusticia
aijusticia.com.mx, www.aijusticia.com.mx, aijusticia.mx, www.aijusticia.mx {
	reverse_proxy http://66.154.100.25:6234
}

# LaLey
laley.com.mx, www.laley.com.mx {
	reverse_proxy http://66.154.100.25:6234
}
```
Cambios: editar `/tmp/Caddyfile` en el host (bind mount), luego
`docker restart caddy`. TLS se emite/renueva solo.

### 3.2 VPS App (66.154.100.25)

**nginx** — `/etc/nginx/sites-available/aijusticia` (symlink en sites-enabled):
un solo `server { listen 6234; }` con los location de API → :8000 y el resto
→ :3000. `nginx -t && systemctl reload nginx` tras editar.

**systemd**:
```bash
systemctl status|restart|stop aijusticia-engine   # FastAPI
systemctl status|restart|stop aijusticia-web      # Next.js
journalctl -u aijusticia-engine -f                # logs
```

**Engine .env** — `/opt/aijusticia/engine/.env`:
```
LMSTUDIO_BASE_URL=http://127.0.0.1:1235/v1     # LLM vía túnel
EMBED_BASE_URL=http://127.0.0.1:1234/v1        # nomic vía túnel
PG_HOST=127.0.0.1
PG_PORT=5433                                    # Postgres vía túnel
```

### 3.3 Mac (casa)

| Servicio | Cómo arranca | Comando manual |
|----------|--------------|----------------|
| Túnel | **launchd** `com.aijusticia.tunnel` (auto) | `launchctl kickstart -k gui/$(id -u)/com.aijusticia.tunnel` |
| LLM | manual | `cd engine && ./start.sh` (levanta mlx_lm+LoRA :1235) |
| Embeddings | LM Studio GUI | cargar solo `nomic-embed-text-v1.5` |
| PostgreSQL | Docker Desktop | `cd engine && docker compose up -d` |

Túnel (plist en `~/Library/LaunchAgents/com.aijusticia.tunnel.plist`):
autossh con `ServerAliveInterval=30`, reintentos cada 15s, logs en
`/tmp/aij-tunnel.log`. Verificar desde el VPS:
`ssh root@66.154.100.25 "curl -s http://127.0.0.1:1235/v1/models | head -c 80"`

⚠ LM Studio: descargar (`lms unload`) cualquier LLM grande — solo nomic
(84MB). El LLM lo sirve mlx_lm :1235. El guard está en `engine/start.sh status`.

---

## 4. Operación diaria

### Arranque tras apagón de la Mac
```bash
# 1. Docker Desktop (Postgres)      → abrir la app
# 2. LM Studio                      → cargar nomic-embed-text-v1.5
# 3. Túnel                          → automático (launchd)
# 4. LLM
cd ~/workspace/aijusticia/engine && ./start.sh
# 5. Verificar producción
curl -s https://aijusticia.mx/health
```
El VPS no requiere ningún arranque (systemd + túnel auto-reconectan).

### Actualizar código (desde la Mac)
```bash
cd ~/workspace/aijusticia
rsync -az --exclude data/ --exclude __pycache__ --exclude .env \
  engine/ root@66.154.100.25:/opt/aijusticia/engine/
rsync -az --exclude node_modules --exclude .next \
  app/ root@66.154.100.25:/opt/aijusticia/app/

# Si cambió el backend:
ssh root@66.154.100.25 "systemctl restart aijusticia-engine"

# Si cambió el frontend:
ssh root@66.154.100.25 "cd /opt/aijusticia/app && \
  NODE_OPTIONS=--max-old-space-size=1536 npm run build && \
  systemctl restart aijusticia-web"
```
⚠ No borrar el `.env` del engine en el VPS (los rsync de arriba lo excluyen).

### Verificar salud ( checklist)
```bash
# Túnel
ssh root@66.154.100.25 "curl -s http://127.0.0.1:1235/v1/models | head -c 60"
# VPS servicios
ssh root@66.154.100.25 "systemctl is-active aijusticia-engine aijusticia-web"
# Producción
curl -s https://aijusticia.mx/health
```

### Diagnóstico rápido
| Síntoma | Causa probable | Fix |
|---------|---------------|-----|
| 502 en dominio | app caída en 66.154 | `systemctl restart aijusticia-engine aijusticia-web` |
| `/health` degraded, llm=False | túnel caído o Mac apagada | verificar Mac + `launchctl kickstart -k gui/$(id -u)/com.aijusticia.tunnel` |
| Respuestas no generan, embeddings ok | mlx_lm caído en Mac | `./start.sh` en la Mac |
| Respuestas desviadas / lento | LLM grande cargado en LM Studio | `lms ps` → `lms unload <modelo>` (dejar solo nomic) |
| DB connection refused | Docker Postgres caído | Mac: `docker compose up -d` (engine/) |

---

## 5. Modelo en producción

| Componente | Valor |
|------------|-------|
| LLM | Qwen3-30B-A3B-Instruct-2507-bf16 (57GB, MLX) |
| Adapter | `data/lora_adapter_v5` (rank 32, val loss 0.853) |
| Inferencia | `mlx_lm.server :1235`, `chat_template_kwargs.enable_thinking=false` |
| Embeddings | nomic-embed-text-v1.5, 768 dim |
| DB | PostgreSQL 16 + pgvector, 162,870 docs, 1.5M chunks |

### Retrain del LoRA (en la Mac)
```bash
cd engine
python scripts/generate_synthetic_v2.py --count 5000   # más sintéticos si hace falta
python -m mlx_lm lora --config data/lora_adapter_v5/config.yaml
# ~3.5 min, val loss esperada ≤ 0.86
systemctl… no aplica: reiniciar mlx_lm (./start.sh) para cargar el adapter nuevo
```
Con datos consentidos de usuarios: `python scripts/train_lora.py --extraer-consentidos`
Adapters de bufete (aislados): `python scripts/train_lora.py --bufete <uuid>`

---

## 6. Seguridad

- SSH solo con llave en ambos servidores (root@66.154 y root@192.227)
- El :6234 del VPS es HTTP plano — solo aceptable porque viaja entre
  servidores propios; si se expone a internet directo, poner TLS o restricción
  por IP en nginx (`allow 192.227.167.147; deny all;`)
- La frase de recuperación NUNCA sale del navegador del usuario (solo hash Argon2/PBKDF2 en DB)
- Bóveda de archivos: cifrada en cliente (fase C)
- Tokens de dispositivo: SHA-256 hasheados en `actores.token_dispositivo_hash`
- Google OAuth: listo pero inactivo — requiere `NEXT_PUBLIC_GOOGLE_CLIENT_ID` +
  `GOOGLE_CLIENT_SECRET` en el VPS (`/opt/aijusticia/app/.env.production`) y
  rebuild; callback: `https://aijusticia.mx/api/auth/google/callback`

---

## 7. Pendientes conocidos
- [ ] DNS aijusticia.com.mx → 192.227.167.147 (Caddy ya listo)
- [ ] Google OAuth: crear proyecto Google Cloud + secrets
- [ ] Fase C: bóveda cifrada de documentos (UI + WebCrypto)
- [ ] Fase D: compartir dossiers con abogados + audit log + directorio
- [ ] DOF backfill completo (murió con Docker; reiniciar en la Mac)
- [ ] Monitoreo externo (UptimeRobot o similar sobre /health)
- [ ] Respaldos de la DB de la Mac (17GB — pg_dump semanal a disco externo o S3)
