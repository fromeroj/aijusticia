# Runbook de Producción — AI Justicia

> Última actualización: 14 octubre 2026
> Estado: **LIVE** en https://aijusticia.mx y https://laley.com.mx

> ## ⚠️ TOPOLOGÍA REAL (verificada 13-oct-2026)
>
> | Servidor | Rol |
> |---|---|
> | **162.35.113.166** (vps3603848.trouble-free.net) | **PRODUCCIÓN** — app + engine + **postgres LOCAL** (473K docs, 14.4M chunks). El Caddy manda aijusticia.mx AQUÍ. |
> | 192.227.167.147 (RackNerd) | Caddy TLS, reverse_proxy → 162.35.113.166:6234 |
> | 182.255.84.124 | Postgres PARALELO (397K docs) — al que apunta el .env de la Mac; recibía la ingesta/harvest del flujo viejo |
> | 66.154.100.25 (bandit) | VPS viejo — hoy auxiliar para harvests; el engine/web ahí NO recibe tráfico público |
>
> **Consecuencias:** (1) deploy de producción = `root@162.35.113.166`;
> (2) la DB canónica para retrieval/corpus es la LOCAL de 162 — la de 182 es
> archivo/entrenamiento; (3) export CPT de Tlamatini debe salir de 162.

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
│  └─ reverse_proxy → 162.35.113.166:6234         │
└───────────────────────┬─────────────────────────┘
                        │ HTTP interno (sin TLS)
                        ▼
┌─────────────────────────────────────────────────┐
│  PRODUCCIÓN — 162.35.113.166                    │
│  (vps3603848.trouble-free.net)                  │
│                                                 │
│  nginx :6234 (edge interno)                     │
│  ├─ API (FastAPI :8000, systemd aijusticia-     │
│  │   engine): /chat/stream /corpus/status       │
│  │   /query/ /dossiers/ /auth/ /admin/ …        │
│  └─ / (resto)     → Next.js :3000 (aijusticia-  │
│                     web)                        │
│                                                 │
│  LLM: MiniMax-M3 vía https://api.minimax.io/v1  │
│  DB: PostgreSQL LOCAL 127.0.0.1:5432            │
│  473,848 docs · 14.4M chunks                    │
│  Cron: DOF diario 11:30 CDMX (dof_diario.sh),   │
│  backup_db.sh 04:00                             │
└─────────────────────────────────────────────────┘

  AUXILIARES:
  ├─ 66.154.100.25 — harvest ordenjuridico (32 estados
  │   → DB archivo 182) + limpieza del archivo
  └─ Mac Studio — túnel vestigial, cosechas con
      navegador (Playwright/CDP), entrenamiento Soup
```

**Regla de oro (v2)**: producción es autónoma (LLM cloud + DB local de 162).
La Mac solo hace cosechas que requieren navegador y entrenamiento (Soup/Tlamatini).

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
	reverse_proxy http://162.35.113.166:6234
}

# LaLey
laley.com.mx, www.laley.com.mx {
	reverse_proxy http://162.35.113.166:6234
}
```
Cambios: editar `/tmp/Caddyfile` en el host (bind mount), luego
`docker restart caddy`. TLS se emite/renueva solo.

### 3.2 VPS Producción (162.35.113.166)

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
PG_HOST=127.0.0.1                              # Postgres LOCAL de 162
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

