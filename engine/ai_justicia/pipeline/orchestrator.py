"""Orquestador del pipeline end-to-end.

Conecta las 5 etapas:
  1. Análisis de consulta (materia, jurisdicción, vigencia)
  2. Recuperación híbrida (BM25 + vectorial, reformulate-and-retry)
  3. Reranking jurídico (art. 133, vinculante vs persuasivo)
  4. Generación anclada (contrato estricto de citas, NO SUSTENTADO)
  5. Verificación dual (resolvedor de citas + NLI) + abstención

Persiste una traza en la tabla `trazas` para auditoría y trazabilidad.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass

import psycopg

from ai_justicia.config import settings
from ai_justicia.corpus.store import get_conn
from ai_justicia.llm.generate import RespuestaGenerada
from ai_justicia.pipeline.query_analysis import AnalisisConsulta, analizar_consulta
from ai_justicia.pipeline.retrieve import recuperar_y_rerankear
from ai_justicia.pipeline.verify import ResultadoVerificacion, verificar
from ai_justicia.llm.generate import generar
from ai_justicia.retrieval.vector_index import Resultado
from ai_justicia.verification.abstention import MENSAJE_DEFERIDO, TipoAbstencion

logger = logging.getLogger(__name__)


@dataclass
class RespuestaPipeline:
    """Salida completa del pipeline, lista para devolver al usuario/API."""
    consulta: str
    abstenido: bool
    respuesta: str                    # texto final (o mensaje de abstención/deferido)
    analisis: dict                    # etapa 1
    pasajes: list[dict]               # etapas 2-3 (metadatos de los pasajes usados)
    verificacion: dict                # etapa 5 (ratio, n_sustentadas, detalle por cita)
    duracion_ms: int
    traza_id: int | None              # id en la tabla trazas
    # Caso B (norma faltante)
    tipo_abstencion: str | None = None   # 'EVIDENCIA_INSUFICIENTE' | 'NORMA_FALTANTE' | None
    job_id: int | None = None            # si Caso B y se creó job: id para polling


def ejecutar_consulta(
    consulta: str,
    nivel: str = "Nivel0",
    webhook_url: str | None = None,
) -> RespuestaPipeline:
    """Ejecuta el pipeline completo de 5 etapas sobre una consulta.

    Args:
        consulta: la pregunta del usuario en lenguaje natural.
        nivel: 'Nivel0' | 'Nivel1' | 'Nivel2' (para trazabilidad).
        webhook_url: si se setea y ocurre Caso B, el worker notificará aquí al completar.

    Returns:
        RespuestaPipeline con todo el estado y la respuesta final.
        Si fue Caso B, `respuesta` es el mensaje deferido y `job_id` permite el polling.
    """
    inicio = time.time()
    logger.info("=== PIPELINE START: %s (nivel=%s) ===", consulta[:80], nivel)

    # Etapa 1
    analisis = analizar_consulta(consulta)
    logger.info("Etapa 1 ✓: materia=%s jurisdiccion=%s", analisis.materia, analisis.jurisdiccion)

    # Etapas 2-3
    pasajes = recuperar_y_rerankear(consulta, analisis)
    logger.info("Etapas 2-3 ✓: %d pasajes", len(pasajes))

    # Etapa 3.5: Filtro de relevancia LLM
    # El LLM verifica cuáles pasajes son realmente relevantes para la pregunta.
    # Esto elimina ruido (manuales administrativos, temas no relacionados).
    from ai_justicia.pipeline.relevance import filtrar_relevantes
    if pasajes:
        pasajes_pre = len(pasajes)
        pasajes = filtrar_relevantes(consulta, pasajes)
        logger.info("Etapa 3.5 ✓: %d→%d pasajes relevantes", pasajes_pre, len(pasajes))

    # Etapa 4
    respuesta_gen = generar(consulta, pasajes)
    logger.info("Etapa 4 ✓: %d oraciones, %d con cita", len(respuesta_gen.oraciones), respuesta_gen.n_sustentadas)

    # Etapa 5 (incluye diagnóstico A/B si abstiene)
    verif = verificar(respuesta_gen, pasajes, consulta=consulta)
    logger.info(
        "Etapa 5 ✓: %s (ratio=%.0f%%, tipo=%s)",
        "ABSTENCIÓN" if verif.decision.abstenido else "RESPONDER",
        verif.decision.ratio_sustento * 100,
        verif.decision.tipo.value if verif.decision.abstenido else "—",
    )

    duracion_ms = int((time.time() - inicio) * 1000)

    # Persistir traza
    traza_id = _guardar_traza(
        consulta=consulta, analisis=analisis, pasajes=pasajes,
        verif=verif, nivel=nivel, duracion_ms=duracion_ms,
    )

    # Caso B: crear job de ingesta on-demand y sobreescribir el mensaje
    job_id = None
    tipo_abstencion = None
    texto_final = verif.texto_final
    if verif.decision.abstenido:
        tipo_abstencion = verif.decision.tipo.value
        if verif.decision.tipo == TipoAbstencion.NORMA_FALTANTE:
            from ai_justicia.jobs.store import crear_job
            job_id = crear_job(
                consulta=consulta,
                norma_faltante=verif.decision.norma_faltante,
                fuente=verif.decision.fuente_faltante,
                id_externo=verif.decision.id_externo,
                traza_id=traza_id,
                webhook_url=webhook_url,
            )
            texto_final = MENSAJE_DEFERIDO.format(
                norma=verif.decision.norma_faltante or "la norma pertinente",
                job_id=job_id,
            )
            logger.info("Caso B: job %d creado para %s (fuente=%s)", job_id, verif.decision.norma_faltante, verif.decision.fuente_faltante)

    return RespuestaPipeline(
        consulta=consulta,
        abstenido=verif.decision.abstenido,
        respuesta=texto_final,
        analisis=analisis.to_dict(),
        pasajes=[_pasaje_a_dict(p) for p in pasajes],
        verificacion={
            "n_oraciones": verif.n_oraciones,
            "n_sustentadas": verif.n_sustentadas,
            "ratio_sustento": round(verif.decision.ratio_sustento, 3),
            "razon": verif.decision.razon,
            "tipo_abstencion": tipo_abstencion,
            "explicacion_diagnostico": verif.decision.explicacion,
            "citas": [_cita_a_dict(c) for c in verif.citas],
        },
        duracion_ms=duracion_ms,
        traza_id=traza_id,
        tipo_abstencion=tipo_abstencion,
        job_id=job_id,
    )


def _pasaje_a_dict(p: Resultado) -> dict:
    return {
        "titulo": p.titulo,
        "fuente": p.fuente,
        "score": round(p.score, 3),
        "vinculante": p.vinculante,
        "jerarquia": p.jerarquia,
        "clave_cita": (
            f"SJF {p.registro_sjf}" if p.registro_sjf
            else (p.titulo[:60] if p.titulo else p.fuente)
        ),
    }


def _cita_a_dict(c) -> dict:
    return {
        "texto": c.oracion.texto[:150],
        "cita_idx": c.oracion.cita_idx,
        "resolver": c.resolucion.resuelto if c.resolucion else None,
        "nli": c.nli.etiqueta if c.nli else None,
        "sustentado": c.sustentado,
    }


def _guardar_traza(
    consulta: str,
    analisis: AnalisisConsulta,
    pasajes: list[Resultado],
    verif: ResultadoVerificacion,
    nivel: str,
    duracion_ms: int,
) -> int | None:
    """Persiste la traza en la tabla trazas para auditoría."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trazas (consulta, analisis, pasajes, respuesta,
                                        n_oraciones, n_sustentadas, ratio_sustento,
                                        abstenido, nivel, duracion_ms)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        consulta,
                        psycopg.types.json.Json(analisis.to_dict()),
                        psycopg.types.json.Json([_pasaje_a_dict(p) for p in pasajes]),
                        verif.texto_final,
                        verif.n_oraciones,
                        verif.n_sustentadas,
                        verif.decision.ratio_sustento,
                        verif.decision.abstenido,
                        nivel,
                        duracion_ms,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return row[0] if row else None
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo guardar la traza: %s", e)
        return None
