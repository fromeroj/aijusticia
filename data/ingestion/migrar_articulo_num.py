#!/usr/bin/env python3
"""Migración: articulo_num en chunks + titulo_search en documentos.

El código nuevo (fts_index.busqueda_fts, chat_stream.buscar_en_ley) espera:
  - documentos_chunks.articulo_num  (int, primer artículo del chunk)
  - documentos.titulo_search        (tsvector generado de titulo)
Ambos faltaban en la DB de producción (creada por el código viejo).
Idempotente. Correr en el server: .venv/bin/python scripts/migrar_articulo_num.py
"""
import re
import sys
import time

sys.path.insert(0, "/opt/aijusticia/engine")
from ai_justicia.config import settings
import psycopg

RE_ART = re.compile(r"(?:^|[\s¡>\n])Art[íi]culo\s+(\d{1,4})[.°º:\-\s]")


def main():
    with psycopg.connect(settings.psycopg_dsn, autocommit=False) as conn:
        cur = conn.cursor()
        print("1) titulo_search…", flush=True)
        cur.execute("""
            ALTER TABLE documentos
            ADD COLUMN IF NOT EXISTS titulo_search tsvector
            GENERATED ALWAYS AS (to_tsvector('spanish', titulo)) STORED
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_docs_titulo_fts
            ON documentos USING GIN (titulo_search)
        """)
        conn.commit()

        print("2) articulo_num…", flush=True)
        cur.execute("""
            ALTER TABLE documentos_chunks
            ADD COLUMN IF NOT EXISTS articulo_num integer
        """)
        conn.commit()

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_articulo
            ON documentos_chunks (articulo_num)
            WHERE articulo_num IS NOT NULL
        """)
        conn.commit()

        print("3) backfill articulo_num por rangos…", flush=True)
        cur.execute("SELECT coalesce(max(id), 0) FROM documentos_chunks")
        max_id = cur.fetchone()[0]
        total = 0
        lo = 0
        PASO = 200_000
        t0 = time.time()
        while lo <= max_id:
            hi = lo + PASO
            cur.execute("""
                WITH m AS (
                    SELECT id, (regexp_match(
                        left(texto, 150),
                        '(?:^|[\s¡>\n])Art[íi]culo\s+(\d{1,4})[.°º:\-\s]'
                    ))[1] AS n
                    FROM documentos_chunks
                    WHERE id > %s AND id <= %s
                      AND articulo_num IS NULL
                      AND left(texto, 150) ~ '(?:^|[\s¡>\n])Art[íi]culo\s+\d{1,4}[.°º:\-\s]'
                )
                UPDATE documentos_chunks c
                SET articulo_num = m.n::int
                FROM m
                WHERE c.id = m.id
            """, (lo, hi))
            total += cur.rowcount
            conn.commit()
            lo = hi
            if total and (total % 200_000) < PASO * cur.rowcount / max(cur.rowcount, 1):
                pass
            print(f"  hasta id {hi}: +{cur.rowcount} (total {total:,}, {time.time()-t0:.0f}s)", flush=True)
        print(f"LISTO: {total:,} chunks con articulo_num en {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
