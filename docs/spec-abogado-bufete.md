# AI Justicia — Spec: Interfaz Abogado / Bufete
## Sistema de trabajo jurídico con política de datos por diseño

*v1.0 — Septiembre 2026 · Basado en análisis de Legora, Harvey, y requerimientos LFPDPPP/CDF*

---

## 1. Filosofía de diseño

**El sistema espeja cómo un despacho mexicano ya funciona** — pero digitalizado:

- El **caso** (expediente) es la unidad de trabajo, como en papel
- La **plantilla** (acta, contrato, demanda tipo) es activo de la FIRMA, no del caso
- El **conocimiento** (precedentes, memos, estrategias) se acumula y se hereda
- El **dato personal del cliente** es tuyo (del ciudadano) y confidencial por ley — ingresa al caso, jamás a la base de la firma

El resultado: cada despacho construye su **cerebro institucional** — cuando un asociado se va, el conocimiento se queda.

---

## 2. Modelo de datos — las cuatro capas de información

```
┌─────────────────────────────────────────────────────┐
│ CAPA 1: CASO/EXPEDIENTE (aislado, confidencial)     │
│  Datos personales del cliente, hechos, documentos   │
│  → Jurisdicción: LFPDPPP datos sensibles + CPF      │
│  → Ciclo de vida: archivable, borrable (autonomía)  │
├─────────────────────────────────────────────────────┤
│ CAPA 2: PLANTILLAS DE LA FIRMA (compartida)         │
│  Actas, contratos, demandas tipo — SIN datos         │
│  personales (se extraen automáticamente)             │
│  → Jurisdicción: propiedad de la firma              │
│  → Ciclo de vida: versionado, nunca se borra         │
├─────────────────────────────────────────────────────┤
│ CAPA 3: CONOCIMIENTO INSTITUCIONAL (compartida)     │
│  Precedentes ganados, memos, estrategias,           │
│  posiciones negociadas, cláusulas preferidas         │
│  → Jurisdicción: secreto profesional                │
│  → Ciclo de vida: acumulativo, curado               │
├─────────────────────────────────────────────────────┤
│ CAPA 4: MODELO (adapter LoRA privado)               │
│  Lo aprendido de TODAS las capas — jamás sale       │
│  del perímetro del bufete                           │
└─────────────────────────────────────────────────────┘
```

### 2.1 Reglas de flujo entre capas (invariantes)

| Regla | Implementación |
|---|---|
| Un documento de caso puede **promoverse** a plantilla solo tras **anonimización automática + revisión humana** | El sistema detecta nombres, RFC, domicilios, cuentas; propone reemplazos `[NOMBRE]`, `[RFC]`, `[DOMICILIO]`; un socio aprueba |
| Una plantilla **jamás** contiene datos personales | Gate automático al guardar: scanner de PII antes de commit |
| El conocimiento institucional se alimenta de casos cerrados con **consentimiento del cliente** | Flujo: caso cerrado → propuesta de extracción de know-how → opt-in → si no, nada sale del caso |
| El adapter (Capa 4) entrena SOLO con Capas 2+3 (+casos con consentimiento explícito) | Invariante del dual-adapter ya documentado |
| Export a Word/PDF de un caso incluye marca de agua con nivel de confidencialidad | Nivel visible siempre |

### 2.2 Inventario de información (requerimiento LFPDPPP art. 21+)

Cada bufete tiene un **inventario vivo** generado por el sistema (exportable como anexo de cumplimiento):

| Inventario | Contenido | Actualización |
|---|---|---|
| Datos personales tratados | Por caso: qué datos, fuente, finalidad, transferencias | automática al crear/modificar |
| Sistemas de tratamiento | Dónde vive cada dato (caso X en instancia Y) | automática |
| Encargados | AI Justicia como encargado (art. 21 LFPDPPP) | contractual |
| Retención | Por tipo: laboral 5 años, civil variable, mercantil 10 | configurable por bufete |
| ARCO/ARDPC | Log de ejercicios de derechos por titulares | automático |

---

## 3. Funcionalidades — el spec

### Módulo A: Casos (expediente digital)

