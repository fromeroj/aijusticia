# Subsistema de Adquisición de Datos — AI Justicia

> Diseño del sistema que mantiene TODAS las leyes de México al día.
> Última actualización: 27 julio 2026.

---

## 1. Visión general

Un subsistema independiente que descarga, limpia e indexa automáticamente
las leyes y jurisprudencia de **toda la república mexicana**:

- **32 estados** (gacetas/periódicos oficiales + leyes vigentes)
- **Federal** (DOF, LeyesBiblio, SJF)
- **Tratados internacionales** (vinculados desde la SCJN)

Con monitoreo que detecta cuando un scraper se rompe silenciosamente,
y un dashboard de administración.

---

## 2. Catálogo de fuentes (40+)

### Fiscales (ya funcionando)
| Fuente | Adapter | Estado | URL |
|---|---|---|---|
| SJF | `sjf.py` | ✅ 150K tesis | sjf2.scjn.gob.mx |
| DOF | `dof.py` | ✅ 47 notas | dof.gob.mx |
| LeyesBiblio | `leyes_biblio.py` | ✅ 334 leyes | diputados.gob.mx |
| CDMX | ingest_cdmx.py | ✅ 147 leyes | aldf.gob.mx |
| Edomex | `edomex.py` | ✅ 137 leyes | legislacion.edomex.gob.mx |
| Nuevo León | `nuevo_leon.py` | ✅ 174 leyes | hcnl.gob.mx |
| Jalisco | `jalisco.py` | ✅ 150 leyes | congresojal.gob.mx |

### Los 28 estados restantes
Cada estado tiene su congreso o legislatura con un portal de leyes.
Patrones identificados:

| Estado | Portal | Stack | Estrategia |
|---|---|---|---|
| Aguascalientes | congresoaags.gob.mx | Drupal | Scrapeo HTML |
| Baja California | congresobc.gob.mx | ASP.NET | Scrapeo HTML |
| Baja California Sur | congresobcs.gob.mx | PHP | Scrapeo HTML |
| Campeche | congresocam.gob.mx | WordPress | Scrapeo HTML |
| Coahuila | congresocoahuila.gob.mx | JSP | Scrapeo HTML |
| Colima | congresocol.gob.mx | Drupal | Scrapeo HTML |
| Chiapas | congresochiapas.gob.mx | PHP | Scrapeo HTML |
| Chihuahua | congresochihuahua.gob.mx | ASP.NET | Scrapeo HTML |
| Durango | congresodurango.gob.mx | PHP | Scrapeo HTML |
| Guanajuato | congresogto.gob.mx | Angular SPA | API JSON o Playwright |
| Guerrero | congresogro.gob.mx | PHP | Scrapeo HTML |
| Hidalgo | congreso-ehidalgo.gob.mx | Drupal | Scrapeo HTML |
| México | ✅ ya hecho | — | — |
| Michoacán | congrsomich.gob.mx | WordPress | Scrapeo HTML |
| Morelos | congresomorelos.gob.mx | PHP | Scrapeo HTML |
| Nayarit | congresonayarit.gob.mx | PHP | Scrapeo HTML |
| Nuevo León | ✅ ya hecho | — | — |
| Oaxaca | congresooaxaca.gob.mx | Drupal | Scrapeo HTML |
| Puebla | congresopuebla.gob.mx | Angular | API JSON |
| Querétaro | legislacionqueretaro.gob.mx | Drupal | Scrapeo HTML |
| Quintana Roo | congresoqroo.gob.mx | PHP | Scrapeo HTML |
| San Luis Potosí | congresoslp.gob.mx | ASP.NET | Scrapeo HTML |
| Sinaloa | congresosinaloa.gob.mx | PHP | Scrapeo HTML |
| Sonora | congresoson.gob.mx | Drupal | Scrapeo HTML |
| Tabasco | congresotabasco.gob.mx | PHP | Scrapeo HTML |
| Tamaulipas | congresotam.gob.mx | Drupal | Scrapeo HTML |
| Tlaxcala | congresotlaxcala.gob.mx | PHP | Scrapeo HTML |
| Veracruz | congresoveracruz.gob.mx | WordPress | Scrapeo HTML |
| Yucatán | congreso.yucatan.gob.mx | PHP | Scrapeo HTML |
| Zacatecas | congresozac.gob.mx | PHP | Scrapeo HTML |
| Jalisco | ✅ ya hecho | — | — |
| CDMX | ✅ ya hecho | — | — |

