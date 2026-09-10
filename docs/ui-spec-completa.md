# AI Justicia — Especificación Completa de la Interfaz

*Septiembre 2026 — para rediseño. Este documento describe TODO lo construido, todo lo especificado, y las reglas de cada pantalla.*

---

## 1. Los usuarios y qué pueden hacer

### 1.1 Ciudadano (anónimo → con caso)

**Identidad:** frase de 12 palabras (o Google OAuth). Sin email obligatorio, sin registro.

| Acción | Dónde | Estado |
|---|---|---|
| Consultar gratis sin cuenta | Chat público | ✅ |
| Convertir chat → caso (frase) | Modal en chat | ✅ |
| Volver a entrar (frase / Google / dispositivo) | /entrar | ✅ |
| Ver sus casos (propios + compartidos) | /casos | ✅ |
| Abrir caso → expediente + documentos + notas | /chat (auto-abre expediente) | ✅ |
| Adjuntar documentos (PDF, imagen → OCR) | Clip en chat / subir en expediente | ✅ |
| Subir como nueva versión de doc existente | Botón "versión nueva" | ✅ |
| Compartir caso (código/QR/WhatsApp) | Expediente → "Invitar" | ✅ |
| Aceptar/rechazar solicitudes de acceso | Expediente → tarjeta pendiente | ✅ |
| Revocar acceso | Expediente → "revocar" | ✅ |
| Salir de caso compartido | /casos → "salir" | ✅ |
| Dar/quitar consentimiento de entrenamiento | /cuenta | ✅ |
| Preferencias de apertura de archivos | /cuenta | ✅ |
| Preguntar a Izel (con contexto del caso) | Chat con dossier_id | ✅ |

### 1.2 Abogado individual

**Identidad:** frase de 12 palabras. Tiene un bufete de una persona automáticamente (M2).

Todo lo del ciudadano MÁS:

| Acción | Dónde | Estado |
|---|---|---|
| Entrar a /app | Login con frase | ✅ |
| Ver casos propios + compartidos conmigo | /app → selector de casos | ✅ |
| Crear caso nuevo | /app → "Nuevo caso" | ✅ |
| Ver documentos del caso (bóveda) | /app → tab Documentos | ✅ |
| Escribir notas del caso (visible a participantes) | /app → tab Notas | ✅ |
| Ver timeline del caso | /app → tab Timeline | ✅ |
| Consultar Izel con contexto del caso | /app → Izel | ✅ |
| Generar documento desde plantilla | /app → Generar | ✅ |
| Ver versiones de documentos | /app → badge v1/v2 | ✅ |

### 1.3 Despacho (firma)

**Identidad:** usuario/contraseña de Nextcloud (hospedado en oficina.konen.guru o on-premise).

Todo lo del abogado MÁS:

| Acción | Dónde | Estado |
|---|---|---|
| Invitar miembros a la firma (código) | /app → "+ Invitar miembro" | ✅ |
| Miembro se une por código | /unirse | ✅ |
| Asignar caso a miembro (responsable/abogado/pasante) | /app → tab Equipo | ✅ |
| Quitar asignación | /app → Equipo → quitar | ✅ |
| Vetar miembro (muro ético) | /app → Equipo → vetar | ✅ |
| Marcar caso confidencial | /app → Equipo → candado | ✅ |
| Promover documento → plantilla (PII-scan) | /app → Documentos → "→ plantilla" | ✅ |
| Ver/editar en Collabora (Nextcloud) | Link "Abrir en Nextcloud" | ✅ |

### 1.4 Empresa (futura)

Igual que despacho pero: identidad por dominio de correo verificado, casos pertenecen a la organización (no al empleado), admin rotativo, verificación documental opcional.

### 1.5 Administrador del sistema

Acceso físico al server (SSH). Puede ver todo via DB directa pero NO via la app (sin grant). Puede recibir un grant de cualquier usuario para ver su caso formalmente (auditado).

