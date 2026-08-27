"""API REST del motor AI Justicia (FastAPI).

Endpoints:
  GET  /health          — estado del servidor (LM Studio, DB)
  POST /query           — ejecuta el pipeline completo sobre una consulta
  POST /query/stream    — SSE: stage progress + token streaming + done
  GET  /jobs/{job_id}   — estado de un job de ingesta on-demand (Caso B)
  GET  /documentos/{id} — metadatos de un documento del corpus
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ai_justicia.config import settings
from ai_justicia.corpus.store import count_chunks, count_documentos
from ai_justicia.jobs.store import obtener_job
from ai_justicia.llm.client import check_connection
from ai_justicia.pipeline.orchestrator import RespuestaPipeline, ejecutar_consulta

logging.basicConfig(level=settings.log_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AI Justicia API iniciando — LM Studio: %s", settings.lmstudio_base_url)
    conn = check_connection()
    if conn["ok"]:
        logger.info("LM Studio OK: %s (llm=%s, embed=%s)", conn["base_url"], conn["llm_loaded"], conn["embed_loaded"])
    else:
        logger.warning("LM Studio no disponible: %s", conn.get("error"))
    yield
    logger.info("AI Justicia API deteniéndose")


app = FastAPI(
    title="AI Justicia — Motor LLM + RAG",
    description="IA jurídica mexicana con citas verificadas contra fuentes oficiales.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS: el frontend Next.js (:3000) llama directamente a FastAPI (:8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Schemas ---
class TurnoHistorial(BaseModel):
    role: str = Field(..., description="user | assistant")
    text: str = Field(..., max_length=4000, description="Texto del turno")


class QueryRequest(BaseModel):
    consulta: str = Field(..., min_length=3, max_length=2000, description="Pregunta jurídica del usuario")
    nivel: str = Field("Nivel0", description="Nivel de servicio: Nivel0 (ciudadano) | Nivel1 | Nivel2 (abogado)")
    webhook_url: str | None = Field(None, description="Si se setea y ocurre Caso B (norma faltante), el worker notificará aquí al completar")
    respuestas_aclaratorias: dict[str, str] | None = Field(None, description="Respuestas del usuario a las preguntas de la ronda actual")
    respuestas_acumuladas: dict[str, str] | None = Field(None, description="Respuestas de TODAS las rondas anteriores (multi-ronda)")
    expediente_prev: dict | None = Field(None, description="Expediente acumulado del caso (viene del último evento clarify o done)")
    historial: list[TurnoHistorial] | None = Field(None, description="Turnos previos de la conversación [{role, text}] — permite contextualizar preguntas de seguimiento")


class QueryResponse(BaseModel):
    estado: str = Field(..., description="completada | pendiente_actualizacion")
    abstenido: bool
    respuesta: str
    analisis: dict
    pasajes: list[dict]
    verificacion: dict
    duracion_ms: int
    traza_id: int | None
    tipo_abstencion: str | None = None   # 'EVIDENCIA_INSUFICIENTE' | 'NORMA_FALTANTE'
    job_id: int | None = None            # si pendiente_actualizacion: id para GET /jobs/{id}
    norma_faltante: str | None = None


class JobStatus(BaseModel):
    job_id: int
    estado: str                          # pendiente | descargando | ingiriendo | completado | fallido
    consulta: str | None = None
    norma_faltante: str | None = None
    fuente: str | None = None
    respuesta: str | None = None
    traza_reintento: int | None = None
    error: str | None = None
    created_at: str | None = None
    completed_at: str | None = None


# --- Endpoints ---
@app.get("/health")
def health() -> dict:
    """Estado del servidor de inferencia y la base de datos."""
    conn = check_connection()
    try:
        n_docs = count_documentos()
        n_chunks = count_chunks()
    except Exception:  # noqa: BLE001
        n_docs, n_chunks = -1, -1
    return {
        "status": "ok" if conn["ok"] and n_docs >= 0 else "degraded",
        "lmstudio": conn,
        "corpus": {"documentos": n_docs, "chunks": n_chunks},
    }


@app.post("/query/stream")
async def query_stream(req: QueryRequest):
    """SSE: ejecuta el pipeline emitiendo eventos de progreso + tokens + resultado final.

    Eventos:
      event: stage   data: {"stage":"analisis","label":"Analizando tu consulta..."}
      event: stage   data: {"stage":"recuperacion","label":"Buscando fuentes oficiales..."}
      event: stage   data: {"stage":"generacion","label":"Generando respuesta..."}
      event: token   data: "El artículo..."  (word-by-word del LLM)
      event: stage   data: {"stage":"verificacion","label":"Verificando citas..."}
      event: done    data: {respuesta, citas, traza_id, job_id, abstenido, ...}
      event: error   data: {"mensaje":"..."}
    """
    import asyncio

    async def event_generator():
        try:
            # Etapa 1.6: Contextualizar la pregunta con el historial de la conversación.
            # Las preguntas de seguimiento ("¿y cuánto tiempo tengo?") son ambiguas
            # por sí solas; sin esto la recuperación busca en todas las materias.
            yield _sse("stage", {"stage": "analisis", "label": "Analizando tu consulta..."})
            from ai_justicia.pipeline.query_analysis import (
                analizar_consulta, contextualizar_consulta, resumir_contexto_conversacion,
            )
            from ai_justicia.pipeline.expediente import (
                Expediente, actualizar_expediente, detectar_huecos_post_rag,
            )
            historial_dicts = [t.model_dump() for t in (req.historial or [])]
            consulta_completa = await asyncio.to_thread(
                contextualizar_consulta, req.consulta, historial_dicts,
            )
            contexto_conv = resumir_contexto_conversacion(historial_dicts)

            analisis = await asyncio.to_thread(analizar_consulta, consulta_completa)

            es_abogado = req.nivel in ("Nivel1", "Nivel2")

            # ── CICLO DE ENTREVISTA (solo ciudadanos; el abogado va directo) ──
            expediente = Expediente.desde_dict(req.expediente_prev)
            preguntas: list = []
            if settings.entrevista_habilitada and not es_abogado:
                expediente, preguntas = await asyncio.to_thread(
                    actualizar_expediente,
                    consulta_completa, historial_dicts, expediente,
                    dict(req.respuestas_acumuladas or {}),
                )

                if preguntas and expediente.rondas_pre_rag < settings.entrevista_rondas_pre_rag:
                    expediente.rondas_pre_rag += 1
                    yield _sse("clarify", {
                        "materia": expediente.materia or analisis.materia,
                        "ronda": expediente.rondas_pre_rag,
                        "rondas_max": settings.entrevista_rondas_pre_rag,
                        "fase": "pre_rag",
                        "expediente": expediente.a_dict(),
                        "questions": [
                            {"id": q.id, "texto": q.texto, "tipo": q.tipo, "opciones": q.opciones}
                            for q in preguntas
                        ],
                    })
                    return  # el cliente reenviará con respuestas acumuladas

            # El expediente completa el análisis (materia/jurisdicción detectadas en entrevista)
            if expediente.materia and not analisis.materia:
                analisis.materia = expediente.materia
            if expediente.jurisdiccion and not analisis.jurisdiccion:
                analisis.jurisdiccion = expediente.jurisdiccion
            # Los hechos del expediente enriquecen la consulta para recuperación
            if expediente.hechos:
                hechos_str = "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in expediente.hechos.items())
                consulta_completa = f"{consulta_completa} (Datos del caso: {hechos_str})"

            yield _sse("stage", {"stage": "recuperacion", "label": "Buscando fuentes oficiales..."})
            from ai_justicia.pipeline.retrieve import recuperar_y_rerankear
            pasajes = await asyncio.to_thread(recuperar_y_rerankear, consulta_completa, analisis)

            # Etapa 3.5: filtro de relevancia LLM (con contexto de la conversación)
            # — antes este paso no se ejecutaba en la ruta SSE.
            if pasajes:
                from ai_justicia.pipeline.relevance import filtrar_relevantes
                pasajes = await asyncio.to_thread(
                    filtrar_relevantes, consulta_completa, pasajes, contexto_conv,
                )

            # ── HUECOS POST-RAG: la ley revela qué falta (solo ciudadanos) ──
            if (
                settings.entrevista_habilitada and not es_abogado
                and pasajes
                and expediente.rondas_post_rag < settings.entrevista_rondas_post_rag
            ):
                huecos = await asyncio.to_thread(
                    detectar_huecos_post_rag, consulta_completa, expediente, pasajes,
                )
                if huecos:
                    expediente.rondas_post_rag += 1
                    yield _sse("clarify", {
                        "materia": expediente.materia or analisis.materia,
                        "ronda": expediente.rondas_post_rag,
                        "rondas_max": settings.entrevista_rondas_post_rag,
                        "fase": "post_rag",
                        "expediente": expediente.a_dict(),
                        "questions": [
                            {"id": q.id, "texto": q.texto, "tipo": q.tipo, "opciones": q.opciones}
                            for q in huecos
                        ],
                    })
                    return

            yield _sse("stage", {"stage": "generacion", "label": "Generando respuesta..."})
            from ai_justicia.llm.generate import generar
            # La generación ve la pregunta ORIGINAL del usuario (no la reescrita)
            # junto con pasajes recuperados con todo el contexto.
            respuesta_gen = await asyncio.to_thread(generar, req.consulta, pasajes, req.nivel)

            # Emitir el texto generado como tokens.
            # Partir por palabras preservando espacios entre lotes.
            texto = respuesta_gen.texto_completo
            palabras = texto.split(" ")
            for i in range(0, len(palabras), 3):
                chunk = " ".join(palabras[i:i+3])
                # Asegurar espacio al final si hay más palabras después
                if i + 3 < len(palabras):
                    chunk += " "
                yield _sse("token", chunk)
                await asyncio.sleep(0.01)  # pequela pausa para el efecto streaming

            yield _sse("stage", {"stage": "verificacion", "label": "Verificando citas..."})
            from ai_justicia.pipeline.verify import verificar
            verif = await asyncio.to_thread(verificar, respuesta_gen, pasajes, consulta_completa)

            # Diagnóstico A/B si hubo abstención
            texto_final = verif.texto_final
            job_id = None
            tipo_abstencion = None
            if verif.decision.abstenido:
                tipo_abstencion = verif.decision.tipo.value
                # Personalizar el mensaje con el tipo de abogado según la materia
                tipo_abogado = _tipo_abogado_por_materia(analisis.materia)
                if verif.decision.tipo.value == "NORMA_FALTANTE":
                    from ai_justicia.jobs.store import crear_job
                    from ai_justicia.verification.abstention import MENSAJE_DEFERIDO
                    job_id = crear_job(
                        consulta=req.consulta,
                        norma_faltante=verif.decision.norma_faltante,
                        fuente=verif.decision.fuente_faltante,
                        id_externo=verif.decision.id_externo,
                        webhook_url=req.webhook_url,
                    )
                    texto_final = MENSAJE_DEFERIDO.format(
                        norma=verif.decision.norma_faltante or "la norma pertinente",
                        job_id=job_id,
                    )
                else:
                    # Caso A: abstención definitiva con tipo de abogado específico
                    texto_final = (
                        f"No encuentro base suficiente en las fuentes oficiales para responder "
                        f"con la precisión que mereces. Te recomiendo validar tu caso con un "
                        f"abogado especialista en {tipo_abogado} con cédula profesional. "
                        f"La orientación inicial es gratuita y la validación cuesta desde "
                        f"$100 MXN, pagable en OXXO."
                    )

            # Persistir traza — guarda la consulta ORIGINAL y, si fue reescrita,
            # se anexa la versión contextualizada para auditoría de recuperación.
            import time
            from ai_justicia.pipeline.orchestrator import _guardar_traza
            consulta_traza = req.consulta if consulta_completa == req.consulta else (
                f"{req.consulta} [contextualizada: {consulta_completa[:300]}]"
            )
            traza_id = await asyncio.to_thread(
                _guardar_traza,
                consulta_traza, analisis, pasajes, verif, req.nivel, 0,
            )

            yield _sse("done", {
                "respuesta": texto_final,
                "abstenido": verif.decision.abstenido,
                "tipo_abstencion": tipo_abstencion,
                "job_id": job_id,
                "traza_id": traza_id,
                "expediente": expediente.a_dict(),
                "n_oraciones": verif.n_oraciones,
                "n_sustentadas": verif.n_sustentadas,
                # Solo enviar los pasajes que el LLM realmente citó en su respuesta.
                # Esto evita mostrar referencias irrelevantes que el RAG recuperó
                # pero el LLM descartó por no aplicar al caso.
                "pasajes": [
                    {
                        "titulo": pasajes[i-1].titulo[:100] if i-1 < len(pasajes) else "Desconocido",
                        "fuente": pasajes[i-1].fuente if i-1 < len(pasajes) else "",
                        "clave_cita": f"SJF {pasajes[i-1].registro_sjf}" if i-1 < len(pasajes) and pasajes[i-1].registro_sjf else (pasajes[i-1].titulo[:50] if i-1 < len(pasajes) else ""),
                        "vinculante": pasajes[i-1].vinculante if i-1 < len(pasajes) else True,
                        "fragmento": pasajes[i-1].texto[:600] if i-1 < len(pasajes) else "",
                        "jerarquia": pasajes[i-1].jerarquia if i-1 < len(pasajes) else 100,
                    }
                    for i in sorted(set(
                        c.oracion.cita_idx for c in verif.citas
                        if c.oracion.cita_idx is not None
                    ))
                ],
                "citas": [
                    {
                        "texto": c.oracion.texto[:120],
                        "sustentado": c.sustentado,
                        "nli": c.nli.etiqueta if c.nli else None,
                    }
                    for c in verif.citas
                ],
            })

        except Exception as e:
            logger.exception("Error en /query/stream")
            yield _sse("error", {"mensaje": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _sse(event: str, data) -> str:
    """Formatea un evento SSE."""
    if isinstance(data, str):
        data_str = data
    else:
        data_str = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {data_str}\n\n"


def _tipo_abogado_por_materia(materia: str | None) -> str:
    """Devuelve el tipo de abogado especialista según la materia detectada."""
    if not materia:
        return "derecho civil o familiar"
    mapping = {
        "Familiar": "derecho familiar",
        "Civil": "derecho civil",
        "Penal": "derecho penal",
        "Laboral": "derecho laboral",
        "Mercantil": "derecho mercantil o bancario",
        "Constitucional": "amparo y derecho constitucional",
        "Fiscal": "derecho fiscal",
        "Administrativo": "derecho administrativo",
        "Amparo": "amparo y derecho constitucional",
        "Electoral": "derecho electoral",
        "Agrario": "derecho agrario",
        "Ambiental": "derecho ambiental",
    }
    return mapping.get(materia, "derecho civil o familiar")


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    """Ejecuta el pipeline completo de 5 etapas sobre una consulta jurídica.

    Si el resultado es Caso B (norma faltante), devuelve estado=pendiente_actualizacion
    + job_id. El cliente puede consultar GET /jobs/{job_id} para saber cuándo está lista.
    """
    logger.info("POST /query: %s", req.consulta[:80])
    resultado: RespuestaPipeline = ejecutar_consulta(
        req.consulta, nivel=req.nivel, webhook_url=req.webhook_url,
    )

    # Determinar el estado HTTP-level
    if resultado.job_id is not None:
        estado = "pendiente_actualizacion"
    else:
        estado = "completada"

    return QueryResponse(
        estado=estado,
        abstenido=resultado.abstenido,
        respuesta=resultado.respuesta,
        analisis=resultado.analisis,
        pasajes=resultado.pasajes,
        verificacion=resultado.verificacion,
        duracion_ms=resultado.duracion_ms,
        traza_id=resultado.traza_id,
        tipo_abstencion=resultado.tipo_abstencion,
        job_id=resultado.job_id,
        norma_faltante=resultado.verificacion.get("explicacion_diagnostico") if resultado.job_id else None,
    )


@app.get("/jobs/{job_id}", response_model=JobStatus)
def job_status(job_id: int) -> JobStatus:
    """Consulta el estado de un job de ingesta on-demand (Caso B).

    El cliente hace polling aquí tras recibir estado=pendiente_actualizacion.
    """
    from datetime import datetime
    job = obtener_job(job_id)
    if job is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Job {job_id} no encontrado")

    def _iso(dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None

    return JobStatus(
        job_id=job.id,
        estado=job.estado.value,
        consulta=job.consulta[:200],
        norma_faltante=job.norma_faltante,
        fuente=job.fuente,
        respuesta=job.respuesta,
        traza_reintento=job.traza_reintento,
        error=job.error,
        created_at=_iso(job.created_at),
        completed_at=_iso(job.completed_at),
    )


# ============================================================
# ADMIN ENDPOINTS — Subsistema de adquisición de datos
# ============================================================

@app.get("/admin/sources")
def admin_sources():
    """Estado de todas las fuentes del corpus (para el dashboard)."""
    from ai_justicia.ingestion.store import listar_sources_health
    sources = listar_sources_health()
    # Serializar fechas
    for s in sources:
        for k in ("last_run_at", "last_success_at"):
            if s.get(k):
                s[k] = s[k].isoformat() if hasattr(s[k], "isoformat") else str(s[k])
        if s.get("watermark"):
            s["watermark"] = s["watermark"].isoformat() if hasattr(s["watermark"], "isoformat") else str(s["watermark"])
    return {"sources": sources, "total": len(sources)}


@app.get("/admin/sources/{fuente}/runs")
def admin_runs(fuente: str, entidad: str = "Federal", limit: int = 50):
    """Historial de ejecuciones de una fuente."""
    from ai_justicia.ingestion.store import listar_runs
    runs = listar_runs(fuente, entidad if entidad != "Federal" else None, limit)
    for r in runs:
        for k in ("started_at", "completed_at"):
            if r.get(k):
                r[k] = r[k].isoformat() if hasattr(r[k], "isoformat") else str(r[k])
        for k in ("watermark_before", "watermark_after"):
            if r.get(k):
                r[k] = r[k].isoformat() if hasattr(r[k], "isoformat") else str(r[k])
    return {"runs": runs}


@app.post("/admin/sources/{fuente}/trigger")
def admin_trigger(fuente: str, entidad: str = "Federal"):
    """Ejecuta manualmente la ingesta de una fuente."""
    from ai_justicia.ingestion.runner import run_source
    result = run_source(fuente, entidad, trigger="manual")
    # Serializar
    if isinstance(result.get("watermark_after"), str):
        pass
    elif result.get("watermark_after"):
        result["watermark_after"] = result["watermark_after"].isoformat()
    return result


class SourceUpdate(BaseModel):
    enabled: bool | None = None
    expected_min_results: int | None = None
    cron_expr: str | None = None
    portal_url: str | None = None


@app.patch("/admin/sources/{fuente}")
def admin_update_source(fuente: str, entidad: str = "Federal", update: SourceUpdate = SourceUpdate()):
    """Actualiza la configuración de una fuente."""
    import psycopg
    sets = []
    params = []
    if update.enabled is not None:
        sets.append("enabled = %s")
        params.append(update.enabled)
    if update.expected_min_results is not None:
        sets.append("expected_min_results = %s")
        params.append(update.expected_min_results)
    if update.cron_expr is not None:
        sets.append("cron_expr = %s")
        params.append(update.cron_expr)
    if update.portal_url is not None:
        sets.append("portal_url = %s")
        params.append(update.portal_url)
    if not sets:
        raise HTTPException(status_code=400, detail="No hay campos para actualizar")
    params.extend([fuente, entidad if entidad != "Federal" else None])
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE source_health SET {', '.join(sets)} WHERE fuente = %s AND entidad = %s",
                params,
            )
        conn.commit()
    return {"status": "updated", "fuente": fuente, "entidad": entidad}


@app.get("/admin/stats")
def admin_stats():
    """Métricas globales del corpus (incluye tokens estimados)."""
    from ai_justicia.corpus.store import count_documentos, count_chunks
    import psycopg as _psy
    with _psy.connect(settings.psycopg_dsn) as _conn:
        with _conn.cursor() as _cur:
            _cur.execute("SELECT COALESCE(SUM(LENGTH(texto)) / 4, 0) FROM documentos")
            tokens = _cur.fetchone()[0]
            _cur.execute("""
                SELECT fuente, COUNT(*), COALESCE(SUM(LENGTH(texto)) / 4000000, 0)
                FROM documentos GROUP BY fuente ORDER BY COUNT(*) DESC
            """)
            fuentes = [{"fuente": f, "docs": n, "tokens_m": round(t, 1)} for f, n, t in _cur.fetchall()]
    return {
        "total_documentos": count_documentos(),
        "total_chunks": count_chunks(),
        "total_tokens": tokens,
        "fuentes": fuentes,
        "sources_healthy": _count_health("healthy"),
        "sources_degraded": _count_health("degraded"),
        "sources_unhealthy": _count_health("unhealthy"),
        "sources_unknown": _count_health("unknown"),
    }


# ── Dossiers y consentimiento ─────────────────────────────────────────────

class DossierCreateRequest(BaseModel):
    """Crear ciudadano anónimo + su primer dossier. La frase se muestra UNA vez."""
    pass


class ConsentimientoRequest(BaseModel):
    otorgar: bool = Field(..., description="True = consentir entrenamiento general, False = revocar")


@app.post("/dossiers")
def crear_dossier_ep(_: DossierCreateRequest | None = None):
    """Crea ciudadano anónimo + dossier. Devuelve la frase de recuperación UNA vez.

    El cliente debe mostrarla inmediatamente y nunca reenviarla al servidor.
    """
    from ai_justicia.dossiers import store as dstore
    actor_id, frase = dstore.crear_ciudadano()
    dossier_id = dstore.crear_dossier(actor_id)
    return {
        "dossier_id": str(dossier_id),
        "actor_id": str(actor_id),
        "frase_recuperacion": frase,
        "aviso": (
            "Guarda esta frase en un lugar seguro: es la ÚNICA forma de volver a entrar "
            "a tu caso. Si la pierdes, el dossier no puede recuperarse."
        ),
    }


@app.post("/dossiers/{dossier_id}/consentimiento")
def consentimiento_ep(dossier_id: str, req: ConsentimientoRequest):
    """Registra/revoca el consentimiento EXPRESO para entrenamiento.

    LFPDPPP 2025: opt-in separado del servicio, revocable, con timestamp
    y versión del aviso como prueba. Solo alimenta el adapter GENERAL;
    los datos de bufetes jamás entran ahí.
    """
    from ai_justicia.dossiers import store as dstore
    import uuid as _uuid
    try:
        did = _uuid.UUID(dossier_id)
    except ValueError:
        raise HTTPException(400, "dossier_id inválido")

    if req.otorgar:
        ok = dstore.otorgar_consentimiento(did)
        accion = "otorgado"
    else:
        ok = dstore.revocar_consentimiento(did)
        accion = "revocado"
    if not ok:
        raise HTTPException(409, f"Consentimiento ya estaba en ese estado")
    return {"dossier_id": dossier_id, "consentimiento": accion}


@app.get("/dossiers/{dossier_id}")
def obtener_dossier_ep(dossier_id: str):
    """Estado del dossier (incluye estado de consentimiento)."""
    from ai_justicia.dossiers import store as dstore
    import uuid as _uuid
    try:
        did = _uuid.UUID(dossier_id)
    except ValueError:
        raise HTTPException(400, "dossier_id inválido")
    d = dstore.obtener_dossier(did)
    if not d:
        raise HTTPException(404, "Dossier no encontrado")
    return d


class AbogadoRegistroRequest(BaseModel):
    cedula: str = Field(..., min_length=5, max_length=20, description="Cédula profesional")
    especialidades: list[str] | None = Field(None, description="Áreas de práctica")
    bufete_nombre: str | None = Field(None, max_length=200, description="Nombre del despacho (opcional)")


@app.post("/abogados/registro")
def registro_abogado_ep(req: AbogadoRegistroRequest):
    """Alta de abogado: cédula + especialidades + bufete opcional.

    La verificación de cédula (RENAJU) es Fase E; por ahora queda
    pendiente de verificación. La frase permite re-entrar a su cuenta.
    Sus datos alimentan SOLO el adapter de su bufete, jamás el general.
    """
    from ai_justicia.dossiers import store as dstore
    actor_id, frase, bufete_id = dstore.crear_abogado(
        cedula=req.cedula.strip(),
        especialidades=[e[:60] for e in (req.especialidades or [])][:8],
        bufete_nombre=req.bufete_nombre.strip() if req.bufete_nombre else None,
    )
    return {
        "actor_id": str(actor_id),
        "bufete_id": str(bufete_id) if bufete_id else None,
        "frase_recuperacion": frase,
        "verificacion": "pendiente",
        "nota_adapter": (
            "Los datos de tu bufete entrenan únicamente el modelo privado de tu "
            "despacho. Jamás entran al modelo general ni al de otros bufetes."
        ),
    }


# ── Autenticación: frase / dispositivo / Google ────────────────────────────

class FraseLoginRequest(BaseModel):
    frase: str = Field(..., min_length=10, description="Frase de recuperación de 12 palabras")


class DispositivoLoginRequest(BaseModel):
    token: str = Field(..., min_length=20, description="Token de dispositivo guardado en el navegador")


class DispositivoRegistroRequest(BaseModel):
    actor_id: str
    token: str = Field(..., min_length=20)


class GoogleLoginRequest(BaseModel):
    google_sub: str = Field(..., description="Subject ID único de Google")
    email: str | None = None


def _sesion_resp(s: dict) -> dict:
    return {
        "actor_id": s["actor_id"],
        "tipo": "abogado" if s["es_abogado"] else "ciudadano",
        "dossier_id": s.get("dossier_id"),
        "bufete_id": s.get("bufete_id"),
        "email": s.get("email"),
    }


@app.post("/auth/frase")
def auth_frase(req: FraseLoginRequest):
    """Re-entrada con la frase de recuperación (ciudadano o abogado)."""
    from ai_justicia.dossiers import store as dstore
    s = dstore.entrar_con_frase(req.frase.strip())
    if not s:
        raise HTTPException(401, "Frase incorrecta. Revisa que sean tus 12 palabras.")
    return _sesion_resp(s)


@app.post("/auth/dispositivo")
def auth_dispositivo(req: DispositivoLoginRequest):
    """Re-entrada de un toque con el token guardado en este navegador."""
    from ai_justicia.dossiers import store as dstore
    s = dstore.entrar_con_dispositivo(req.token.strip())
    if not s:
        raise HTTPException(401, "Este dispositivo ya no está vinculado. Usa tu frase.")
    return _sesion_resp(s)


@app.post("/auth/dispositivo/registrar")
def auth_dispositivo_registrar(req: DispositivoRegistroRequest):
    """Vincula el navegador actual tras un login exitoso (one-tap la próxima vez)."""
    from ai_justicia.dossiers import store as dstore
    import uuid as _uuid
    try:
        aid = _uuid.UUID(req.actor_id)
    except ValueError:
        raise HTTPException(400, "actor_id inválido")
    dstore.registrar_dispositivo(aid, req.token.strip())
    return {"ok": True}


@app.post("/auth/google")
def auth_google(req: GoogleLoginRequest):
    """Find-or-create por Google (llamado por el callback OAuth del frontend)."""
    from ai_justicia.dossiers import store as dstore
    s = dstore.entrar_o_crear_con_google(req.google_sub.strip(), req.email)
    return _sesion_resp(s)


@app.get("/admin/rag-results")
def admin_rag_results():
    """Resultados del último batch de preguntas procesadas por RAG.
    Lee data/rag_results.jsonl del engine."""
    import json as _json
    from pathlib import Path

    results_file = Path(__file__).resolve().parents[2] / "data" / "rag_results.jsonl"
    if not results_file.exists():
        return {"results": [], "total": 0, "answered": 0, "abstained": 0}

    results = []
    with open(results_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    results.append(_json.loads(line))
                except _json.JSONDecodeError:
                    continue

    answered = sum(1 for r in results if not r.get("abstencion"))
    abstained = sum(1 for r in results if r.get("abstencion"))

    return {
        "results": results,
        "total": len(results),
        "answered": answered,
        "abstained": abstained,
        "answer_rate": round(answered / max(len(results), 1) * 100, 1),
    }


def _count_health(status: str) -> int:
    import psycopg
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM source_health WHERE health_status = %s AND enabled = TRUE",
                (status,),
            )
            return cur.fetchone()[0]


def run() -> None:
    """Punto de entrada para `aij-serve` (uvicorn)."""
    import uvicorn
    uvicorn.run(
        "ai_justicia.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
