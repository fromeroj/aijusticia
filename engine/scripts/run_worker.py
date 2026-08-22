"""Worker CLI — procesa la cola de ingesta on-demand (Caso B).

Loop que toma jobs pendientes de la DB, descarga la norma faltante,
la ingiere y re-ejecuta el pipeline.

Uso:
    python scripts/run_worker.py                  # loop infinito
    python scripts/run_worker.py --once           # procesa 1 job y termina
    python scripts/run_worker.py --interval 3     # poll cada 3s
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_justicia.config import settings
from ai_justicia.jobs.worker import run_worker


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker de ingesta on-demand (Caso B)")
    parser.add_argument("--once", action="store_true", help="Procesa 1 job y termina")
    parser.add_argument("--interval", type=float, default=5.0, help="Intervalo de poll (s)")
    args = parser.parse_args()

    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    max_jobs = 1 if args.once else None
    run_worker(poll_interval=args.interval, max_jobs=max_jobs)


if __name__ == "__main__":
    main()
