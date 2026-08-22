"""Ingesta el corpus en la base de datos.

Para desarrollo: usa el fixture (documentos reales de ejemplo).
Para producción: llamará a corpus/sources/*.py (ingesta diaria del DOF, LeyesBiblio, SJF).

Uso:
    python scripts/ingest_corpus.py              # fixture
    python scripts/ingest_corpus.py --fixture    # explícito
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_justicia.corpus.store import chunk_and_index, count_chunks, count_documentos, upsert_documento
from tests.fixtures.corpus_fixture import FIXTURE_DOCUMENTOS


def ingest_fixture() -> None:
    """Ingere el fixture de corpus: upsert + chunk + index vectorial."""
    print(f"Ingresando {len(FIXTURE_DOCUMENTOS)} documentos del fixture...")
    total_chunks = 0
    for i, doc in enumerate(FIXTURE_DOCUMENTOS, 1):
        doc_id = upsert_documento(doc)
        n_chunks = chunk_and_index(doc, doc_id)
        total_chunks += n_chunks
        print(f"  [{i}/{len(FIXTURE_DOCUMENTOS)}] {doc.fuente.value}: {doc.titulo[:60]}... → doc_id={doc_id}, {n_chunks} chunks")

    print()
    print(f"✓ Ingesta completa: {count_documentos()} documentos, {count_chunks()} chunks indexados")


if __name__ == "__main__":
    ingest_fixture()
