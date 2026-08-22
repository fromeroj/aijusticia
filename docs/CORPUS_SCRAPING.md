# Corpus Scraping — Plan y Hallazgos

> Documento de referencia para la ingesta del corpus oficial mexicano.
> Última actualización: 25 julio 2026. Investigación verificada en vivo.

---

## 1. Visión general

AI Justicia necesita un corpus siempre vigente del derecho mexicano. Las fuentes
son **todas públicas y gratuitas** (dominio público — Ley Federal del Derecho de
Autor Art. 14 excluye textos oficiales de leyes/reglamentos/gacetas del copyright;
Ley del DOF y Gacetas Gubernamentales, reformada 31-may-2019, reconoce la
publicación electrónica como legalmente válida).

Este documento describe cómo se scrapea cada fuente, la arquitectura de adapters,
y cómo extender el sistema.

### Alcance actual (fase 1)
- **Federales**: DOF, LeyesBiblio, SJF (Semanario Judicial de la Federación)
- **Estados piloto** (4): Estado de México, Nuevo León, CDMX, Jalisco
- **Backfill**: último 1 año al arranque
- **Frecuencia**: scripts manuales ahora; arquitectura lista para cron después

---

## 2. Fuentes federales

### 2.1 DOF — Diario Oficial de la Federación (`dof.gob.mx`)

Publica leyes, reglamentos, decretos, acuerdos y avisos federales. Es la fuente
primaria de vigencia: una ley no entra en vigor hasta que se publica en el DOF.

**Tecnología**: sitio Apache antiguo. **No hay API ni RSS** — todo HTML.

| Operación | URL | Método | Codificación |
|---|---|---|---|
| Lista de notas del día | `/index_111.php?year=Y&month=M&day=D` | GET | ISO-8859-1 |
| Metadata de una nota | `/nota_detalle.php?codigo=X&fecha=DD/MM/YYYY` | GET | ISO-8859-1 |
| Texto completo (born-digital) | `https://dof.gob.mx/{YYYY}/{ORG}/{ORG}_{DDMMYY}.html` | GET | **UTF-8** |
| Export Word (fallback) | `/nota_to_doc.php?codnota={even_codigo}` | GET | application/msword |

**Estructura de una nota**:
- `codigo` — ID numérico secuencial dentro del día (impar=HTML, par=export .doc)
- Dependencia emisora (SHCP, SEGOB, PRESIDENCIA, SEP, ...)
- Categoría (DECRETO, LEY, REGLAMENTO, ACUERDO, AVISO, ...)
- Fecha de publicación

**Texto completo**: el `nota_detalle.php` carga un iframe cuyo `src` apunta al HTML
born-digital del artículo. No hay PDF gemelo; el `.doc` vía `nota_to_doc.php` es
el único fallback. Ediciones pre-~2000 son PDFs escaneados (necesitan OCR).

**robots.txt**: bloquea solo notas individuales eliminadas + `nota_to_doc.php` +
`copias_cert.php`. Listings y búsqueda NO están bloqueados.

**Gotchas**:
- Codificación mixta: listings/detail en ISO-8859-1, artículo en UTF-8.
- Cookie `DOF_WEB`: algunos endpoints 302 a `/Error_BS.php` sin ella → usar cookie jar.
- Sin rate-limit visible, pero servidor gubernamental → throttle 1-2 req/s.

### 2.2 LeyesBiblio (`diputados.gob.mx/LeyesBiblio`)

Texto consolidado (vigente) de las leyes federales, con trail de reformas.

**Tecnología**: HTML estático + archivos `.doc`. Requiere **User-Agent de navegador**
(403 a curl default). No hay robots.txt.

| Operación | URL | Qué devuelve |
|---|---|---|
| Índice de leyes | `/LeyesBiblio/index.htm` | Lista de ~80 leyes con códigos |
| Metadata + reformas | `/LeyesBiblio/ref/{code}.htm` | Trail de fechas DOF (DD-MM-YYYY) |
| Texto vigente | `/LeyesBiblio/doc/{CODE}.doc` | Word con texto consolidado |

**Códigos de leyes clave**: `cpeum` (Constitución), `ccf` (Código Civil Federal),
`cpf` (Código Penal Federal), `cft` (Código Federal del Trabajo), `lritf` (Ley Fintech),
`cfpc` (Código Federal de Procedimientos Civiles), `lfpdppp` (Protección de Datos).

**Trail de reformas**: `ref/{code}.htm` contiene "DOF 26-05-1928, 14-07-1928, ..."
con cada fecha de reforma. La fecha más reciente es la **última reforma publicada**,
clave de verificación de citas.