---

## 2. Las pantallas y su contenido

### 2.1 `/` — Landing público
Marketing: hero, 3 rutas (ciudadano/abogado/despacho), features, pricing, CTA.
CTA según sesión: sin sesión → "Entrar" | con sesión → "Volver a mi chat"

### 2.2 `/chat` — Chat con Izel
**El corazón del producto para ciudadanos.**

Componentes:
- **Header**: logo Izel · modo (Ciudadano/Abogado) · badge expediente activo · "Guardar como caso" (si anónimo) · Casos · Cuenta · Salir
- **Área de mensajes**:
  - Burbujas usuario/asistente
  - AnalysisCard (materia detectada, etapas con timing)
  - ClarifyCard (preguntas de contexto con chips de opciones)
  - ReferencesCard (pasajes citados expandibles + export PDF + WhatsApp)
  - AbstentionCard (cuando no sabe, explica por qué)
  - ConsentCard (opt-in entrenamiento tras primera respuesta útil)
  - ConsentNotice (modo abierto, bajo el input)
- **ExpedientePanel** (drawer lateral derecho, auto-abre si hay caso):
  - Resumen del expediente (materia, jurisdicción, hechos)
  - Documentos (lista con versión, badge OCR/texto, "versión nueva", click=descargar)
  - Notas del caso (conversación, autor, fecha)
  - Invitar (código + QR + WhatsApp, aceptar/rechazar, revocar, accesos activos)
- **InputBar**: clip adjuntar · textarea auto-expandible · enviar/parar · disclaimer legal

### 2.3 `/entrar` — Login
- One-tap: "Continuar en este dispositivo" (si hay token guardado)
- Google: "Continuar con Google" (si GOOGLE_CLIENT_ID configurado)
- Frase: textarea de 12 palabras → "Entrar a mi caso"
- Handoff de Google: callback → code de un solo uso → tokens → redirect

### 2.4 `/casos` — Mis casos
Lista de tarjetas:
- **Propios**: icono carpeta, nombre, materia, estado
- **Compartidos contigo**: icono compartir, quién compartió, tu rol, botón "salir"
- Click → abre en /chat con el expediente auto-visible

### 2.5 `/cuenta` — Mi cuenta
- Tarjeta Izel (acceso directo al chat)
- Consentimiento LFPDPPP: toggle otorgado/revocado
- Preferencias de archivo: abrir en editor / solo descargar / descargar y abrir
- Cerrar sesión

### 2.6 `/app` — App de trabajo (abogados + despachos)

**Layout actual:** header + grid 2 columnas (generador | Izel)

**Elementos:**
- **Header**: logo · usuario · rol · "+ Invitar miembro" (admin) · Salir · Refrescar
- **Login** (si sin sesión): tabs Despacho (NC user/pass) | Abogado (frase)
- **Selector de casos**: dropdown con propios (sin icono) y compartidos (📂)
- **Generador de documentos**:
  - Select plantilla (por materia)
  - Select caso destino
  - Variables detectadas (inputs dinámicos)
  - Botón generar → job → poll → resultado con link NC
  - Info PII detectada en el resultado
  - "Nuevo caso" (nombre + materia)
- **Vista de caso** (4 tabs al seleccionar caso):
  - **Timeline**: eventos cronológicos (creación, docs, accesos, asignaciones, notas)
  - **Documentos**: bóveda del caso, click descargar, "→ plantilla" para .docx
  - **Notas**: lista + form agregar, autor visible
  - **Equipo** (admin): asignar miembro + rol en caso, quitar, vetar, confidencial
- **Izel · consulta jurídica**: textarea → respuesta anclada (con contexto del caso si seleccionado)

### 2.7 `/reclamar` — Canjear invitación de caso
- Input código (o pre-cargado por URL ?c=XXX)
- Campo etiqueta opcional ("Berto — comprador")
- Sin sesión → link a /app?volver=/reclamar?c=CODE
- Con sesión → canjea → "Solicitud enviada, espera aceptación del dueño"

