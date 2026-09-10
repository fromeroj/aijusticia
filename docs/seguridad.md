# AI Justicia — Plan de Seguridad e Integridad Unificado

*Septiembre 2026 · Auditoría + plan por fases · **actualizado 2026-09-06 tras S3 (F1 del plan v2)***

---

## 1. Auditoría honesta (estado al 2026-09-06)

### 🔴 CRÍTICO — ✅ RESUELTO

| Riesgo | Estado | Fix aplicado |
|---|---|---|
| **`/admin/*` del engine públicos** | ✅ | Basic auth nginx en todos los `/admin/*` + `X-Robots-Tag: noindex` en páginas internas (2026-09-05/06) |
| **`POST /dossiers` sin ruta nginx** (caía a Next.js por el pattern `/dossiers/` con slash) | ✅ | `location = /dossiers` en nginx — el "Guardar como caso" por URL pública quedó roto silenciosamente hasta 2026-09-06 |

### 🟠 ALTO — ✅ RESUELTO (S2, 2026-09-05)

| Riesgo | Estado | Fix aplicado |
|---|---|---|
| **Secrets en git** | ✅ | `.env` fuera de git; contraseñas rotadas (Postgres 32-char, NC admin reseteado vía API PHP; nuevas en `/root/.secrets_rotadas`) |
| **Contraseñas débiles/known en DB** | ✅ | Ídem; JWT_SECRET fuerte generado (`openssl rand -hex 32`) |
| **NFS `no_root_squash` sin cifrado** | 🟡 parcial | Export restringido a la IP del web; wireguard pendiente si crece el fleet |
| **CORS wildcard en WebDAV** | ✅ | Restringido a `aijusticia.mx` / `oficina.konen.guru` |
| **Sin rate limiting** | ✅ | `limit_req` nginx: api 10/min burst 5 en `/query`; auth burst 3 en `/auth/*` |

### 🟡 MEDIO — ✅ mayormente RESUELTO (S3 = F1 plan v2, 2026-09-06)

| Riesgo | Estado | Fix aplicado |
|---|---|---|
| Sesiones ciudadano sin firma | ✅ | **JWT para ciudadanos**: `/entrar`, onboarding y conversión chat→caso canjean frase/dispositivo/Google por par access(15m)+refresh(30d rotatorio). `lib/auth.ts` con auto-refresh; `aij_sesion` plana eliminada del flujo |
| Engine confía en el frontend | ✅ | `GET /dossiers/{id}` y consentimiento exigen JWT + ownership (`tiene_acceso`); consentimiento SOLO el dueño |
| **Secuestro por `/auth/dispositivo/registrar`** (vincular token a cualquier actor_id sin prueba) | ✅ | Prueba de posesión obligatoria: JWT del mismo actor o frase válida (disponible solo al crear el caso) |
| **`/auth/google` sin verificar firma** | ✅ | El engine valida el `id_token` contra Google (tokeninfo): audiencia, expiración, email_verified. El `google_sub` enviado a mano ya no se acepta. Handoff de tokens al frontend vía code de un solo uso (60s) — jamás por URL |
| **`/jobs/{id}` enumerable filtraba consultas ajenas** | ✅ | Ya no devuelve `consulta` |
| **SSRF vía `webhook_url`** | ✅ | Validador pydantic: solo https, hosts públicos (bloquea localhost/privadas/link-local) |
| **Frase con sal estática + duplicados en la lista** | ✅ | `frase_hash_saltado` con sal por actor (`frase_salt`); migración de actores legados al vuelo en el siguiente login; lista de palabras deduplicada. `frase_hash` queda solo como índice determinístico de lookup |
| NC admin = cuenta única | 🟡 | Existe usuario `demo` vinculado al bufete piloto (`actores.nc_login`); usuarios por rol completos en F2 |
| ~~Collabora con credenciales débiles~~ | ✅ RESUELTO (2026-09-06) | Credenciales rotadas (aleatorias en `/root/.secrets_rotadas`), admin console DESACTIVADO (`--o:admin_console.enable=false`): sin creds → 403, creds viejas → 403. WOPI allowlist `aliasgroup1=oficina.konen.guru` verificada; `post_allow=0.0.0.0/0` correcto en topología proxy (los navegadores guardan vía POST público) |
| Backups automáticos DB RAG | ✅ | pg_dump diario 4am → NFS, retención 7d |
| ~~App-password del panel en sessionStorage~~ | ✅ | JWT via=nc (2026-09-05) |

