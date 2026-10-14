# Componente: Auth / Identidad

**Qué es**: acceso progresivo — anónimo → email+password → frase de recuperación.
**Vive en**: `engine/ai_justicia/api/routes/{auth,registro,email}.py` + flujos en `apps/web` (entrar, cuenta, onboarding). Migración de schema: `engine/migrations/006_add_email_auth.sql`.

## Modelo
- `actores` (ciudadanos/abogados/bufetes) con `token_dispositivo_hash` (SHA-256).
- `frase_hash`/`frase_salt`/`frase_hash_saltado` **nullable** (fix 12-oct: el registro con email fallaba por NOT NULL).
- Frase de recuperación NUNCA sale del cliente (Argon2/PBKDF2 en browser; solo hash a la DB).
- Google OAuth: preparado pero inactivo (requiere `NEXT_PUBLIC_GOOGLE_CLIENT_ID` + secret en el VPS + rebuild). Callback: `/api/auth/google/callback`.

## Reglas
- Sin cuentas de terceros para lo crítico; email vía Nextcloud (ver office.md) para notificaciones.
- Tokens de dispositivo revocables por el usuario.
