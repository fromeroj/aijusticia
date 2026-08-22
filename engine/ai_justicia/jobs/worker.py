"""Worker de la cola de ingesta on-demand (Caso B).

Loop que:
  1. Toma el próximo job pendiente (atómico, SKIP LOCKED)
  2. Selecciona el adapter según la fuente
  3. Descarga la norma faltante → upsert → chunk_and_index
  4. Recarga el índice BM25
  5. Re-ejecuta el pipeline sobre la consulta original
  6. Guarda la respuesta, marca completado
  7. Notifica webhook si aplica

Sobrevive reinicios porque el estado está en Postgres.

Uso:
    from ai_justicia.jobs.worker import run_worker
    run_worker(poll_interval=5)  # loop infinito

    # o desde CLI:
    python scripts/run_worker.py
"""

from __future__ import annotations

import logging
import time

from ai_justicia.corpus.adapters.base import DocumentoMetadata
from ai_justicia.corpus.models import Fuente
from ai_justicia.jobs.models import EstadoJob, PendingJob
from ai_justicia.jobs.store import actualizar_estado, marcar_completado, marcar_fallido, siguiente_pendiente
from ai_justicia.retrieval.bm25_index import reload_bm25_index

logger = logging.getLogger(__name__)


def procesar_job(job: PendingJob) -> None:
    """Procesa un job individual: descarga norma → ingesta → reintenta pipeline."""
    logger.info("=== Procesando job %d: %s (fuente=%s) ===", job.id, job.norma_faltante, job.fuente)
    try:
        # 1. Descargar la norma faltante vía el adapter correspondiente
        actualizar_estado(job.id, EstadoJob.DESCARGANDO)
        n_docs = _descargar_e_ingestar(job)

        if n_docs == 0:
            marcar_fallido(
                job.id,
                f"No se pudo descargar {job.norma_faltante} de {job.fuente} "
                f"(id_externo={job.id_externo}). El adapter no encontró el documento.",
            )
            return

        logger.info("Job %d: %d documento(s) ingresado(s)", job.id, n_docs)

        # 2. Recargar el índice BM25 (el vectorial lee la DB directamente)
        actualizar_estado(job.id, EstadoJob.INGIRIENDO)
        reload_bm25_index()
        logger.info("Job %d: índice BM25 recargado", job.id)

        # 3. Re-ejecutar el pipeline sobre la consulta original
        from ai_justicia.pipeline.orchestrator import ejecutar_consulta
        logger.info("Job %d: re-ejecutando pipeline...", job.id)
        resultado = ejecutar_consulta(job.consulta, nivel="Nivel0")

        # 4. Guardar respuesta y marcar completado
        marcar_completado(job.id, resultado.respuesta, traza_reintento=resultado.traza_id)
        logger.info("Job %d: completado. Respuesta (%d chars)", job.id, len(resultado.respuesta))

        # 5. Notificar webhook si el cliente lo pidió
        if job.webhook_url:
            _notificar_webhook(job, resultado.respuesta)

    except Exception as e:  # noqa: BLE001
        logger.exception("Job %d falló", job.id)
        marcar_fallido(job.id, f"{type(e).__name__}: {e}")


def _descargar_e_ingestar(job: PendingJob) -> int:
    """Descarga la norma faltante según la fuente y la ingiere.

    Devuelve el número de documentos ingresados (0 si no se pudo).
    """
    from ai_justicia.corpus.adapters.base import metadata_a_documento
    from ai_justicia.corpus.store import chunk_and_index, upsert_documento

    fuente = (job.fuente or "").upper()

    if fuente == "SJF":
        from ai_justicia.corpus.adapters.sjf import SJFAdapter
        adapter = SJFAdapter()
        # Si tenemos id_externo (registro SJF), descargar esa tesis específica
        if job.id_externo:
            return _ingestar_por_id_externo(adapter, job)
        # Si solo tenemos descripción de la norma, buscar por título
        return _buscar_e_ingestar(adapter, job)

    if fuente in ("LEYESBIBLIO", "DOF"):
        # Estos adapters no existen todavía — marcar como fallido con mensaje claro
        logger.warning("Job %d: adapter %s no implementado aún", job.id, fuente)
        return 0

    logger.warning("Job %d: fuente desconocida '%s'", job.id, fuente)
    return 0


def _ingestar_por_id_externo(adapter, job: PendingJob) -> int:
    """Descarga un documento por su id_externo (ej. registro SJF) y lo ingiere."""
    from ai_justicia.corpus.adapters.base import metadata_a_documento
    from ai_justicia.corpus.store import chunk_and_index, upsert_documento

    meta = DocumentoMetadata(
        id_externo=job.id_externo,
        fuente=Fuente(job.fuente),
        titulo=job.norma_faltante or job.id_externo,
        fecha_publicacion=__import__("datetime").date.today(),
        extra={},
    )
    texto = adapter.obtener_texto(meta)
    if not texto.strip():
        return 0
    doc = metadata_a_documento(meta, texto)
    doc_id = upsert_documento(doc)
    chunk_and_index(doc, doc_id)
    return 1


def _buscar_e_ingestar(adapter, job: PendingJob) -> int:
    """Busca la norma por título en el adapter y ingiere la primera coincidencia."""
    from datetime import date

    from ai_justicia.corpus.adapters.base import metadata_a_documento
    from ai_justicia.corpus.store import chunk_and_index, upsert_documento

    # Listar recientes y buscar por título (búsqueda simple)
    for meta in adapter.listar_desde(date(2020, 1, 1), max_pages=5):
        if job.norma_faltante and job.norma_faltante.lower() in meta.titulo.lower():
            texto = adapter.obtener_texto(meta)
            doc = metadata_a_documento(meta, texto)
            doc_id = upsert_documento(doc)
            chunk_and_index(doc, doc_id)
            return 1
    return 0


def _notificar_webhook(job: PendingJob, respuesta: str) -> None:
    """POST al webhook_url del cliente con el resultado."""
    import requests
    try:
        requests.post(
            job.webhook_url,
            json={"job_id": job.id, "estado": "completado", "respuesta": respuesta},
            timeout=10,
        )
        logger.info("Job %d: webhook notificado", job.id)
    except Exception as e:  # noqa: BLE001
        logger.warning("Job %d: webhook falló (%s)", job.id, e)


def run_worker(poll_interval: float = 5.0, max_jobs: int | None = None) -> None:
    """Loop principal del worker.

    Args:
        poll_interval: segundos entre polls cuando no hay jobs.
        max_jobs: si se setea, procesa N jobs y termina (útil para tests).
    """
    logger.info("Worker iniciado (poll cada %.1fs)", poll_interval)
    procesados = 0
    while True:
        job = siguiente_pendiente()
        if job is None:
            time.sleep(poll_interval)
            continue
        procesar_job(job)
        procesados += 1
        if max_jobs and procesados >= max_jobs:
            logger.info("Worker: %d jobs procesados, terminando", procesados)
            return