### Tratados internacionales (SCJN)
La SCJN mantiene una sección de tratados internacionales que son Ley Suprema
de la Unión (art. 133 constitucional). Fuente: sjf2.scjn.gob.mx o
legislacion.scjn.gob.mx con credenciales `consultaSCOW:2consulTa_2026`.

---

## 3. Arquitectura

```
                    ┌─────────────────────────────────┐
                    │     SCHEDULER (OS-native)        │
                    │  systemd timer / launchd         │
                    │  Dispara a las 6AM diariamente   │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │   INGESTION RUNNER               │
                    │   (python -m ingestion.scheduler)│
                    │                                   │
                    │   Por cada fuente habilitada:    │
                    │   1. Leer watermark              │
                    │   2. Hash del listado (detectar  │
                    │      cambios estructurales)      │
                    │   3. Adapter.listar_desde()      │
                    │   4. Adapter.obtener_texto()     │
                    │   5. upsert + chunk + embed      │
                    │   6. Escribir ingestion_run row  │
                    │   7. Recalcular health           │
                    └──────────────┬──────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
    ┌─────────▼─────────┐ ┌───────▼────────┐  ┌───────▼────────┐
    │  POSTGRESQL        │ │  ADAPTERS       │  │  HEALTH         │
    │                    │ │  (plugin system)│  │  MONITORS       │
    │  source_health     │ │                  │  │                 │
    │  ingestion_runs    │ │  7 base adapters │  │  3 detectores:  │
    │  documentos        │ │  + 28 estatales  │  │  A: empty-result│
    │  documentos_chunks │ │  + tratados      │  │  B: page-hash   │
    │                    │ │                  │  │  C: yield-drift │
    └────────────────────┘ └──────────────────┘  └────────────────┘
              │
    ┌─────────▼──────────────────────────────────────────┐
    │   ADMIN DASHBOARD (Next.js + FastAPI /admin/*)      │
    │                                                      │
    │   ┌─────────────────────────────────────────────┐   │
    │   │ Tabla de fuentes (40+ filas)                │   │
    │   │ 🟢 SJF  🟢 DOF  🟡 Puebla  🔴 Guerrero     │   │
    │   │ click → detalle de ejecuciones               │   │
    │   └─────────────────────────────────────────────┘   │
    │   ┌──────────────────┐  ┌────────────────────────┐ │
    │   │ Gráfico histórico │  │ Hash/estructura changes │ │
    │   └──────────────────┘  └────────────────────────┘ │
    │   ┌─────────────────────────────────────────────┐   │
    │   │ Log de errores por fuente                   │   │
    │   └─────────────────────────────────────────────┘   │
    │                                                      │
    │   [Trigger manual] [Enable/Disable] [Ajustar config] │
    └──────────────────────────────────────────────────────┘
```

---

## 4. Plugin system para adapters

Cada fuente es un registro en `source_health` + un adapter Python.
Agregar un estado nuevo = 2 pasos:

### Paso 1: Registrar en la DB
```sql
INSERT INTO source_health (fuente, entidad, tipo, adapter_class, ...)
VALUES ('GacetaEstatal', 'Guerrero', 'estado', 'guerrero');
```

### Paso 2: Crear el adapter
```python
# corpus/adapters/guerrero.py
class GuerreroAdapter(CorpusAdapter):
    fuente = Fuente.GACETA_ESTATAL
    def listar_desde(self, ...): ...
    def obtener_texto(self, ...): ...
```

El `ingestion/scheduler.py` descubre los adapters dinámicamente por el
campo `adapter_class` en `source_health`.

---

## 5. Esquema de DB

### `source_health` (una fila por fuente)
```sql
CREATE TABLE source_health (
    fuente              TEXT NOT NULL,          -- 'SJF', 'DOF', 'GacetaEstatal'
    entidad             TEXT,                   -- 'Guerrero', 'CDMX', NULL=federal
    tipo                TEXT NOT NULL,          -- 'jurisprudencia', 'ley', 'gaceta', 'tratado'
    adapter_class       TEXT NOT NULL,          -- 'sjf', 'dof', 'guerrero', etc.

    -- Configuración
    enabled             BOOLEAN DEFAULT TRUE,
    cron_expr           TEXT DEFAULT '0 6 * * *',
    expected_min_results INT DEFAULT 1,

    -- Estado (actualizado por cada ejecución)
    last_run_at         TIMESTAMPTZ,
    last_success_at     TIMESTAMPTZ,
    consecutive_failures INT DEFAULT 0,
    consecutive_empty    INT DEFAULT 0,
    health_status       TEXT DEFAULT 'unknown',
    watermark           DATE,
    total_documentos    INT DEFAULT 0,          -- COUNT en documentos

    -- Detección de cambios
    listing_page_hash   TEXT,
    rolling_avg_results REAL DEFAULT 0,

    PRIMARY KEY (fuente, entidad)
);
```

