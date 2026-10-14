"""Ingesta tesis del SJF (Semanario Judicial de la Federación).

Uso:
    python scripts/ingest_sjf.py                          # solo primera página (lo más reciente)
    python scripts/ingest_sjf.py --desde 2025-01-01       # desde fecha
    python scripts/ingest_sjf.py --paginas 10             # N páginas
    python scripts/ingest_sjf.py --detalle                # obtener texto completo (lento)
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_justicia.corpus.adapters.sjf import SJFAdapter
from ai_justicia.corpus.models import Fuente
from ai_justicia.corpus.store import chunk_and_index, count_chunks, count_documentos, upsert_documento
from ai_justicia.corpus.watermark import guardar_watermark, leer_watermark


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingesta tesis del SJF")
    parser.add_argument("--desde", type=str, help="Fecha inicial YYYY-MM-DD (default: watermark)")
    parser.add_argument("--paginas", type=int, default=50, help="Máximo de páginas (default 50)")
    parser.add_argument("--detalle", action="store_true", help="Obtener texto completo vía detalle (lento)")
    parser.add_argument("--limite", type=int, help="Máximo número de tesis a procesar")
    args = parser.parse_args()

    # Determinar fecha de inicio
    if args.desde:
        desde = date.fromisoformat(args.desde)
    else:
        desde = leer_watermark(Fuente.SJF)
        if desde is None:
            desde = date(2025, 1, 1)  # default: último año aprox.
        print(f"Watermark SJF: {desde}")

    adapter = SJFAdapter()
    print(f"Ingresando SJF desde {desde} (máx {args.paginas} págs, detalle={args.detalle})...")

    procesadas = 0
    ultima_fecha = desde
    for meta in adapter.listar_desde(desde, max_pages=args.paginas):
        if args.limite and procesadas >= args.limite:
            print(f"Límite de {args.limite} alcanzado, parando.")
            break

        # Texto: del detalle (lento pero completo) o del slim (rápido)
        if args.detalle:
            try:
                texto = adapter.obtener_texto(meta)
            except Exception as e:
                print(f"  ✗ {meta.id_externo}: error detalle ({e}), usando slim")
                texto = meta.extra.get("_texto_slim", "")
        else:
            texto = meta.extra.get("_texto_slim", "")

        if not texto:
            continue

        # Construir Documento y persistir
        from ai_justicia.corpus.adapters.base import metadata_a_documento
        doc = metadata_a_documento(meta, texto)
        doc_id = upsert_documento(doc)
        n_chunks = chunk_and_index(doc, doc_id)
        procesadas += 1
        if meta.fecha_publicacion > ultima_fecha:
            ultima_fecha = meta.fecha_publicacion

        if procesadas % 10 == 0 or procesadas <= 3:
            vinc = "vinc" if meta.vinculante else "pers"
            print(f"  [{procesadas}] {meta.id_externo} ({vinc}, {meta.materia}): {meta.titulo[:55]}... → {n_chunks} chunks")

    # Guardar watermark
    if procesadas > 0:
        guardar_watermark(Fuente.SJF, ultima_fecha)

    print()
    print(f"✓ SJF: {procesadas} tesis procesadas, watermark → {ultima_fecha}")
    print(f"  Corpus total: {count_documentos()} documentos, {count_chunks()} chunks")


if __name__ == "__main__":
    main()
