"""Estado público del corpus: stats por fuente, por entidad y totales.

GET /corpus/status — sin auth; cacheado 15 min, se recalcula sin bloquear la petición.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from fastapi import APIRouter

from ai_justicia.config import settings

logger = __import__("logging").getLogger(__name__)
router = APIRouter(tags=["corpus"])

_CACHE: dict | None = None
_CACHE_AT = 0.0
CACHE_TTL = 900  # segundos: son agregados de un corpus de ~500K documentos
_REFRESCANDO = False
_lock = threading.Lock()


def _refrescar() -> None:
    """Recalcula las estadísticas (10-30s) y las publica."""
    global _CACHE, _CACHE_AT
    try:
        datos = _consultar()
    except Exception as e:
        logger.error("corpus_status: %s", str(e)[:200])
        return
    with _lock:
        _CACHE, _CACHE_AT = datos, time.time()


def _refrescar_en_segundo_plano() -> None:
    global _REFRESCANDO
    try:
        _refrescar()
    finally:
        with _lock:
            _REFRESCANDO = False

# cadencia esperada de cada fuente (días) para el semáforo de frescura
_CADENCIA = {
    "DOF": 1, "LeyesBiblio": 15, "SJF": 8,
    "SentenciasEdomex": 14, "SentenciasCDMX": 14, "SentenciasQro": 30,
    "GacetaEstatal": 7, "GacetaCDMX": 7, "SCJN-Libros": 30, "JustiaEstatal": 30,
}

# metas conocidas (para % de avance)
_METAS = {
    "LeyesBiblio": {"meta": 316, "nota": "316 leyes y códigos federales base"},
}

_ENTIDAD_A_ISO = {
    "Aguascalientes": "MXAGU", "Baja California": "MXBCN",
    "Baja California Sur": "MXBCS", "Campeche": "MXCAM",
    "Chiapas": "MXCHP", "Chihuahua": "MXCHH", "Ciudad de México": "MXCMX",
    "Coahuila": "MXCOA", "Colima": "MXCOL", "Durango": "MXDUR",
    "Estado de México": "MXMEX", "Guanajuato": "MXGUA", "Guerrero": "MXGRO",
    "Hidalgo": "MXHID", "Jalisco": "MXJAL", "Michoacán": "MXMIC",
    "Morelos": "MXMOR", "Nayarit": "MXNAY", "Nuevo León": "MXNLE",
    "Oaxaca": "MXOAX", "Puebla": "MXPUE", "Querétaro": "MXQUE",
    "Quintana Roo": "MXROO", "San Luis Potosí": "MXSLP", "Sinaloa": "MXSIN",
    "Sonora": "MXSON", "Tabasco": "MXTAB", "Tamaulipas": "MXTAM",
    "Tlaxcala": "MXTLA", "Veracruz": "MXVER", "Yucatán": "MXYUC",
    "Zacatecas": "MXZAC",
}


def _dias(fecha) -> int | None:
    if not fecha:
        return None
    return (datetime.now(timezone.utc) - fecha).days


def _consultar() -> dict:
    import psycopg

    with psycopg.connect(settings.psycopg_dsn) as conn:
        cur = conn.cursor()

        fuentes = []
        cur.execute("""
            SELECT fuente, count(*), min(fecha_publicacion), max(fecha_publicacion),
                   max(created_at)
            FROM documentos GROUP BY fuente ORDER BY count(*) DESC
        """)
        for fuente, n, fmin, fmax, cread in cur.fetchall():
            dias = _dias(cread)
            cad = _CADENCIA.get(fuente)
            if cad is None:
                estado = "estatico"
            elif dias is not None and dias <= cad * 2:
                estado = "vivo"
            elif dias is not None and dias <= cad * 4:
                estado = "tibio"
            else:
                estado = "detenido"
            item = {
                "fuente": fuente, "documentos": n,
                "inicio": fmin.isoformat() if fmin else None,
                "ultimo_doc": fmax.isoformat() if fmax else None,
                "ultima_ingesta": cread.isoformat() if cread else None,
                "dias_sin_nuevos": dias, "estado": estado,
            }
            if fuente in _METAS:
                item["meta"] = _METAS[fuente]
            fuentes.append(item)

        entidades = []
        cur.execute("""
            SELECT entidad, count(*), max(created_at)::date
            FROM documentos WHERE entidad IS NOT NULL AND entidad <> ''
            GROUP BY entidad ORDER BY count(*) DESC
        """)
        for ent, n, last in cur.fetchall():
            entidades.append({
                "entidad": ent, "iso": _ENTIDAD_A_ISO.get(ent),
                "documentos": n, "ultima": last.isoformat() if last else None,
            })

        cur.execute("SELECT count(*) FROM documentos_chunks")
        chunks = cur.fetchone()[0]

        cur.execute("SELECT count(*) FROM documentos")
        total_docs = cur.fetchone()[0]

    return {
        "generado": datetime.now(timezone.utc).isoformat(),
        "totales": {
            "documentos": total_docs,
            "chunks": chunks,
            "tokens_estimados": chunks * 280,  # ~280 tokens por chunk (calibrado)
            "fuentes": len(fuentes),
        },
        "fuentes": fuentes,
        "entidades": entidades,
        # proyectos activos con meta conocida (avances fuera de la tabla)
        "proyectos": [
            {"nombre": "Jalisco — sentencias", "fase": "descarga de PDFs (local, en curso)",
             "ids_recolectados": 16000, "meta": 84745, "unidad": "tocas"},
            {"nombre": "Estado de México", "fase": "enumeración en curso",
             "ids_recolectados": 56933, "meta": None, "unidad": "PDFs en manifiesto"},
        ],
    }


@router.get("/corpus/status")
def corpus_status():
    """Estadísticas del corpus.

    stale-while-revalidate: se entrega siempre la última versión calculada y, si
    venció, se recalcula en un hilo aparte. Recalcular cuesta 10-30s (un COUNT(*)
    sobre 18M chunks); con la petición bloqueada, dos corridas de CI solapadas
    bastaban para que /corpus/status tardara más que el timeout del monitor.
    El campo `generado` dice cuándo se calcularon los números entregados.
    """
    global _REFRESCANDO
    with _lock:
        cache, vencido = _CACHE, time.time() - _CACHE_AT > CACHE_TTL
        lanzar = vencido and not _REFRESCANDO
        if lanzar:
            _REFRESCANDO = True
    if cache is None:
        # primera llamada tras arrancar: no hay nada que entregar, sí se espera
        _refrescar()
        with _lock:
            return _CACHE if _CACHE is not None else {"error": "estadísticas no disponibles"}
    if lanzar:
        threading.Thread(target=_refrescar_en_segundo_plano, daemon=True).start()
    return cache