### `ingestion_runs` (una fila por ejecución)
```sql
CREATE TABLE ingestion_runs (
    id                  BIGSERIAL PRIMARY KEY,
    fuente              TEXT NOT NULL,
    entidad             TEXT,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    duration_ms         INT,
    trigger             TEXT DEFAULT 'scheduled',
    status              TEXT NOT NULL,          -- 'success'|'empty_suspicious'|'failed'
    documentos_fetched  INT DEFAULT 0,
    documentos_new      INT DEFAULT 0,
    documentos_updated  INT DEFAULT 0,
    documentos_errored  INT DEFAULT 0,
    http_status_codes   INT[] DEFAULT '{}',
    listing_page_hash   TEXT,
    hash_changed        BOOLEAN DEFAULT FALSE,
    error_message       TEXT,
    error_count         INT DEFAULT 0,
    watermark_before    DATE,
    watermark_after     DATE,
    chunks_indexed      INT
);
```

---

## 6. Monitoreo de salud

### 3 detectores (corren después de cada ejecución)

**Detector A — Empty-result (HTML cambió)**
- Si `documentos_fetched == 0` Y no hubo errores Y HTTP 200 → sospechoso
- 2 días seguidos con 0 = alerta `unhealthy`

**Detector B — Page-hash (estructura cambió)**
- Hash del HTML del listado (sin scripts/styles/whitespace)
- Si cambió Y rendimiento bajo → probable ruptura del scraper

**Detector C — Yield drift (throttling)**
- EWMA de documentos nuevos (alpha 0.1)
- Si rendimiento < 30% del promedio histórico → `degraded`

### Estados de salud
| Estado | Color | Significado |
|---|---|---|
| `healthy` | 🟢 | Última ejecución OK, sin alertas |
| `degraded` | 🟡 | 1 detector activo, rendimiento bajo |
| `unhealthy` | 🔴 | 2+ días sin éxito, scraper roto |
| `unknown` | ⚪ | Nunca se ha ejecutado |

---

## 7. Scheduler

**OS-native, no APScheduler:**

### Dev (macOS): launchd
```xml
<!-- ~/Library/LaunchAgents/com.aijusticia.ingestion.plist -->
<key>StartCalendarInterval</key>
<dict><key>Hour</key><integer>6</integer></dict>
```

### Prod (Linux): systemd timer
```ini
[Timer]
OnCalendar=*-*-* 06:00:00
Persistent=true
```

El proceso es **stateless**: arranca, corre fuentes pendientes, termina.
Si crashea, el siguiente tick continúa desde el watermark.

---

## 8. Admin Dashboard

### Endpoints FastAPI `/admin/*`
```
GET  /admin/sources                    → estado de todas las fuentes
GET  /admin/sources/{fuente}/runs      → historial de ejecuciones
POST /admin/sources/{fuente}/trigger   → ejecutar manualmente
PATCH /admin/sources/{fuente}          → ajustar config
GET  /admin/alerts                     → alertas recientes
GET  /admin/stats                      → métricas globales del corpus
```

### UI (Next.js `/admin`)
1. **Tabla de fuentes**: 40+ filas, color por estado, docs totales, watermark
2. **Gráfico**: documentos nuevos por día por fuente
3. **Detalle**: historial de ejecuciones, errores, hashes
4. **Acciones**: trigger manual, enable/disable, ajustar expected_min

---

## 9. Orden de implementación

### Fase 1: Core (hoy)
1. Esquema DB: `source_health` + `ingestion_runs`
2. Sembrar `source_health` con las 7 fuentes existentes + 28 estados + tratados
3. `ingestion/runner.py`: instrumentar ingesta con logging
4. `ingestion/health.py`: los 3 detectores
5. `ingestion/scheduler.py`: entrypoint

### Fase 2: Adapters de los 28 estados
6. Generar adapters base (scrapeo HTML genérico configurable)
7. Probar estado por estado (como hicimos Edomex/NL/Jalisco)

### Fase 3: Admin
8. Endpoints `/admin/*`
9. Dashboard Next.js

### Fase 4: Scheduler
10. launchd plist (dev)
11. systemd timer (prod)

### Fase 5: Tratados internacionales
12. Adapter SCJN tratados (usar credenciales ya descubiertas)