### 🟢 BAJO/aceptado — documentar

| Ítem | Decisión |
|---|---|
| SSH root entre máquinas | Aceptado (fleet privado); 2FA en el edge si crece |
| Frase ciudadano irrecuperable | Por diseño (privacidad estructural), documentado en UX |
| TLS del edge (Caddy) | Automático Let's Encrypt, correcto |
| DNSSEC roto de aijusticia.mx | Pendiente del registrar; los servicios críticos ya usan konen.guru |
| Login Google no configurado en prod | `GOOGLE_CLIENT_ID` vacío → engine responde 503 (deshabilitado explícito) |

---

## 2. Modelo de identidad unificado (el diseño)

```
┌─────────────────── TIER CIUDADANO (sin cuenta) ───────────────────┐
│ Identidad = posesión del secreto, no registro                      │
│   • Frase 12 palabras (raíz, bcrypt)                              │
│   • Token dispositivo (conveniencia)                              │
│   • Google sub (llave, correo nunca al corpus)                    │
│ Emisión: JWT corto {sub: actor_id, tier: ciudadano, exp: 15min}   │
└────────────────────────────────────────────────────────────────────┘
┌─────────────────── TIER DESPACHO (con cuenta NC) ────────────────┐
│ Identidad = Nextcloud del despacho (SSO)                           │
│   • Login NC (ldap/local) con roles: socios/asociados/pasantes    │
│   • OAuth2 NC → JWT del engine {sub, bufete, rol}                 │
│   • RLS Postgres: SET app.bufete_id = claim del token             │
└────────────────────────────────────────────────────────────────────┘
                    │                                    │
                    ▼                                    ▼
         Engine: middleware deps.py valida JWT en CADA ruta
         (ciudadano → dossiers propios; despacho → RLS bufete)
```

**Un solo verificador** (el engine), **dos emisores** (frase para ciudadanos, NC para despachos), **un token** (JWT). El panel NC ya tiene sesión heredada; el JWT se agrega para las llamadas API del engine.

---

## 3. Integridad del corpus (anti-tamper)

Del spec c5-legal (práctica ya adoptada), formalizada:

| Medida | Implementación | Cuándo |
|---|---|---|
| **Snapshot hashes** | Cada fuente externa (LawInstruct, lex-mx) registra sha256 del snapshot exacto usado | ya en `harvest_scripts` (ampliar a sha256 de archivos) |
| **Manifest de entrenamiento** | `training_manifest` (tabla ya existe): cada corpus exportado lleva lista de fuentes + hash + fecha | al armar el export CPT |
| **Inmutabilidad de raw** | Los JSONL de cosecha son append-only (nunca reescribir; correcciones = archivos nuevos) | política de escritura |
| **Checksums por documento** | `INSERT` calcula md5 del texto; alteración detectable | al R5 (migración con columna checksum) |
| **Procedencia del modelo** | Tlamatini lleva embedded: hash del training manifest + fecha + fuentes | al terminar CPT |

---

## 4. Plan de ejecución