**Parsing del .doc**: usar `antiword`, `mammoth` (tras convertir a .docx), o
LibreOffice headless. El texto viene con numeración de artículos (`Artículo 14.`).

### 2.3 SJF — Semanario Judicial de la Federación (`sjf2.scjn.gob.mx`) ⭐

Jurisprudencia y tesis de la SCJN. **La mejor fuente para scrapear**: API JSON
limpia, sin autenticación, permitida por robots.txt.

**Tecnología**: Angular SPA + Spring Boot microservices + Elasticsearch.
Los endpoints públicos `/services/.../api/public/*` son scrapeables.

| Operación | URL | Método |
|---|---|---|
| Tesis por registro digital | `/services/sjftesismicroservice/api/public/tesis/{ius}` | GET |
| Feed newest-first | `/services/sjftesismicroservice/api/public/tesis?page=0&size=200` | POST |
| Ejecutorias | `/services/sjfejecutoriamicroservice/api/public/ejecutorias` | GET/POST |
| Votos particulares | `/services/sjfvotosmicroservice/api/public/votos` | GET/POST |
| Acuerdos | `/services/sjfacuerdosmicroservice/api/public/acuerdos` | GET/POST |

**Headers requeridos** (sin ellos → 403 del WAF Imperva):
```
User-Agent: <navegador real>
Referer: https://sjf2.scjn.gob.mx/
Accept: application/json
```

**Esquema JSON de una tesis** (~50 campos, los clave):
- `ius` — registro digital (primary key, ej. `2024156789`)
- `rubro` — título/rubro (HTML `<p>`)
- `texto` — cuerpo completo (HTML `<p>`)
- `precedentes` — citas de casos (HTML)
- `materias` — "Constitucional, Común" (coma-separado)
- `ta_tj` — 0 = tesis aislada, 1 = jurisprudencia (vinculante)
- `fechaPublicacion` — ISO 8601, **clave para incremental**
- `localizacion` — cita estructurada ("11a. Época; T.C.C.; Gaceta S.J.F.; Libro 52...")
- `claveTesis` — clave oficial (ej. "II.2o.C.9 K (11a.)")

**GOTCHA CRÍTICO — lag "semanal"**: las tesis más nuevas (`semanal=1`) aparecen
en búsqueda pero **404 en el endpoint de detalle** durante ~2-4 semanas, hasta que
se promueven de `dbSemanal` a la DB principal. Estrategia:
1. Descubrir vía POST search (newest-first, ve semanal inmediatamente)
2. Si `semanal=1` y detalle 404: guardar el objeto slim ahora, reintentar backfill semanal
3. `fechaPublicacion` es el watermark canónico de novedad

**Volumen total**: 311,773 tesis + 22,913 ejecutorias + 10,092 votos + 4,065 acuerdos.

**robots.txt**: solo bloquea `/api/account`, `/api/logs/`, `/api/users/`,
`/management/`, `/v3/api-docs/`. Los endpoints públicos son crawlables.

**Formato**: HTML embebido en JSON (born-digital, sin OCR).

---

## 3. Gacetas estatales (fase piloto: 4 estados)

Cada estado tiene su propio sistema. **No hay agregador unificado.** SEGOB
mantiene un directorio de enlaces en `ordenjuridico.gob.mx/enlaces.php?a=diarios`
(útil como seed list, pero con errores: Querétaro apunta a Puebla, BCS mal etiquetado).

### 3.1 Estado de México (`legislacion.edomex.gob.mx`)
- **Stack**: Drupal. Listado JS-renderizado (necesita Playwright o síntesis de URLs).
- **Formato**: PDF born-digital, sin HTML.
- **Patrón URL**: `sites/.../files/files/pdf/gct/{YEAR}/{month}/{month}{day}{letter}.pdf`
  (ej. `gct/2026/julio/jul173/jul173a.pdf`).
- **Frecuencia**: diario, lunes a viernes (estatutario).
- **Estrategia**: sintetizar URLs por fecha (más barato que Playwright).

### 3.2 Nuevo León (`sistec.nl.gob.mx`)
- **Stack**: ASP.NET WebForms (postbacks, sin URLs limpias de navegación).
- **Formato**: PDF born-digital, ediciones grandes (~22 MB).
- **Patrón URL**: `Transparencia_2015/Archivos/AC_0001_0007_{EDITION_ID_7dig}_{SEQ_6dig}.pdf`.
- **Archivo**: 2003-presente, filtro por año/rango.
- **Estrategia**: enumerar edition IDs parseando el HTML del listado ASP.NET.