| Función | Detalle |
|---|---|
| **Crear caso** | Desde cero, desde ciudadano compartido (con expediente ya montado), o importado |
| **Vista de caso** | Timeline de eventos, hechos estructurados (el expediente del chat ciudadano), documentos, notas, tareas |
| **Entrevista complementaria** | La IA hace preguntas de hechos faltantes al abogado (como al ciudadano pero en modo técnico) |
| **Retención/archivado** | Al cerrar: retención según política del bufete; el ciudadano puede solicitar borrado total (derecho ARDPC) — el borrado borra datos personales, preserva plantilla/know-how anonimizado ya promovido |

### Módulo B: Documentos con versionado y edición

**El formato de trabajo: Markdown + Git interno.** Cada documento es un repo con historial completo.

| Función | Detalle |
|---|---|
| **Editor Markdown con stylesheet del despacho** | Edición en MD; preview/render con identidad visual de la firma (logo, tipografía, márgenes, memberañas). Export a DOCX/PDF impecable |
| **Versionado por documento** | Git interno: cada save = commit con autor, mensaje, timestamp. Diff visual (redline) entre cualquier par de versiones |
| **Comentarios/anotaciones** | Inline tipo Google Docs: resaltar texto → comentario → hilo; resueltos se archivan con la versión |
| **Redline/compare** | Diff visual con markup de inserción/eliminación estilo track-changes; aceptar/rechazar por hunk |
| **Co-edición** | Edición concurrente (CRDT) entre miembros del bufete en el mismo doc |
| **Promover a plantilla** | Botón "Guardar como plantilla" → PII-scan automático → propuesta de variables (`[NOMBRE]`, `[RFC]`, `[MONTO]`) → revisión → commit a biblioteca de plantillas |
| **Generación desde plantilla** | Seleccionar plantilla + caso → la IA rellena variables desde el expediente → borrador v1 listo para editar |

### Módulo C: Biblioteca (plantillas + conocimiento)

| Función | Detalle |
|---|---|
| **Biblioteca de plantillas** | Por materia (civil, mercantil, laboral…); cada plantilla versionada; uso contado (qué casos la usaron — sin exponer datos) |
| **Biblioteca de cláusulas** | Fragmentos reutilizables con metadata: tipo, materia, riesgo, posición (preferida/fallback/rechazada), nota de negociación |
| **Precedentes de la firma** | Casos cerrados anonimizados: estrategia, resultado, lecciones — buscables |
| **Playbooks** | Guías de decisión por materia: posición estándar, fallback, cuándo escalar al socio |
| **Búsqueda semántica** | "cláusula de penalización que usamos en arrendamientos" → encuentra la cláusula + en qué contratos se usó + cómo negoció |

### Módulo D: Investigación (Tlamatini + RAG)

| Función | Detalle |
|---|---|
| **Investigación anclada** | Como el chat ciudadano pero Nivel1: técnico, con doctrina y jurisprudencia + precedentes de la FIRMA mezclados en el retrieval |
| **Router de modelos** | Trabajo público/anónimo (research web, borradores base) → LLM frontera cloud; todo lo que toca el caso → Tlamatini local. PII-gate clasifica cada entrada (ver arquitectura.md §6) |
| **Cascada verificada** | Para razonamiento complejo: frontera abre anonimizada → Tlamatini fundamenta y ancla contra el corpus → salida con doble firma |
| **Monitores** | Vigilancia de reformas: DOF + gaceta estatal + SJF — si cambia una ley que toca tus plantillas activas, alerta con redline del cambio |
| **Comparador de versiones de ley** | "¿Qué cambió del art. 164 LFT desde 2023?" → diff con fecha de reforma (usamos git-history de lex-mx + DOF) |

### Módulo E: Administración del bufete

| Función | Detalle |
|---|---|
| **Miembros y roles** | Socio (todo), asociado (casos propios + biblioteca lectura), pasante (drafts solo). Permisos por caso |
| **Panel de cumplimiento** | El inventario LFPDPPP exportable, log ARDPC, retenciones configuradas, contrato de encargado |
| **Auditoría** | Quién vio qué, cuándo — especial en casos marcados "solo socios" |
| **Métricas internas** | Tiempo promedio por tipo de documento, uso de plantillas, taux de aceptación de drafts de IA |

---

## 4. El flujo estrella: acta constitutiva

