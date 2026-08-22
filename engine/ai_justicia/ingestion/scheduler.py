"""Scheduler entrypoint para el subsistema de adquisición de datos.

Uso:
    python -m ai_justicia.ingestion.scheduler              # todas las fuentes habilitadas
    python -m ai_justicia.ingestion.scheduler --source SJF # una fuente específica
    python -m ai_justicia.ingestion.scheduler --list       # solo listar estado
"""

from __future__ import annotations

import argparse
import logging
import sys

from ai_justicia.config import settings
from ai_justicia.ingestion.runner import run_source
from ai_justicia.ingestion.store import listar_sources_health

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ingestion.scheduler")


def main():
    parser = argparse.ArgumentParser(description="Scheduler de adquisición de datos")
    parser.add_argument("--source", type=str, help="Fuente específica (formato: FUENTE/ENTIDAD)")
    parser.add_argument("--list", action="store_true", help="Solo listar estado de fuentes")
    parser.add_argument("--trigger", default="scheduled", help="scheduled | manual | backfill")
    args = parser.parse_args()

    sources = listar_sources_health()

    if args.list:
        print(f"{'Fuente':<16} {'Entidad':<22} {'Status':<12} {'Enabled':<8} {'Docs':<8} {'Last Run'}")
        print("-" * 90)
        for s in sources:
            last = s.get("last_run_at")
            last_str = last.strftime("%Y-%m-%d %H:%M") if last else "nunca"
            flag = "✅" if s["enabled"] else "⬜"
            print(f"{s['fuente']:<16} {s['entidad']:<22} {s['health_status']:<12} {flag:<8} {s['total_documentos']:<8} {last_str}")
        return

    # Filtrar fuentes a ejecutar
    if args.source:
        parts = args.source.split("/")
        fuente = parts[0]
        entidad = parts[1] if len(parts) > 1 else "Federal"
        to_run = [s for s in sources if s["fuente"] == fuente and s["entidad"] == entidad]
    else:
        to_run = [s for s in sources if s["enabled"]]

    logger.info("╔══════════════════════════════════════════════╗")
    logger.info("║   SCHEDULER — Adquisición de Datos           ║")
    logger.info("╚══════════════════════════════════════════════╝")
    logger.info("Fuentes a ejecutar: %d", len(to_run))

    results = []
    for s in to_run:
        try:
            result = run_source(s["fuente"], s["entidad"], trigger=args.trigger)
            results.append(result)
        except Exception as e:
            logger.error("Error en %s/%s: %s", s["fuente"], s["entidad"], e)
            results.append({"fuente": s["fuente"], "entidad": s["entidad"], "error": str(e)})

    # Resumen
    logger.info("")
    logger.info("╔══════════════════════════════════════════════╗")
    logger.info("║   RESUMEN                                    ║")
    logger.info("╚══════════════════════════════════════════════╝")
    total_new = sum(r.get("new", 0) for r in results)
    total_err = sum(r.get("errored", 0) if isinstance(r.get("errored"), int) else 0 for r in results)
    healthy = sum(1 for r in results if r.get("health") == "healthy")
    unhealthy = sum(1 for r in results if r.get("health") == "unhealthy")

    for r in results:
        status = r.get("status", "error")
        new = r.get("new", 0)
        health = r.get("health", "?")
        descargado = r.get("descargado_en", "—")
        total = r.get("total_documentos", 0)
        logger.info("  %s/%s: %s (%d new, total %d) → %s [descargado: %s]",
                    r["fuente"], r["entidad"], status, new, total, health, descargado)

    logger.info("")
    logger.info("Total nuevos: %d | Sanos: %d | En problemas: %d", total_new, healthy, unhealthy)


if __name__ == "__main__":
    main()
