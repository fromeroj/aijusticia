# AI Justicia — Plan de Seguridad e Integridad Unificado

*Septiembre 2026 · Auditoría + plan por fases*

---

## 1. Auditoría honesta (estado al 2026-09-05)

### 🔴 CRÍTICO — corregido hoy

| Riesgo | Estado | Fix aplicado |
|---|---|---|
| **`/admin/*` del engine públicos** (stats, harvesters, preguntas, sources — información completa del sistema sin autenticación) | EXPUESTO en producción | ✅ **Basic auth nginx** en todos los `/admin/*` (admin / `Soberania2026!`) — hoy |

### 🟠 ALTO — corregir esta semana (S2)

| Riesgo | Detalle | Fix |
|---|---|---|
| **Secrets en git** | `aijusticia2016`, `tlamatini2026`, `nc_oficina_2026` en 10+ archivos del repo y compose | `.env` real fuera de git (`.gitignore`), secrets de compose via `${VARS}` de un `.env` no versionado; rotar TODAS las contraseñas comprometidas |
| **Contraseñas débiles/known en DB** | Postgres `aijusticia2016`, NC admin `tlamatini2026` | Rotar: NC admin password → nueva fuerte; Postgres → contraseña aleatoria 32 chars en `.env` con permisos 600 |
| **NFS `no_root_squash` sin cifrado** | Storage monta el corpus con root total | `root_squash` + export solo a la IP del web (ya está) + evaluar wireguard entre nodos |
| **CORS wildcard en WebDAV** | `Access-Control-Allow-Origin: *` que pusimos para el panel | Reducir a los orígenes reales: `https://aijusticia.mx`, `https://oficina.konen.guru` |
| **Sin rate limiting** | `/query/stream` puede ser drenado (costo MiniMax) | `limit_req` en nginx: 10 req/min por IP en /query; 5/min en /auth/* |

### 🟡 MEDIO — fase F1 (con el refactor R1-R5)

| Riesgo | Detalle | Fix |
|---|---|---|
| Sesiones ciudadano sin firma | localStorage = cualquier script puede "ser" otro actor | **JWT de vida corta (15min) + refresh** — R3 del refactor |
| Engine confía en el frontend | `/dossiers/{id}` accesible con solo saber el UUID | El JWT lleva el actor; middleware `deps.py` verifica ownership |
| NC admin = cuenta única | Todo el despacho corre como admin | Crear usuarios reales por rol: socios/asociados/pasantes (NC groups) |
| Collabora con credenciales débiles | cola/colabora2026 | Rotar + `--o:admin_console.enable=false` |
| Sin backups automáticos de la DB RAG | Un disco muerto = perder el índice | pg_dump diario → storage NFS, retención 7d + pg_basebackup semanal |
| App-password del panel en sessionStorage | Credencial permanente, no sesión | Migrar a JWT del engine emitido vía OAuth NC (NC como IdP) |

### 🟢 BAJO/aceptado — documentar

| Ítem | Decisión |
|---|---|
| SSH root entre máquinas | Aceptado (fleet privado); 2FA en el edge si crece |
| Frase ciudadano irrecuperable | Por diseño (privacidad estructural), documentado en UX |
| TLS del edge (Caddy) | Automático Let's Encrypt, correcto |
| DNSSEC roto de aijusticia.mx | Pendiente del registrar; los servicios críticos ya usan konen.guru |

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
│  anónima)      │  │   │         bufete?, rol?}   │
├────────────────┤  │   └──────────────────────────┘
│ NC OAuth2      │──┘        │
│ (despacho:         ▼        ▼
│  cloud u on-prem)  RLS Postgres  →  datos del bufete
│                    sin bufete_id →  solo dossiers propios
```

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