```
Socio crea caso "Const. XYZ SA de CV"
    ↓
Selecciona plantilla "Acta Constitutiva SA (v3.2 — revisada por FGR 2026-03)"
    ↓
La IA rellena: denominación, objeto, capital, accionistas
desde los datos capturados del cliente (Capa 1)
    ↓
Borrador v1 (Markdown, stylesheet del despacho) → revisión del asociado
    ↓
Comentario del socio: "la cláusula de administración es la de
mayoría calificada, no la simple" → cambio de cláusula
desde biblioteca (1 click) → v2
    ↓
Redline v1→v2 aprobado → EXPORT a DOCX con logo del despacho
    ↓
Caso cierra. Sistema pregunta: "¿Promover a plantilla?"
    ↓
PII-scan: elimina nombres, capital real, objeto específico
deja [DENOMINACIÓN], [CAPITAL], [OBJETO]
    ↓
Socio aprueba → Acta Constitutiva v4.0 en biblioteca
con la mejora de la cláusula de administración
    ↓
El adapter del bufete aprende: "en este despacho,
administración = mayoría calificada"
(Capa 4 — jamás sale del bufete)
```

---

## 5. Seguridad y cumplimiento (lo que nos diferencia)

| Requisito | Solución |
|---|---|
| **Secreto profesional (CPF 210-211)** | Opción on-premise: todo corre en infraestructura del despacho. Cero llamadas externas |
| **LFPDPPP datos sensibles** | Inventario automático, consentimientos gestionados, derechos ARDPC implementados, retención configurable |
| **"Zero AI training on your data"** (claim de Legora) | Nosotros vamos más allá: SÍ entrenamos — pero solo tu adapter privado, dentro de tu perímetro. El know-how se queda y compite |
| **Auditoría de acceso** | Log inmutable por caso: quién vio, editó, exportó |
| **Aislamiento inter-bufetes** | Un adapter por firma, datasets separados, verificable técnica y contractualmente |
| **Respaldo y continuidad** | Snapshot diario cifrado; export completo del bufete bajo demanda (los datos del despacho SON del despacho) |

---

## 6. Competencia — dónde ganamos y dónde no

| | Harvey/Legora ($300-500/asiento) | AI Justicia despachos |
|---|---|---|
| Derecho mexicano | Superficial | Nativo (RAG 3B+ tokens + Tlamatini) |
| Despliegue | Solo nube (SaaS) | On-premise opcional |
| Entrenamiento con know-how | "Zero training" | Adapter privado por bufete |
| Precio | USD 300-500/mes/asiento | Desde ~$2,000 MXN/mes/asiento (a definir) |
| Word add-in | Sí | Fase 2 (roadmap) |
| Frontera para research/base | Propietaria integrada | Router multi-LLM con PII-gate (arquitectura §6) |
| Agentic workflows maduros | Sí | Fase 3 (roadmap) |
| Español mexicano + LFPDPPP nativo | No | Sí |

**Estrategia**: no competir en agentic-corporativo-global; competir en **profundidad mexicana + soberanía + precio local**. El despacho mediano mexicano (5-30 abogados) es nuestro beachhead — Harvey no lo atiende.

---

## 7. Fases de implementación

| Fase | Alcance | Depende de |
|---|---|---|
| **F1 — MVP (Q4 2026)** | Casos + documentos MD versionados + 3 plantillas base + compliance básico + chat Nivel1 | Lo existente |
| **F2 — Biblioteca (Q1 2027)** | Promoción a plantilla con PII-scan + cláusulas + búsqueda semántica local + monitores | Tlamatini v1 |
| **F3 — Adaptador (post-CPT)** | Entrenamiento y servido del adapter privado + redline avanzado + co-edición CRDT | Tlamatini + infra on-prem |
| **F4 — Agentic (2027+)** | Workflows (integración completa de caso), portal cliente, Word add-in | Adopción |

---

## 8. Decisiones técnicas abiertas

1. **Editor**: Tiptap (base legal-doc del ecosistema) vs CodeMirror+custom — ambos render MD; Tiptap tiene colaboración CRDT (Yjs) integrada
2. **Git interno**: libgit2 embebido vs git plano por documento — el repo del bufete COMPLETO también se versiona (disaster recovery)
3. **Diff redline**: difflib + render propio vs legal-redline-tools (produce track-changes DOCX real)
4. **PII-scan**: regex + NER propio entrenado (FER) vs Presidio (Microsoft, Apache-2.0) — Presidio tiene modelos para español, verificable
5. **CRDT**: Yjs (maduro, Tiptap-compatible)

---

*Acompañar con diagramas Mermaid de flujos por módulo en la siguiente iteración del spec.*