### 3.4 DB de producción (LOCAL en 162)

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
ssh root@162.35.113.166 "systemctl restart aijusticia-engine aijusticia-web"
curl -s https://aijusticia.mx/health
curl -s -o /dev/null -w '%{http_code}\n' https://aijusticia.mx/estado
```
El sitio es autónomo (LLM cloud + DB remota): si la Mac se apaga, el sitio
sigue funcionando completo. La Mac solo hace harvesting y entrenamiento.

### Actualizar código — CI/CD (14-oct)

**El push a `main` deploya solo** (GitHub Actions): compila Python, build de
Next.js, deploy por rsync con la llave de CI, y gate de salud post-deploy.
Monitoreo externo cada 30 min (job `monitor` — falla solo en críticos).

```bash
make deploy       # manual, igual que CI (rsync + restart + gate de salud)
make salud        # chequeo integral (~15s, exit≠0 si algo crítico falla)
make salud-full   # + smoke real del chat
make bateria      # batería de evaluación contra producción
make deploy-data  # sincroniza data/ a 162 y 66
```

⚠ No borrar el `.env` del engine en el VPS (el rsync lo excluye).

**Nada a mano en los servidores.** Si algo se edita directamente en un server
(sin pasar por el repo), hay que traerlo al repo en el mismo cambio: el 23-nov
dos sesiones trabajaron a la vez sobre los mismos servidores y una dejó
`backup_db.sh` y la retención del storage fuera del repo. Comparar con:
`md5sum /opt/aijusticia/data/ingestion/backup_db.sh` contra `git show HEAD:data/ingestion/backup_db.sh | md5sum`.
Para exigir aprobación antes de deployar: GitHub → Environments → production →
required reviewers (la llave de CI vive en el secret `CI_SSH_KEY`).

### Verificar salud
```bash
make salud          # chequeo integral (~30s): HTTP + servidores, por SSH
make salud-full     # + un smoke real del chat
```
Lo mismo corre solo cada 30 min en CI (job `monitor`) y alerta una sola vez
por conjunto de fallos (`infra/salud_ci.py`): repite a las 12h si persiste.
Incluye lo que antes pasaba inadvertido: kills por OOM, resultado del
mantenimiento nocturno, réplica off-site y disco del storage.

### Diagnóstico rápido
| Síntoma | Causa probable | Fix |
|---------|---------------|-----|
| 502 en dominio | app caída en 162 | `systemctl restart aijusticia-engine aijusticia-web` |
| `/health` ok pero sin respuesta | MiniMax cloud caído / API key | revisar `LMSTUDIO_BASE_URL` en el .env del VPS |
| Chat sin eventos `laws` | buscar_en_ley falla (col falta) | revisar `journalctl -u aijusticia-engine \| grep buscar_en_ley` |
| DB connection refused/fatal | postgres local de 162 caído | `ssh root@162.35.113.166 "pg_isready -h 127.0.0.1"` |
| Correo "OOM recientes" | un proceso nocturno se desbordó | `journalctl -k --since "-30 hours" | grep "Out of memory"`; todo paso nocturno debe correr bajo `systemd-run --scope -p MemoryMax=1500M` |
| Correo "réplica off-site … sin réplica en curso" | la réplica al storage no se lanzó | `tail /var/log/aijusticia_offsite.log`; espacio en el storage (`backup_db.sh` no lanza con <20GB libres) |
| `/corpus/status` lento | no debería: recalcula en segundo plano | `journalctl -u aijusticia-engine | grep corpus_status` |

---

## 5. Corpus — estado y scripts (23 nov 2026)

Fuente de verdad: `https://aijusticia.mx/corpus/status` y
`docs/components/data-consumer.md`.

| Fuente | Docs | Último ingreso | Estado |
|--------|------|----------------|--------|
| DOF | 161,975 | diario | ✅ cron 17:30 UTC |
| SJF | 150,509 | diario | ✅ cron nocturno con watermark |
| SentenciasEdomex | 63,211 | — | completa de su manifiesto ingestado |
| SentenciasCDMX | 42,947 | — | completa |
| UNAM-Tesis | 17,616 | 11-nov | completa |
| OrdenJuridico (32 estados) | 29,261 | 23-nov | +1,409 recuperadas de 182 |
| GacetaEstatal | 21,056 | **7-nov** | ❌ **sin cosecha en producción** (scheduler no instalado en 162) |
| GacetaCDMX | 4,397 | — | |
| LeyesBiblio | 18 canónicas | **15-oct** | ❌ sin refresco automático (a mano) |
| LexMX | 317 | agosto | manual |
| **Total** | **500,868** | | ~19.5M chunks |

