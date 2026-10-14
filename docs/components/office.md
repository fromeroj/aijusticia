# Componente: Office (piloto despacho — Nextcloud + Collabora)

**Qué es**: la oficina digital del despacho piloto — archivos, edición colaborativa
(OOXML en browser), plantillas, calendario. Integra con dossiers del engine.
**Vive en**: `office/` (ex `pilot/`). **Corría en**: Mac Docker (`aijusticia-pilot-*`: nextcloud:31-apache + collabora + postgres + redis).
**Estado**: EN MIGRACIÓN a 162 — ver `office/compose-oficina-server.yml` (destino `/opt/aijusticia/oficina/`, :8080, trusted domains `162.35.113.166` + `oficina.aijusticia.mx`).

## Plan de migración (14-oct)
1. Compose server ya existe (credenciales a igualar con las del Mac: `nextcloud_pilot_2026`).
2. Volumen `aijusticia-pilot_nc_data` → rsync a `/opt/aijusticia/oficina/html` (dockervolume del Mac → tar → scp).
3. `pg_dump` del `aijusticia-pilot-db-1` → restore en el db del compose.
4. `docker compose up` en 162 → verificar login en `http://162.35.113.166:8080`.
5. Apagar (NO borrar) los contenedores del Mac.
6. Cuando el storage server (161.129.70.21) viva: NFS `soft` para el datadir.
7. Opcional: subdominio `oficina.aijusticia.mx` en Caddy (RackNerd) → 162:8080.

## Reglas
- La bóveda cifrada del cliente (WebCrypto, fase C del spec) no depende de este stack.
- El stack completo es descartable/reconstruible salvo `html/` (archivos del usuario) y la DB.
