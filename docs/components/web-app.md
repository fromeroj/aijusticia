# Componente: Web App (Next.js)

**Qué es**: aijusticia.mx y laley.com.mx (same-origin, mismo build).
**Vive en**: `apps/web/` (ex `app/`) → deploy `/opt/aijusticia/app` en 162 (systemd `aijusticia-web`, :3000).

## Páginas clave
`/` (landing ciudadano), `/chat` (Izel streaming — consume SSE del engine),
`/estado` (mapa SVG + tarjetas por fuente, lee `/corpus/status`),
`/panel` `/studio` (abogados), `/casos`, `/dossiers`, `/onboarding`, `/unirse`,
`/tlamatini` (landing del modelo), `/qa`.

## SSE
`src/lib/chatStream.ts` — cliente de `/chat/stream`: eventos token/laws/done/reset.

## Deploy
```bash
rsync -az --exclude node_modules --exclude .next apps/web/ root@162.35.113.166:/opt/aijusticia/app/
ssh root@162.35.113.166 "cd /opt/aijusticia/app && NODE_OPTIONS=--max-old-space-size=1536 npm run build && systemctl restart aijusticia-web"
```
⚠️ Build consume ~1.5GB heap — en el VPS con 11GB RAM ok.

## Fronteiras
Nunca toca la DB. Todo vía API same-origin. Sin NEXT_PUBLIC_API_URL (vacío = same-origin).