### Mantenimiento del corpus (cada paso con tope de memoria y plazo)
```bash
cd /opt/aijusticia/engine
# incremental (lo que corre cada noche):
systemd-run --scope -p MemoryMax=1500M -p MemorySwapMax=0 nice -n 19 \
  timeout 180m .venv/bin/python scripts/quality/limpieza_profunda.py
# barrido completo reanudable (domingos):  ... --completo
# traer documentos de otra DB sin pisar nada:
  ... scripts/ingestion/importar_jsonl_documentos.py <export.jsonl.gz>
```
Nunca re-ingerir una fuente completa con los ingesters: reescriben todos sus
chunks y pisan texto limpio con texto crudo (Nov 2026: 4.6M de filas por noche).

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

## 7. Seguridad

- **SSH sólo con llave en los cinco servidores** (aplicado 23-nov-2026). Hasta
  ese día los cinco tenían `PasswordAuthentication yes` + `PermitRootLogin yes`
  — este documento ya decía "sólo con llave" y era falso — y la producción
  estaba bajo fuerza bruta como root (5,500 intentos fallidos en 3 horas). Ninguna
  contraseña llegó a aceptarse. Drop-in `/etc/ssh/sshd_config.d/00-solo-llave.conf`
  (`PasswordAuthentication no`, `PermitRootLogin prohibit-password`).
  **Rollback:** borrar ese archivo y `systemctl reload ssh`.
  Llaves en uso: la del dueño (Mac) y `ci@aijusticia` (162, 66, storage).
- Un VPS que no está en este runbook entra a 182 por SSH: llave
  `root@vps3610288.trouble-free.net`, desde 162.35.184.145 (Interserver), una
  sesión cada ~9 segundos. Está autorizado en el `authorized_keys` de 182 y
  **el dueño lo confirmó como propio (23-nov-2026)**. Si se cancela 182, ese
  trabajo empezará a fallar: revisarlo antes.
- El :6234 del VPS es HTTP plano — solo aceptable porque viaja entre
  servidores propios; si se expone a internet directo, poner TLS o restricción
  por IP en nginx (`allow 192.227.167.147; deny all;`)
- PostgreSQL de producción: localhost + 66.154.100.25 únicamente (scram).
- La frase de recuperación NUNCA sale del navegador del usuario (solo hash Argon2/PBKDF2 en DB)
- Bóveda de archivos: cifrada en cliente (fase C)
- Tokens de dispositivo: SHA-256 hasheados en `actores.token_dispositivo_hash`
- Google OAuth: listo pero inactivo — requiere `NEXT_PUBLIC_GOOGLE_CLIENT_ID` +
  `GOOGLE_CLIENT_SECRET` en el VPS (`/opt/aijusticia/app/.env.production`) y
  rebuild; callback: `https://aijusticia.mx/api/auth/google/callback`

---

## 8. Pendientes conocidos
- [x] ~~Decidir retención del storage~~ — 10 dumps (23-nov-2026).
      `/usr/local/bin/backups_retention.sh` + `/etc/cron.d/backups-retention`
      en el storage; copias en `infra/storage/`.
- [ ] **Cosecha de gacetas estatales en producción**: instalar/reescribir el
  scheduler de fuentes (`aijusticia-ingest.timer` sólo existió en 182).
- [ ] **Refresco automático de leyes federales** (LeyesBiblio): hoy es manual.
- [ ] Cancelar el VPS de 182 (su contenido útil ya está en producción).
- [ ] DNS aijusticia.com.mx → 192.227.167.147 (Caddy ya listo)
- [ ] Google OAuth: crear proyecto Google Cloud + secrets
- [ ] Fase C: bóveda cifrada de documentos (UI + WebCrypto)
- [ ] Fase D: compartir dossiers con abogados + audit log + directorio
- [x] ~~Monitoreo externo~~ — CI monitor cada 30 min, integral, con alertas deduplicadas
- [x] ~~Respaldos de la DB~~ — diario, verificado, con réplica off-site
- [ ] CPT Tlamatini v1: exportar el corpus desde 162 (`prep_cpt_completo.py`)
- [ ] Voz (TTS/STT) en el chat — sesión 3 del plan de rediseño
- [ ] RackNerd (Caddy): disco al 80% y swap casi lleno
