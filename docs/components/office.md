# Componente: Office (piloto despacho — Nextcloud + Collabora)

**Qué es**: la oficina digital del despacho piloto — archivos, edición colaborativa
(OOXML en browser), plantillas, calendario. Integra con dossiers del engine.
**Vive en**: `office/` (ex `pilot/`). **Corría en**: Mac Docker (`aijusticia-pilot-*`: nextcloud:31-apache + collabora + postgres + redis).
**Estado**: ✅ MIGRADO a 162 (14-oct). Piloto corriendo en `http://162.35.113.166:8080` — ver `office/compose-oficina-server.yml` (destino `/opt/aijusticia/oficina/`, :8080, trusted domains `162.35.113.166` + `oficina.aijusticia.mx`).

## Migración ejecutada (14-oct)
1. Volumen `aijusticia-pilot_nc_data` (293MB comprimido) → `/opt/aijusticia/oficina/html`.
2. `pg_dump` del `aijusticia-pilot-db-1` (352KB) → restore limpio (DB recreada desde cero).
3. ⚠️ Lección: el auto-instalador (`NEXTCLOUD_ADMIN_USER` en compose) reescribió
   `config.php` con `dbuser=oc_admin` y colisionó con el restore — env vars de
   admin ELIMINADAS del compose y `config.php` corregido a `dbuser=nextcloud`.
4. Verificado: `status.php` installed/maintenance-false, login 200, archivos de
   usuario (admin/, demo/) presentes.
5. Contenedores del Mac APAGADOS (volúmenes intactos como rollback).
6. Pendiente: subdominio `oficina.aijusticia.mx` en Caddy → 162:8080.

## 6-nov-2026: datadir de VUELTA a disco local (lección NFS)

El datadir vivía en NFS del storage (148) — ese server (1 vCPU, 933MB RAM)
se ahoga sirviendo NFS (especialmente con la lectura del JSONL de UNAM encima)
→ `nfs: server not responding` en dmesg → workers de Apache **segfault** en
cadena → el office dejó de responder y el monitor externo se puso rojo ~30
corridas seguidas.

Arquitectura final: **app-data crítica en disco local de 162** (161GB libres,
los archivos del piloto son 95MB — no hay razón para NFS); NFS del storage
solo para **bulk tolerante**: backups off-site (escritura 04:00, falla
graceful) y corpus de lectura para CPT. El JSONL de UNAM se copió a disco
local y el ingester lee de ahí.

## Reglas
- La bóveda cifrada del cliente (WebCrypto, fase C del spec) no depende de este stack.
- El stack completo es descartable/reconstruible salvo `html/` (archivos del usuario) y la DB.
