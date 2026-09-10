"""Rutas de administración: fuentes, stats, harvesters, preguntas, rag-results."""
from __future__ import annotations

import json as _json
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ai_justicia.config import settings
from ai_justicia.corpus.store import count_documentos, count_chunks

router = APIRouter(prefix="/admin", tags=["admin"])


def _count_health(status: str) -> int:
    import psycopg
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM source_health WHERE health_status = %s AND enabled = TRUE",
                (status,),
            )
            return cur.fetchone()[0]





@router.get("/sources")
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


@router.get("/sources/{fuente}/runs")
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


@router.post("/sources/{fuente}/trigger")
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


@router.patch("/sources/{fuente}")
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


@router.get("/stats")
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







@router.get("/rag-results")
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




@router.get("/harvesters")
def admin_harvesters():
    """Registro de harvesters: fuentes, URLs, scripts y estado diferencial."""
    import psycopg
    conn = psycopg.connect(host="127.0.0.1", port=5432, dbname="aijusticia",
                           user="aijusticia", password=settings.pg_password)
    cur = conn.cursor()
    cur.execute("""
        SELECT fuente, nombre, descripcion, metodo, origen_url, ejecucion,
               diferencial, frecuencia, completa, estado, ultima_ejecucion
        FROM harvest_scripts ORDER BY fuente
    """)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return {"harvesters": rows}


@router.get("/preguntas")
def admin_preguntas(fuente: str | None = None, idioma: str | None = None, q: str | None = None,
                    limit: int = 50, offset: int = 0, solo_sin_traducir: bool = False):
    """Preguntas del corpus de evaluación/SFT con filtros y búsqueda."""
    import psycopg
    conn = psycopg.connect(host="127.0.0.1", port=5432, dbname="aijusticia",
                           user="aijusticia", password=settings.pg_password)
    cur = conn.cursor()
    where, params = [], []
    if fuente:
        where.append("fuente=%s"); params.append(fuente)
    if idioma:
        where.append("idioma=%s"); params.append(idioma)
    if q:
        where.append("texto ILIKE %s"); params.append(f"%{q}%")
    if solo_sin_traducir:
        where.append("traducido=false")
    w = (" WHERE " + " AND ".join(where)) if where else ""
    cur.execute(f"SELECT count(*) FROM preguntas{w}", params)
    total = cur.fetchone()[0]
    cur.execute(f"SELECT id, texto, idioma, fuente, texto_es, traducido FROM preguntas{w} ORDER BY id LIMIT %s OFFSET %s",
                params + [limit, offset])
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.execute("SELECT fuente, count(*) FROM preguntas GROUP BY fuente ORDER BY 2 DESC")
    fuentes = {f: c for f, c in cur.fetchall()}
    conn.close()
    return {"total": total, "preguntas": rows, "fuentes": fuentes}
