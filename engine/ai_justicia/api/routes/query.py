"""Rutas de consulta: pipeline jurídico, streaming SSE, jobs de ingesta."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from ai_justicia.config import settings
from ai_justicia.corpus.store import count_chunks, count_documentos
from ai_justicia.jobs.store import obtener_job
from ai_justicia.llm.client import check_connection
from ai_justicia.pipeline.orchestrator import RespuestaPipeline, ejecutar_consulta

logger = logging.getLogger(__name__)
router = APIRouter(tags=["query"])


# --- Schemas ---
class TurnoHistorial(BaseModel):
    role: str = Field(..., description="user | assistant")
    text: str = Field(..., max_length=4000, description="Texto del turno")


class QueryRequest(BaseModel):
    consulta: str = Field(..., min_length=3, max_length=2000, description="Pregunta jurídica del usuario")
    nivel: str = Field("Nivel0", description="Nivel de servicio: Nivel0 (ciudadano) | Nivel1 | Nivel2 (abogado)")
    webhook_url: str | None = Field(None)
    respuestas_aclaratorias: dict[str, str] | None = Field(None)
    respuestas_acumuladas: dict[str, str] | None = Field(None)
    expediente_prev: dict | None = Field(None)
    historial: list[TurnoHistorial] | None = Field(None)
    # F3: caso con bóveda — Izel cita los documentos (requiere JWT con acceso)
    dossier_id: str | None = Field(None, max_length=64)

    @field_validator("webhook_url")
    @classmethod
    def _webhook_seguro(cls, v: str | None) -> str | None:
        """A6: el worker hará POST a esta URL — solo https público (guard SSRF)."""
        if not v:
            return v
        from urllib.parse import urlparse
        u = urlparse(v)
        host = (u.hostname or "").lower()
        if u.scheme != "https":
            raise ValueError("webhook_url debe ser https://")
        if (not host or host in ("localhost", "0.0.0.0", "::1")
                or host.startswith("127.") or host.startswith("10.")
                or host.startswith("192.168.") or host.startswith("169.254.")
                or (host.startswith("172.") and host.split(".")[1].isdigit()
                    and 16 <= int(host.split(".")[1]) <= 31)):
            raise ValueError("webhook_url no puede apuntar a redes privadas")
        return v


class QueryResponse(BaseModel):
    estado: str
    abstenido: bool
    respuesta: str
    analisis: dict
    pasajes: list[dict]
    verificacion: dict
    duracion_ms: int
    traza_id: int | None
    tipo_abstencion: str | None = None
    job_id: int | None = None
    norma_faltante: str | None = None


class JobStatus(BaseModel):
    job_id: int
    estado: str
    consulta: str | None = None
    norma_faltante: str | None = None
    fuente: str | None = None



def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


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




@router.get("/health")
def health() -> dict:
    """Estado del servidor de inferencia y la base de datos."""
    conn = check_connection()
    try:
        n_docs = count_documentos()
        n_chunks = count_chunks()
    except Exception:  # noqa: BLE001
        logger.exception("Fallo contando corpus para /health")
        n_docs, n_chunks = -1, -1
    return {
        "status": "ok" if conn["ok"] and n_docs >= 0 else "degraded",
        "lmstudio": conn,
        "corpus": {"documentos": n_docs, "chunks": n_chunks},
    }


@router.post("/query/stream")
async def query_stream(req: QueryRequest, request: Request):
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

    # F3: documentos de la bóveda del caso — Izel los cita. Opcional: si el
    # JWT no es válido o no hay acceso, simplemente no hay contexto extra.
    documentos_ctx = ""
    if req.dossier_id and request is not None:
        try:
            import uuid as _uuid
            from ai_justicia.auth.jwt import verificar_token
            from ai_justicia.dossiers import boveda, store as dstore
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                claims = verificar_token(auth_header[7:])
                if claims and dstore.tiene_acceso(
                        _uuid.UUID(req.dossier_id), _uuid.UUID(claims["sub"]),
                        claims.get("bufete")):
                    documentos_ctx = boveda.textos_para_contexto(_uuid.UUID(req.dossier_id))
        except Exception:
            documentos_ctx = ""

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
            # F3: los documentos de la bóveda del caso (contratos, recibos…)
            if documentos_ctx:
                consulta_completa = (
                    f"{consulta_completa}\n\nDocumentos adjuntos del caso "
                    f"(contratos/escritos subidos por el usuario):\n{documentos_ctx}")

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
            # (F3: consulta_completa incluye hechos del expediente Y los
            # documentos de la bóveda — sin esto el modelo "no ve" el contrato)
            respuesta_gen = await asyncio.to_thread(
                generar, consulta_completa, pasajes, req.nivel)

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


@router.post("/query", response_model=QueryResponse)
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


@router.get("/jobs/{job_id}", response_model=JobStatus)
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
        # A5: sin consulta del usuario (endpoint público/enumerable); el
        # frontend solo necesita estado + norma para el polling.
        consulta=None,
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