### 3.3 CDMX (`data.consejeria.cdmx.gob.mx`)
- **Stack**: Joomla (server-side rendered HTML + PDFs).
- **⚠️ TLS**: certificado inválido (`UNABLE_TO_VERIFY_LEAF_SIGNATURE`) → requiere
  `verify=False` o pinning del host.
- **Formato**: PDF + HTML de listing.
- **Frecuencia**: diario, lunes a viernes.

### 3.4 Jalisco (`periodicooficial.jalisco.gob.mx`)
- **Stack**: Angular SPA + Laravel API (`apiperiodico.jalisco.gob.mx/api`).
- **API JSON**: `GET /api/newspaper/public?fecha=YYYY-MM-DD` (valida formato estricto).
- **⚠️ Token**: requiere header `Application`/`token` extraído del bundle SPA.
  Spike esto primero — es el ítem más riesgoso.
- **Formato**: PDF born-digital.
- **Frecuencia**: semanal a quincenal (menos frecuente que los otros 3).

### Patrones comunes
- Casi todos son "Periódico Oficial" (algunos "Gaceta Oficial": Chihuahua, Veracruz, Edomex, CDMX).
- Subdominio típico: `periodicooficial.{estado}.gob.mx`.
- PDFs born-digital son la norma para ediciones actuales (OCR solo para histórico pre-2010).
- Sin rate-limit visible, pero throttle 1-2 req/s por cortesía.

---

## 4. Arquitectura de adapters

Cada fuente implementa una **interfaz común** (`CorpusAdapter`), desacoplando la
lógica de obtención del resto del sistema.

```python
# corpus/adapters/base.py
class CorpusAdapter(Protocol):
    """Contrato que toda fuente del corpus implementa."""
    fuente: Fuente  # enum: DOF, LEYES_BIBLIO, SJF, GACETA_ESTATAL

    def listar_desde(self, fecha_inicio: date) -> Iterator[DocumentoMetadata]:
        """Lista documentos nuevos desde fecha_inicio (para incremental)."""
        ...

    def obtener_texto(self, metadata: DocumentoMetadata) -> str:
        """Obtiene el texto completo de un documento."""
        ...
```

### Implementaciones
| Adapter | Fuente | Tecnología | Dificultad |
|---|---|---|---|
| `sjf.py` | SJF | API JSON ⭐ | Fácil (el primero) |
| `dof.py` | DOF | Scrapeo HTML | Media |
| `leyes_biblio.py` | LeyesBiblio | HTML + .doc | Media |
| `edomex.py` | Edomex | PDF (síntesis URL) | Media |
| `nuevo_leon.py` | Nuevo León | PDF (ASP.NET listing) | Media |
| `cdmx.py` | CDMX | PDF (Joomla, TLS) | Media |
| `jalisco.py` | Jalisco | JSON API + token | Difícil (token) |

### Componentes compartidos
- `corpus/http_client.py` — cliente HTTP educativo (UA navegador, rate limit
  1-2 req/s, retry con backoff exponencial, cookie jar, soporte gzip)
- `corpus/clean.py` — limpieza de texto (normalización NFKC, strip de HTML,
  filtros de 10-gramas para artefactos, dedup de espacios/líneas)
- `corpus/watermark.py` — tracking de última fecha procesada por fuente
  (para incremental: "dame todo desde la última vez")
- `corpus/ingest.py` — orquestador que llama adapters → normaliza → upsert →
  chunk_and_index

### Flujo de ingesta
```
ingest.py
  ├─ leer watermark de cada fuente
  ├─ para cada adapter:
  │    ├─ adapter.listar_desde(watermark) → [DocumentoMetadata]
  │    ├─ para cada metadata:
  │    │    ├─ texto = adapter.obtener_texto(metadata)
  │    │    ├─ texto_limpio = clean(texto)
  │    │    ├─ doc = Documento(fuente=..., texto=texto_limpio, metadatos=...)
  │    │    ├─ upsert_documento(doc)  # idempotente por dedup_key
  │    │    └─ chunk_and_index(doc, doc_id)  # embeds + pgvector
  │    └─ actualizar watermark
  └─ recargar BM25 index en memoria
```

---

## 5. Cómo extender (añadir un estado)