### 2.8 `/unirse` — Canjear invitación de firma
- Input código de 8 chars
- Sin sesión → link a /app?volver=/unirse?c=CODE
- Con sesión → canjea → "¡Bienvenido a la firma!"

### 2.9 Marketing páginas
- `/para-ti` — landing ciudadano (features, pricing, CTA)
- `/abogados` — landing abogado
- `/despachos` — landing despacho (CTA → /app)
- `/tlamatini` — landing del modelo soberano
- `/tecnologia` — B2B: soberanía, adapters, PII-scan

### 2.10 Internas (basic auth nginx)
- `/admin` — dashboard corpus (fuentes, health, harvesters, stats)
- `/qa/preguntas` — explorador de preguntas de evaluación
- `/test-results` — resultados del batch RAG

---

## 3. Flujos clave (step by step)

### 3.1 Ciudadano nuevo → caso
```
/ → /para-ti → "Preguntar ahora" → /chat (anónimo)
→ pregunta → Izel responde con citas → useful → ConsentCard
→ "Guardar como caso" → modal → frase (12 palabras) → verificar 3 → sesión creada
→ expediente auto-visible con documentos/notas/compartir
```

### 3.2 Compartir caso ciudadano → abogado/despacho
```
/chat → expediente → "Invitar a mi abogado"
→ elegir tipo: [Asesor | Contraparte] × [Persona | Despacho]
→ "Generar código" → código + QR + WhatsApp
→ abogado entra a /reclamar?c=CODE → canjea
→ ciudadano ve "solicita acceso" → [Aceptar] 
→ abogado ve el caso en /app
```

### 3.3 Miembro se une a firma
```
/admin de firma → /app → "+ Invitar miembro" → código 8 chars
→ abogado nuevo → /unirse?c=CODE → "Unirme a la firma" → bienvenido
→ casos asignados aparecen en /app
```

### 3.4 Promover documento → plantilla
```
/app → seleccionar caso → tab Documentos
→ click "→ plantilla" en un .docx
→ job: PII-scan → anonimiza → sube a NC /Plantillas/Importadas/
→ "✓ Plantilla creada: convenio_anon.docx (1 datos anonimizados)"
```

### 3.5 Iteración de acta constitutiva (el caso de uso real)
```
Pari: crea caso → invita a Max (despacho ptrabogados)
Pari: sube acta v1 → describe lo que quiere
Max: entra a /app → ve caso compartido → lee documento
Max: escribe nota con correcciones (SAPI bursátil vs no bursátil, jerarquía)
Pari: corrige → sube acta v2 (versión nueva de v1)
Max: revisa v2 → escribe nota OK
→ timeline del caso registra TODO: docs, notas, accesos, versiones
→ cualquiera puede preguntar a Izel con contexto del acta
```

---

## 4. Modelo de datos visible en la UI

| Entidad | Dónde aparece | Qué muestra |
|---|---|---|
| **Dossier (caso)** | /casos, /app selector | Nombre, materia, estado, origen (propio/compartido) |
| **Expediente** | Drawer en /chat | Materia, jurisdicción, hechos estructurados (dict) |
| **Documento** | Expediente/docs tab | Nombre, versión, tamaño, método texto (OCR/pdf), fecha |
| **Versión de documento** | Badge v1/v2 | Link entre versiones (version_de) |
| **Nota** | Expediente/notas tab | Texto, autor, fecha — la conversación del caso |
| **Acceso (grant)** | Expediente/compartir | Beneficiario, rol, relación (parte/asesor), estado |
| **Invitación** | Expediente/compartir | Código, estado (activa/solicitada/usada), expiración |
| **Asignación** | /app/equipo | Actor, rol en caso (responsable/abogado/pasante), rol en firma |
| **Veto (muro ético)** | /app/equipo | Actor vetado, razón — bloqueo absoluto |
| **Miembro de firma** | /app/equipo | Actor, rol (admin/abogado/pasante), estado |
| **Timeline** | /app/timeline | Todos los eventos del caso en orden cronológico |

