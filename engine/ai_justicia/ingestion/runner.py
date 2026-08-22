"""Runner: ejecuta UNA fuente end-to-end con instrumentación completa.

1. Abre ingestion_runs row (status='running')
2. Hash del listado (detectar cambios estructurales)
3. Adapter.listar_desde() → obtener documentos
4. Por cada documento: obtener_texto + upsert + chunk
5. Cierra ingestion_runs row con resultados
6. Recalcula health_status

Reemplaza la función ingestar_adapter() de ingest_all.py con versión instrumentada.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime
from typing import Any

from ai_justicia.config import settings
from ai_justicia.corpus.adapters.base import metadata_a_documento
from ai_justicia.corpus.store import batch_upsert_documentos, count_documentos
from ai_justicia.ingestion.health import recalcular_salud
from ai_justicia.ingestion.store import crear_run, completar_run, obtener_health

logger = logging.getLogger(__name__)


def run_source(fuente: str, entidad: str, trigger: str = "scheduled") -> dict:
    """Ejecuta la ingesta de una fuente. Devuelve un resumen.

    Args:
        fuente: 'SJF', 'DOF', 'LeyesBiblio', 'GacetaEstatal'
        entidad: 'Federal', 'Ciudad de México', 'Nuevo León', etc.
        trigger: 'scheduled' | 'manual' | 'backfill'
    """
    # Leer health para obtener adapter_class y watermark
    health = obtener_health(fuente, entidad if entidad != "Federal" else None)
    if not health:
        return {"error": f"No hay source_health para {fuente}/{entidad}"}

    if not health.get("enabled", True):
        return {"error": f"Fuente {fuente}/{entidad} deshabilitada"}

    adapter_class = health["adapter_class"]
    watermark_before = health.get("watermark")
    expected_min = health.get("expected_min_results", 1)
    prev_hash = health.get("listing_page_hash")

    # Crear run row
    run_id = crear_run(fuente, entidad if entidad != "Federal" else None, trigger, watermark_before)
    logger.info("▶ Run #%d: %s/%s (trigger=%s, watermark=%s)", run_id, fuente, entidad, trigger, watermark_before)

    docs_fetched = 0
    docs_new = 0
    docs_updated = 0
    docs_errored = 0
    http_codes: list[int] = []
    listing_hash = None
    hash_changed = False
    error_msg = None
    error_count = 0
    chunks_indexed = 0

    try:
        # Obtener adapter dinámicamente
        adapter = _get_adapter(adapter_class, entidad)

        # Hash del listado (Detector B)
        listing_hash = _hash_listing(adapter, fuente, entidad)
        if listing_hash and prev_hash and listing_hash != prev_hash:
            hash_changed = True
            logger.warning("Hash del listado cambió en %s/%s!", fuente, entidad)

        # Listar documentos
        docs_buffer = []
        for meta in adapter.listar_desde(watermark_before):
            docs_fetched += 1
            meta.extra["_texto_usable"] = meta.titulo  # fallback

            # Obtener texto
            try:
                texto = adapter.obtener_texto(meta)
                if len(texto) < 50:
                    docs_errored += 1
                    continue
                meta.extra["_texto_usable"] = texto
            except Exception as e:
                docs_errored += 1
                error_count += 1
                if error_count <= 3:
                    logger.warning("  ✗ %s: %s", meta.id_externo, str(e)[:80])
                continue

            docs_buffer.append(meta)

            # Flush cada 50
            if len(docs_buffer) >= 50:
                _count_before = count_documentos()
                docs = [metadata_a_documento(m, m.extra.get("_texto_usable", m.titulo)) for m in docs_buffer]
                batch_upsert_documentos(docs)
                _count_after = count_documentos()
                docs_new += max(0, _count_after - _count_before)
                docs_buffer = []

        # Flush final
        if docs_buffer:
            _count_before = count_documentos()
            docs = [metadata_a_documento(m, m.extra.get("_texto_usable", m.titulo)) for m in docs_buffer]
            batch_upsert_documentos(docs)
            _count_after = count_documentos()
            docs_new += max(0, _count_after - _count_before)

        # Determinar status
        if docs_fetched == 0 and docs_errored == 0:
            run_status = "empty_suspicious"
        elif docs_errored > 0 and docs_new == 0:
            run_status = "failed"
            error_msg = f"{docs_errored} documentos con errores de extracción"
        elif docs_errored > 0:
            run_status = "partial"
        else:
            run_status = "success"

        # Generar embeddings si hay chunks pendientes
        if docs_new > 0:
            from ai_justicia.corpus.store import count_chunks_sin_embedding, indexar_chunks_pendientes
            pendientes = count_chunks_sin_embedding()
            if pendientes > 0:
                chunks_indexed = indexar_chunks_pendientes(lote=64)

    except Exception as e:
        run_status = "failed"
        error_msg = str(e)[:500]
        error_count += 1
        logger.exception("Run #%d falló: %s", run_id, e)

    # Watermark después
    watermark_after = date.today() if run_status in ("success", "partial") else watermark_before

    # Total documentos en la fuente
    import psycopg
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            if entidad == "Federal":
                cur.execute("SELECT COUNT(*) FROM documentos WHERE fuente = %s", (fuente,))
            else:
                cur.execute("SELECT COUNT(*) FROM documentos WHERE fuente = %s AND entidad = %s", (fuente, entidad))
            total_docs = cur.fetchone()[0]

    # Cerrar run
    completar_run(
        run_id=run_id,
        status=run_status,
        documentos_fetched=docs_fetched,
        documentos_new=docs_new,
        documentos_updated=docs_updated,
        documentos_errored=docs_errored,
        http_status_codes=http_codes,
        listing_page_hash=listing_hash,
        hash_changed=hash_changed,
        error_message=error_msg,
        error_count=error_count,
        watermark_after=watermark_after,
        chunks_indexed=chunks_indexed,
    )

    # Recalcular salud
    health_status = recalcular_salud(
        fuente=fuente,
        entidad=entidad,
        run_status=run_status,
        documentos_new=docs_new,
        documentos_fetched=docs_fetched,
        hash_changed=hash_changed,
        watermark_after=watermark_after,
        total_documentos=total_docs,
        listing_page_hash=listing_hash,
    )

    # Timestamp de descarga para el log
    descargado_en = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    logger.info("✓ Run #%d: %s/%s → %s (%d fetched, %d new, %d errors) → %s [descargado: %s]",
                run_id, fuente, entidad, run_status, docs_fetched, docs_new, docs_errored,
                health_status, descargado_en)

    return {
        "run_id": run_id,
        "fuente": fuente,
        "entidad": entidad,
        "status": run_status,
        "health": health_status,
        "fetched": docs_fetched,
        "new": docs_new,
        "errored": docs_errored,
        "hash_changed": hash_changed,
        "watermark_after": watermark_after.isoformat() if watermark_after else None,
        "total_documentos": total_docs,
        "descargado_en": descargado_en,
    }


def _get_adapter(adapter_class: str, entidad: str = ""):
    """Factory: devuelve el adapter por nombre de clase."""
    from ai_justicia.corpus.adapters.sjf import SJFAdapter
    from ai_justicia.corpus.adapters.dof import DOFAdapter
    from ai_justicia.corpus.adapters.leyes_biblio import LeyesBiblioAdapter
    from ai_justicia.corpus.adapters.edomex import EdomexAdapter
    from ai_justicia.corpus.adapters.nuevo_leon import NuevoLeonAdapter
    from ai_justicia.corpus.adapters.jalisco import JaliscoAdapter
    from ai_justicia.corpus.adapters.generico import EstadoGenericoAdapter, ESTADOS_URLS

    # Adapters dedicados
    dedicated = {
        "sjf": lambda: SJFAdapter(),
        "dof": lambda: DOFAdapter(),
        "leyes_biblio": lambda: LeyesBiblioAdapter(),
        "edomex": lambda: EdomexAdapter(),
        "nuevo_leon": lambda: NuevoLeonAdapter(),
        "jalisco": lambda: JaliscoAdapter(),
    }

    if adapter_class in dedicated:
        return dedicated[adapter_class]()

    # Adapter genérico: funciona para cualquier estado que tenga portal_url en la DB
    if adapter_class == "generico":
        return EstadoGenericoAdapter(entidad)

    # Adapter Playwright para estados JS-rendered
    if adapter_class == "playwright":
        from ai_justicia.corpus.adapters.playwright_adapter import PlaywrightAdapter
        return PlaywrightAdapter(entidad)

    raise ValueError(f"Adapter '{adapter_class}' para '{entidad}' no registrado.")


def _hash_listing(adapter, fuente: str, entidad: str) -> str | None:
    """Genera un hash del HTML del listado de la fuente para detectar cambios.

    No todos los adapters tienen una URL de listado fácilmente hasheable.
    Para los que sí (SJF, DOF), la generamos. Para otros, retorna None.
    """
    try:
        if fuente == "SJF":
            from ai_justicia.corpus.http_client import EducationalHTTPClient
            client = EducationalHTTPClient(referer="https://sjf2.scjn.gob.mx/")
            resp = client.post(
                "https://sjf2.scjn.gob.mx/services/sjftesismicroservice/api/public/tesis?page=0&size=1",
                json_body={"criteria": {"searchTerms": [], "classifiers": []}},
            )
            return hashlib.sha256(resp.content).hexdigest()[:32]
        elif fuente == "DOF":
            from ai_justicia.corpus.http_client import EducationalHTTPClient
            from datetime import date
            client = EducationalHTTPClient(verify_tls=False)
            resp = client.get(
                "https://www.dof.gob.mx/index_111.php",
                params={"year": date.today().year, "month": date.today().month, "day": date.today().day},
            )
            # Normalizar: quitar scripts, styles, whitespace
            html = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', resp.text, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'\s+', ' ', html).strip()
            return hashlib.sha256(html.encode()).hexdigest()[:32]
    except Exception as e:
        logger.debug("No se pudo hash listing de %s: %s", fuente, e)
    return None