1. Crear `ai_justicia/corpus/adapters/{estado}.py` implementando `CorpusAdapter`.
2. Implementar `listar_desde(fecha)` — enumerar ediciones desde esa fecha.
3. Implementar `obtener_texto(metadata)` — descargar y extraer texto del PDF/HTML.
4. Registrar el adapter en `adapters/__init__.py`.
5. Añadir CLI en `scripts/ingest_estado.py --estado {estado}`.

**Plantilla**: copiar `edomex.py` como base (es el patrón PDF más típico).

### Prioridad de estados futuros (fase 2)
Puebla, Guanajuato, Oaxaca, Michoacán, Sonora, Veracruz — según valor poblacional
y factibilidad técnica.

---

## 6. Comandos CLI

```bash
# Ingesta de una fuente específica (último año por defecto)
python scripts/ingest_sjf.py                    # Semanario Judicial
python scripts/ingest_dof.py                    # Diario Oficial
python scripts/ingest_leyes_biblio.py           # Leyes federales consolidadas

# Ingesta de estados
python scripts/ingest_estado.py --estado edomex
python scripts/ingest_estado.py --estado nuevo_leon
python scripts/ingest_estado.py --estado cdmx
python scripts/ingest_estado.py --estado jalisco

# Todo de una vez
python scripts/ingest_all.py                    # Todos los adapters

# Backfill con ventana personalizada
python scripts/ingest_sjf.py --desde 2024-01-01 --hasta 2024-12-31
```

---

## 7. Consideraciones legales

- **Dominio público**: los textos oficiales de leyes, reglamentos, decretos,
  gacetas y resoluciones judiciales **no están sujetos a copyright** en México
  (Ley Federal del Derecho de Autor Art. 14).
- **Publicación electrónica válida**: la Ley del DOF y Gacetas Gubernamentales
  (reformada 31-may-2019) reconoce la publicación electrónica como legalmente
  válida. La SCJN ha confirmado este criterio.
- **robots.txt**: todas las fuentes permiten el scrapeo de contenido público.
  Solo se bloquean endpoints admin/auth o notas eliminadas.
- **Etiqueta**: throttle 1-2 req/s, User-Agent descriptivo, respetar 503/429.
- **Atribución**: citar siempre la fuente ("Semanario Judicial de la Federación, SCJN"
  + registro digital / claveTesis; "DOF" + fecha + código).

---

## 8. Plan futuro — cron automático

Cuando los scrapers estén estables, activar cron:

```
# crontab
0 6 * * *  cd /path/engine && python scripts/ingest_all.py >> /var/log/aij-ingest.log 2>&1
```

- Corre diario a las 6 AM (después de que las fuentes publican).
- Notifica fallos (email/Slack).
- Métricas: documentos nuevos, tiempo, errores por fuente.
- Backfill semanal de tesis `semanal=1` que estaban en lag.

### Monitoreo
- `GET /health` de la API reporta conteos de documentos/chunks.
- Tabla `documentos` tiene `created_at` y `updated_at` para auditoría.
- Log de cada ingesta con adapter, documentos procesados, errores.

---

## 9. Hallazgos técnicos para recordar

- **SJF es la joya**: API JSON limpia, sin auth, sin OCR. Empezar por ahí.
- **DOF**: codificación mixta (ISO-8859-1 vs UTF-8), cookie jar necesario.
- **LeyesBiblio**: User-Agent obligatorio, texto en .doc (no HTML/PDF).
- **Estados**: 32 sistemas heterogéneos, no hay aggregator. Empezar con 4.
- **Jalisco**: el más riesgoso (token del SPA). Spike antes de comprometer.
- **CDMX**: cert TLS inválido, requiere `verify=False`.
- **Backfill SJF**: la lag "semanal" de 2-4 semanas es real y esperada.
- **Todo born-digital**: OCR solo para histórico pre-2010.

---

## 10. Referencias

- **DOF**: https://www.dof.gob.mx
- **LeyesBiblio**: https://www.diputados.gob.mx/LeyesBiblio/index.htm
- **SJF**: https://sjf2.scjn.gob.mx
- **SEGOB directorio de gacetas**: http://www.ordenjuridico.gob.mx/enlaces.php?a=diarios
- **Edomex**: https://legislacion.edomex.gob.mx/ve_periodico_oficial
- **Nuevo León**: https://sistec.nl.gob.mx/Transparencia_2015_LyPOE/Acciones/PeriodicoOficial.aspx
- **CDMX**: https://consejeria.cdmx.gob.mx/gaceta-oficial
- **Jalisco**: https://periodicooficial.jalisco.gob.mx/
- **Ley del DOF**: https://www.diputados.gob.mx/LeyesBiblio/pdf/75_100619.pdf