| Sprint | Acciones | Estado |
|---|---|---|
| **HOY** | ✅ Basic auth /admin/* | hecho |
| **S2 (esta semana)** | Rotar secrets; .env fuera de git; CORS restringido; rate limiting; backups DB diarios | |
| **F1 refactor** | JWT (R3) + deps.py + RLS (R4) + usuarios NC por rol | |
| **F2** | OAuth NC→engine para panel; Collabora lockdown; logs de auditoría unificados (NC activity + trazas engine) | |
| **F3** | Stack on-prem endurecido: todo lo anterior aplicado al paquete despacho | |

---

## 5. Lo que NO hacemos (decisiones deliberadas)

- **No WAF empresarial / SOC2 todavía**: el producto es piloto; el basic auth + rate limit + JWT cubren el riesgo real actual
- **No cifrado de disco en VPS**: el riesgo real es la red (TLS ✓) y el acceso (SSH + auth); LUKS en VPS da falsa seguridad contra el proveedor
- **No 2FA para ciudadanos**: la frase de 12 palabras YA es el segundo factor (posesión + conocimiento según camino)

---

## 6. Corrección del modelo: despacho también en nube (2026-09-05)

**Realidad del mercado**: muchos despachos chicos (2-10 abogados) NO tienen máquina ni IT.
El tier despacho debe ofrecer dos modos con el MISMO código:

| Modo | Dónde corre | A quién sirve | Auth |
|---|---|---|---|
| **Despacho Cloud** | Nuestra instancia (oficina.konen.guru) | Despachos sin hardware; onboarding en minutos | Login NC hospedado → OAuth → JWT engine |
| **Despacho On-Prem** | Su servidor (docker-compose) | Despachos con requisito de soberanía/secreto profesional | Login NC local → OAuth → JWT engine local |

**La factura diferencial es la privacidad del dato, no la funcionalidad**: en Cloud, los
documentos del caso viven en NUESTRA infra (somos encargados LFPDPPP art. 21, contrato
de encargamiento); en On-Prem, en la del despacho (cero transferencia). El adapter
privado en Cloud entrena en su tenant aislado (RLS) pero dentro de nuestra infra —
es el trade-off que Harvey/Legora ya venden, pero con derecho mexicano nativo.

### 6.1 Modelo de identidad final (3 emisores, 1 verificador)

```
EMISORES                              VERIFICADOR
┌────────────────┐
│ Google OAuth   │──┐
│ (ciudadano +   │  │   ┌──────────────────────────┐
│ abogado solo)  │  ├──▶│ Engine: deps.py          │
├────────────────┤  │   │ valida JWT en CADA ruta  │
│ Frase/Disposit.│──┤   │                          │
│ (recuperación  │  │   │ claims: {sub, tier,      │
│  anónima)      │  │   │         bufete?, rol?,   │
├────────────────┤  │   │         dossier?}        │
│ NC OAuth2      │──┘   └──────────────────────────┘
│ (despacho:         ▼        ▼
│  cloud u on-prem)  RLS Postgres  →  datos del bufete
│                    sin bufete_id →  solo dossiers propios
```

**M1 — Modelo de acceso a dossiers (implementado 2026-09-06, S3):** el dossier
pertenece SIEMPRE a quien lo crea; abogados y despachos acceden por grants
revocables en `dossier_accesos` (rol lectura|edicion, otorgado_por, historial
permanente = auditoría LFPDPPP). Reasignar = revocar + otorgar.
`tiene_acceso(dossier, actor, bufete?)` es la única puerta: devuelve
`dueño | edicion | lectura | None` y la usan los endpoints para autorizar.
La API pública de grants (directorio, compartir, revocar desde la UI) es F4
del plan v2.

### 6.2 Multi-tenancy del Despacho Cloud

Un NC por despacho sería limpio pero costoso. Arquitectura pragmática:

- **1 instancia NC** con usuarios agrupados por despacho (NC groups = bufete)
- Carpetas raíz por bufete: `/Bufetes/{slug}/Casos/...` con ACLs NC por grupo
- **RLS en Postgres del engine** por `bufete_id` del JWT (nunca del request)
- Nextcloud "bulk upload" / provisioning API crea el bufete + usuarios al registro
- El adapter LoRA privado: en Cloud entrena con los datos del tenant (RLS); en On-Prem
  con los datos locales. El adapter general NUNCA ve datos de bufete.

### 6.3 Emisión del JWT — especificación

```
POST /auth/token
{
  "via": "google" | "frase" | "dispositivo" | "nc_oauth",
  ...credenciales según vía...
}

→ 200 { "access_token": "<JWT>", "expires_in": 900, "refresh_token": "<JWT>" }

claims: {
  sub: actor_uuid,
  tier: "ciudadano" | "abogado" | "despacho",
  bufete: uuid | null,      // solo tier despacho
  rol: "socio" | "asociado" | "pasante" | null,
  iat, exp
}
```

- `access_token`: 15 min (Header `Authorization: Bearer`)
- `refresh_token`: 30 días rotativo (revocable: tabla `refresh_tokens` con hash)
- Firma: HS256 con `JWT_SECRET` del `.env` (rotable sin invalidar actores)
- El refresh detecta dispositivo nuevo → exige re-emisión con credencial raíz