---

## 5. Reglas de seguridad que la UI debe respetar

| Regla | Impacto en UI |
|---|---|
| Solo el dueño invita | Botón "Invitar" solo para dueño; grantees no ven el botón |
| Handshake obligatorio | Siempre: código → canje → aceptación. Nunca acceso directo |
| Revocación instantánea | El caso desaparece de la lista del revocado en el próximo refresh |
| Muro ético prevalece | El vetado no ve el caso NI aparece en la lista de asignables |
| Caso confidencial | Ni los admins no asignados lo ven en la lista |
| Consentimiento separado | Toggle de entrenamiento NO está empaquetado con nada más |
| Frase nunca en email | Link de un solo uso (15 min) que muestra la frase |
| Códigos de un solo uso | Cada invitación se usa una vez, luego "usada" |

---

## 6. Izel — el asistente

**Identidad:** Izel (náhuatl: "única"). Siempre presente, siempre con nombre.

**Dónde aparece:**
- Chat ciudadano (header: "Izel · AI Justicia / Tu asistente legal")
- /app (columna derecha: "Izel · consulta jurídica")
- Empty state: "Hola, soy Izel"

**Qué puede hacer:**
- Responder consultas jurídicas con citas verificadas
- Usar el contexto del caso (expediente + documentos con OCR)
- Abstenerse honestamente cuando no sabe
- Distinguir: "no tengo la norma" (Caso B) vs "esto requiere un abogado" (Caso A)

**Qué NO es (footer legal):**
"AI Justicia e Izel ofrecen información jurídica general verificada. No son abogados ni sustituyen asesoría legal profesional."

---

## 7. Problemas conocidos de la UI actual (para el rediseño)

| Problema | Detalle |
|---|---|
| **Chat vacío al abrir caso existente** | /casos → /chat muestra empty state de Izel en vez del contenido del caso |
| **Expediente oculto** | El drawer requiere click en "Ver mi expediente" — debería ser vista por defecto |
| **Sin navegación global** | No hay navbar global; cada página dibuja su propio header |
| **/app es dos columnas fijas** | No es responsive; no hay vista móvil |
| **Sin búsqueda de casos** | Con >5 casos, el dropdown se vuelve inmanejable |
| **Sin vista unificada de caso** | Ciudadano ve expediente (drawer), abogado ve tabs — inconsistent |
| **Sin indicador de notificaciones** | No sabes si alguien compartió/actualizó sin entrar a mirar |
| **Sin onboarding guiado** | Primera vez en /app: dos dropdowns vacíos, cero explicación |
| **Timeline sin ricos** | Eventos de texto plano; sin avatares, sin iconos por tipo |
| **Documentos sin preview** | Solo nombre + versión; no se ve el contenido sin descargar |
| **Izel sin streaming en /app** | /bufetes/query es síncrono; espera 30-90s sin feedback |
| **Sin modo oscuro** | Todo blanco |
| **Sin móvil** | Layout pensado para desktop |

---

## 8. Referencias de diseño

**Outlook-like (lo que el usuario menciona):**
- Panel izquierdo: lista de casos (como inbox)
- Panel central: contenido del caso seleccionado (documentos, notas, timeline en tabs)
- Panel derecho: Izel/chat contextual
- Header global: búsqueda, notificaciones, cuenta

**Otras referencias del dominio legal:**
- **Clio** (practice management): matter-centric, todo orbita el caso
- **Notion**: flexibilidad de vistas, sidebar navegable
- **Linear**: limpieza, velocidad, modo oscuro, keyboard shortcuts

**Principio rector:** el CASO es el centro de todo. Todo lo demás (Izel, documentos, notas, compartir, timeline) vive DENTRO del caso, no en páginas separadas.
