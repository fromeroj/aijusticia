# Visión del proyecto — AI Justicia

> Última actualización: 14 octubre 2026
> Este documento explica **el intento** (qué estamos construyendo y por qué) y
> **la colaboración** (cómo se conectan los subsistemas). El detalle operativo
> de cada pieza vive en [`components/`](components/); el índice completo en
> [`INDEX.md`](INDEX.md).

## 1. El intento

Que cualquier persona en México —ciudadano, abogado o despacho— pueda preguntar
en lenguaje natural y recibir **respuesta legal con la cita exacta y verificable**,
al día con el Diario Oficial, sin depender de modelos extranjeros que improvisan.

Tres capas de producto sobre un mismo corpus:

1. **Ciudadano** — Izel responde qué dice la ley, qué artículo ampara y qué pasos seguir.
2. **Abogado / despacho** — Studio: expedientes, bóveda cifrada, equipo compartido, citas precisas.
3. **Despacho con oficina** — piloto Nextcloud/Collabora: edición de documentos
   con plantillas del despacho dentro del ecosistema.

Y una pieza estratégica: **Tlamatini**, modelo legal mexicano open-weight,
entrenado (CPT) sobre nuestro propio corpus — para no depender de MiniMax ni de
ningún proveedor, y para poder exportarse on-premise.

## 2. Principios de diseño (aprendidos a la hard way)

- **Producción autónoma**: el sitio funciona completo sin la Mac ni ningún
  componente local (LLM cloud + DB local del VPS). Lo local solo cosecha y entrena.
- **Recencia como ventaja defendible**: el DOF entra diario por cron; las reformas
  del mes están en el corpus antes que en el knowledge cutoff de cualquier modelo.
  La rama de "recientes" del retrieval hardwirea esta ventaja.
- **Cita verificable o no cita**: cada respuesta ancla pasajes con fuente y artículo;
  la batería de evaluación castiga fechas inventadas y artículos inexistentes.
- **Dos bases con roles distintos**: prod (162, sirve) vs archivo (182, entrena).
  No se mezclan; la sincronización es trabajo explícito del data consumer.
- **Correcciones aburridas y verificables**: toda reorganización/refactor pasa por
  la batería antes y después. Nada de big-bang sobre producción.

## 3. Los subsistemas y cómo colaboran

```
                ┌──────────────────────────────┐
                │  INFRA/OPS (servers, crons)  │
                └──────────────┬───────────────┘
     escribe ▼                 ▼ sirve                 lee ▼
┌───────────────┐    ┌──────────────────┐      ┌────────────────┐
│ DATA CONSUMER │───▶│ DB PROD (162)    │      │ EVAL (batería) │
│ harvest, ing. │    │ 473K docs/14.1M  │      │ árbitro de los │
│ limpieza      │    │ + DB ARCHIVO(182)│      │ otros tres     │
└───────────────┘    └────────┬─────────┘      └────────────────┘
                              │ SQL / FTS
                              ▼
                    ┌──────────────────┐         ┌──────────────────┐
                    │ RAG (retrieval)  │◀──lee──│ DB ARCHIVO (182) │──▶ TLAMATINI
                    └────────┬─────────┘         └──────────────────┘   (Soup CPT,
                             │ pasajes[]                          merge, GGUF)
                             ▼
                    ┌──────────────────┐   swap por env var
                    │ IZEL + BIBLIO.   │◀──────────── [MiniMax-M3 cloud | Tlamatini]
                    │ (agente, SSE)    │
                    └────────┬─────────┘
                             │ /chat/stream
   ┌──────────────┐          ▼
   │ AUTH         │──▶ API PRODUCTO (FastAPI) ──▶ WEB APP (Next.js)
   └──────────────┘          │
                             ▼
                    ┌──────────────────┐
                    │ OFFICE (Nextcloud│  (en migración: Mac → 162;
                    │  + Collabora)    │   storage: server dedicado cuando viva)
                    └──────────────────┘
   MARCA/GTM (tlamatini.live, deck, artículo) — solo lee del producto.
```

### Reglas de dependencia (las flechas no se cruzan)

| Regla | Consecuencia práctica |
|---|---|
| `apps/web` habla SOLO con la API | nunca toca la DB directamente |
| `agents/` usa `retrieval/` y `llm/`, no SQL suelto | el RAG cambia sin tocar el agente |
| `data/` escribe a DB, no importa de services | la cosecha nunca rompe el producto |
| `models/tlamatini/` lee del archivo, produce artefactos | entrenar no toca producción |
| `eval/` solo lee (DB + HTTP) | medir jamás perturba |
| LLM = endpoint OpenAI-compatible | cambiar de modelo = una env var |

### El ciclo de valor completo (cómo colaboran en un día típico)

1. **11:30 CDMX**: el cron ingiere el DOF del día a la DB prod (data consumer).
2. **Un ciudadano pregunta** en aijusticia.mx → Izel consulta al Bibliotecario →
   el RAG trae pasajes (ley consolidada + decretos frescos de ≤150 días) →
   respuesta con citas [n] y panel de leyes.
3. **08:30 CDMX (ventana muerta)**: limpieza profunda y re-ingestas pendientes,
   con nice, sin perturbar el sitio.
4. **Continuo en 66.154**: el harvest de leyes consolidadas llena la DB archivo
   para el próximo CPT de Tlamatini.
5. **Cuando Tlamatini tenga checkpoint**: `eval_bateria` corre contra él Y contra
   MiniMax — si gana, swap de env var. Ese A/B es el hito del proyecto.

## 4. Estado de cada subsistema (14-oct)

| Subsistema | Estado | Doc de componente |
|---|---|---|
| Data consumer | 🟢 DOF diario vivo; harvest OJ 16/32 (66→182); limpieza en ventana nocturna | `components/data-consumer.md` |
| DBs | 🟢 prod 473,848/14.1M; archivo 411K; ⚠️ storage server NFS caído (161.129.70.21) | `components/bases-de-datos.md` |
| RAG | 🟢 dos fases + recientes; batería 6-7/8 estricto (varianza = modelo) | `components/rag.md` |
| Izel | 🟢 en producción; pendiente extraer a `agents/` con gate de batería | `components/izel.md` |
| Tlamatini | 🟡 pipeline listo; corpus re-export pendiente post-limpieza | `components/tlamatini.md` |
| API producto | 🟢 live | `components/api-producto.md` |
| Web app | 🟢 live | `components/web-app.md` |
| Auth | 🟢 anónimo→email→frase funcionando; Google OAuth pendiente | `components/auth.md` |
| Office | 🟡 en migración Mac→162 | `components/office.md` |
| Eval | 🟢 batería de producción + eval de entrenamiento | `components/eval.md` |
| Infra/Ops | 🟢 4 servers + storage caído; monitoreo externo pendiente | `components/infra.md` |
| Marca/GTM | 🟢 tlamatini.live + deck con cifras reales | `components/marca.md` |

## 5. Próximos hitos

1. Terminar ingesta SIVEPJ + limpieza (ventana nocturna) → re-medir batería limpia.
2. Migrar Office a 162 y apagar los contenedores de la Mac.
3. Harvest OJ completo (32/32 en archivo) → `prep_cpt_completo.py` desde **162** →
   **primer entrenamiento Tlamatini** → A/B con batería.
4. Storage server arriba → NFS para Office (y reconsiderar corpus_downloads).
5. Monitoreo externo (UptimeRobot sobre /health).
