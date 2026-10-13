# Runbook de Producción — AI Justicia

> Última actualización: 12 octubre 2026
> Estado: **LIVE** en https://aijusticia.mx y https://laley.com.mx

---

## 1. Arquitectura

```
                        INTERNET
                           │
        DNS: aijusticia.mx, www, laley.com.mx, www
                           │
                           ▼
┌─────────────────────────────────────────────────┐
│  RACKNERD — 192.227.167.147                     │
│  hostname: netmaker.konen.guru                  │
│                                                 │
│  Caddy (Docker, :80/:443)                       │
│  ├─ TLS Let's Encrypt automático                │
│  └─ reverse_proxy → 66.154.100.25:6234          │
└───────────────────────┬─────────────────────────┘
                        │ HTTP interno (sin TLS)
                        ▼
┌─────────────────────────────────────────────────┐
│  VPS APP — 66.154.100.25 (bandit.konen.guru)    │
│  Ubuntu 22.04 · 3 vCPU · 2GB RAM · 30GB disco   │
│                                                 │
│  nginx :6234 (edge interno)                     │
│  ├─ API (FastAPI :8000, systemd aijusticia-     │
│  │   engine): /chat/stream /corpus/status       │
│  │   /query/ /dossiers/ /auth/ /admin/ …        │
│  └─ / (resto)     → Next.js :3000 (aijusticia-  │
│                     web)                        │
│                                                 │
│  Código: /opt/aijusticia/{engine,app}           │
│  LLM: MiniMax-M3 vía https://api.minimax.io/v1  │
│  (cloud — no depende de la Mac)                 │
│  DB: PostgreSQL en 182.255.84.124:5432          │
│  (conexión DIRECTA — el túnel SSH de la Mac ya  │
│  no participa; 397K docs · 10.6M chunks)        │
└─────────────────────────────────────────────────┘
```

**Regla de oro (v2)**: el VPS es autónomo — LLM cloud + DB remota. La Mac
solo hace harvesting/cosecha pesada y entrenamiento (Soup/Tlamatini).

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
LMSTUDIO_BASE_URL=https://api.minimax.io/v1    # MiniMax-M3 (cloud)
PG_HOST=182.255.84.124                         # Postgres producción (directo)
PG_PORT=5432
PG_DB=aijusticia
PG_USER=aijusticia
PG_PASSWORD=<ver .env, NO commitear>
```
⚠ El túnel autossh de la Mac (`com.aijusticia.tunnel`) ya NO es necesaria
para el sitio; sigue instalada para los harvesters locales. Si quitas el
forward `5433`, verificar que nada use `127.0.0.1:5433` en el VPS.

### 3.3 Mac (casa)

| Servicio | Cómo arranca | Notas |
|----------|--------------|-------|
| Túnel | launchd `com.aijusticia.tunnel` | forward `-R 5433→Mac:5432` (fix 12-oct; el plist viejo apuntaba a 5433→5433 y la DB nunca llegaba) |
| Harvesters pesados | manual / setsid | ordenjuridico, estados (ver §5) |
| Entrenamiento Tlamatini | Soup CLI | `tohil/` (configs + Makefile) |

### 3.4 DB de producción (182.255.84.124)

PostgreSQL 16 — 397K documentos, 10.6M chunks, ~2.97B tokens.
Columnas clave añadidas el 12-oct-2026 (ver scripts):
- `documentos.titulo_search` — tsvector GENERATED de `titulo`
- `documentos_chunks.articulo_num` — int, primer artículo del chunk (backfill
  por rangos con regex; índice parcial)

Estado por fuente: `GET /corpus/status` (o ver https://aijusticia.mx/estado).

---

## 4. Operación diaria

### Arranque tras mantenimiento
```bash
ssh root@66.154.100.25 "systemctl restart aijusticia-engine aijusticia-web"
curl -s https://aijusticia.mx/health
curl -s -o /dev/null -w '%{http_code}\n' https://aijusticia.mx/estado
```
El sitio es autónomo (LLM cloud + DB remota): si la Mac se apaga, el sitio
sigue funcionando completo. La Mac solo hace harvesting y entrenamiento.

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
| `/health` ok pero sin respuesta | MiniMax cloud caído / API key | revisar `LMSTUDIO_BASE_URL` en el .env del VPS |
| Chat sin eventos `laws` | buscar_en_ley falla (col falta) | revisar `journalctl -u aijusticia-engine \| grep buscar_en_ley` |
| DB connection refused/fatal | DB en 182.255 caída o password | `ssh root@66.154.100.25 "pg_isready -h 182.255.84.124"` |

---

## 5. Corpus — estado y scripts (12 oct 2026)

| Fuente | Docs | Nota |
|--------|------|------|
| DOF | 161,577 | vivo (diario) |
| SJF | 149,995 | tesis + ejecutorias |
| SentenciasEdomex/CDMX/Qro | 66,726 | harvests por estado |
| GacetaEstatal | 15,123 | 31 entidades (gacetas oficiales) |
| GacetaCDMX | 2,193 | |
| LeyesBiblio / LexMX / Justia | 1,195 | leyes federales/estatales |
| **OrdenJuridico** | creciendo | **32 estados — leyes consolidadas; harvest en curso (script `harvest_ordenjuridico.py`, resume con estado.json, borra archivos tras extraer)** |

### Limpieza de corpus (el texto estaba sucio)
```bash
# en el VPS, tras un harvest grande:
cd /opt/aijusticia/engine
.venv/bin/python scripts/limpieza_profunda.py   # idempotente, solo filas sucias
.venv/bin/python scripts/fix_titulos_oj.py      # títulos mojibake de ordenjuridico
.venv/bin/python scripts/migrar_articulo_num.py # (solo si falta la columna)
```
`limpieza_profunda` arregla: guiones partidos, saltos/espacios, números de
página, controles/form-feeds, mojibake, "Artículo N" en minúsculas, títulos.
FTS se reindexa solo (columnas GENERATED). Embeddings no cambian.

---

## 6. Modelo en producción

| Componente | Valor |
|------------|-------|
| LLM | MiniMax-M3 (cloud, razonador — emite `<think>` que el engine purga) |
| Chat | 2 agentes: Izel (conversacional, streaming SSE) + Bibliotecario (leyes) |
| Streaming | `POST /chat/stream` — eventos `token`/`laws`/`done`/`reset` |
| Embeddings | desactivados; recuperación 100% FTS español (GIN tsvector) |
| DB | PostgreSQL 16 — 397K docs, 10.6M chunks (182.255.84.124) |

### Guardas del chat (implementadas en chat_stream.py)
- Purga de caracteres CJK por token (M3 desliza chino en español)
- Detección de repetición degenerada → reintento + evento `reset`
- `enable_thinking` off en llamadas cortas
- Prompt anti-voseo (español mexicano, de tú)

### Entrenamiento Tlamatini (en la Mac)
Ver `tohil/` (Makefile, configs Soup, eval_bateria.py) y `docs/`.

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
- [x] ~~DOF backfill~~ — DOF vivo vía scheduler (161K docs, al día)
- [ ] Monitoreo externo (UptimeRobot o similar sobre /health)
- [ ] Respaldos de la DB de producción (397K docs en 182.255 — pg_dump semanal)
- [ ] CPT Tlamatini v1: reexportar corpus con `prep_cpt_completo.py` DESPUÉS
      de que `limpieza_profunda` + harvest OrdenJuridico terminen (12-oct)
- [ ] Voz (TTS/STT) en el chat — sesión 3 del plan de rediseño
