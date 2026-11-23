#!/usr/bin/env python3
"""Rellena documentos_chunks.articulo_num (el número de artículo que abre el chunk).

El localizador de artículos de la recuperación (`fts_index.busqueda_fts`,
`chat_stream._buscar_en_ley`) depende de esta columna: garantiza en el pool los
chunks que EMPIEZAN con "Artículo N". Todo documento ingestado después del
backfill original llega con NULL — era el caso de TODO el corpus de
OrdenJuridico (29K leyes estatales) y de las leyes traídas de 182 (23-nov-2026):
el localizador nunca había servido para las leyes de los estados.

Modos:
  (por defecto)  incremental: documentos de leyes actualizados en las últimas
                 --ventana-dias. Corre cada noche, después de la limpieza.
  --completo     todas las leyes, reanudable por id de documento (avance en
                 /opt/aijusticia/.estado_limpieza/articulos_full.txt).

Sólo importa para documentos de LEYES: sentencias y tesis no se citan por artículo.

IO acotado: primero elige documentos de leyes (una lista corta de ids por
página) y sólo entonces mira sus chunks por clave primaria. Una sola consulta
con JOIN por rango de ids termina leyendo las sentencias y tesis del mismo rango
(23-nov-2026: más de 2 minutos de IO aleatorio por lote, sin avanzar).

Uso (en 162, siempre bajo el mantenimiento nocturno, con tope de memoria y plazo):
  rellenar_articulo_num.py                       # incremental 48h
  rellenar_articulo_num.py --completo            # barrido completo reanudable
  rellenar_articulo_num.py --desde-id A --hasta-id B    # prueba acotada
"""
from __future__ import annotations

import argparse
import os
import resource
import sys
import time

sys.path.insert(0, "/opt/aijusticia/engine")
from ai_justicia.config import settings
import psycopg

FUENTES_LEY = ["OrdenJuridico", "LeyesBiblio", "LexMX", "DOF"]
PAGINA_DOCS = 300           # documentos por página (en memoria sólo los ids)
DIR_ESTADO = "/opt/aijusticia/.estado_limpieza"
ESTADO = "articulos_full.txt"
# Tolerante a mayúsculas (muchas leyes estatales van en MAYÚSCULAS) y a
# ordinales: "Artículo 1.-", "ARTÍCULO 1o.-", "Artículo 3°-", "Artículo 123 Bis."
# (El troceador sigue siendo sensible a mayúsculas: ver el pendiente de
# re-trocear las leyes estatales en docs/components/data-consumer.md.)
RE_ARTICULO = r"(?i)(?:^|[\s¡>\n])art[ií]culo\s+(\d{1,4})(?=[\s.°º:\-oª])"

SQL_IDS = """
    SELECT id FROM documentos
    WHERE id > %s AND fuente = ANY(%s) {ventana}
    ORDER BY id
    LIMIT %s"""
SQL_RELLENAR = """
    UPDATE documentos_chunks c SET articulo_num = m.n
    FROM (SELECT c2.documento_id, c2.ordinal,
                 (regexp_match(left(c2.texto, 150), %s))[1]::int AS n
          FROM documentos_chunks c2
          WHERE c2.documento_id = ANY(%s)
            AND c2.articulo_num IS NULL
            AND left(c2.texto, 150) ~ %s) m
    WHERE c.documento_id = m.documento_id AND c.ordinal = m.ordinal"""


def _leer_estado() -> int | None:
    try:
        return int(open(os.path.join(DIR_ESTADO, ESTADO)).read().strip())
    except (OSError, ValueError):
        return None


def _guardar_estado(ultimo: int) -> None:
    os.makedirs(DIR_ESTADO, exist_ok=True)
    tmp = os.path.join(DIR_ESTADO, ESTADO + ".tmp")
    with open(tmp, "w") as f:
        f.write(str(ultimo))
    os.replace(tmp, os.path.join(DIR_ESTADO, ESTADO))


def _borrar_estado() -> None:
    try:
        os.remove(os.path.join(DIR_ESTADO, ESTADO))
    except OSError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Rellena articulo_num en chunks de leyes")
    ap.add_argument("--completo", action="store_true", help="todas las leyes (reanudable)")
    ap.add_argument("--ventana-dias", type=int, default=2, help="días hacia atrás (modo incremental)")
    ap.add_argument("--desde-id", type=int, default=0, help="id de documento inicial")
    ap.add_argument("--hasta-id", type=int, default=None, help="id de documento final (pruebas)")
    opts = ap.parse_args()

    t0 = time.time()
    if opts.completo:
        ventana_sql, ventana_params = "", []
        previo = _leer_estado()
        ultimo = max(opts.desde_id, previo or 0)
        if previo:
            print(f"reanudando barrido desde el documento {ultimo:,}", flush=True)
    else:
        ventana_sql = "AND updated_at > now() - (%s || ' days')::interval"
        ventana_params = [str(opts.ventana_dias)]
        ultimo = opts.desde_id

    docs = puestos = 0
    with psycopg.connect(settings.psycopg_dsn) as conn:
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '150s'")
        while True:
            cur.execute(SQL_IDS.format(ventana=ventana_sql),
                        [ultimo, FUENTES_LEY, *ventana_params, PAGINA_DOCS])
            ids = [r[0] for r in cur.fetchall()]
            if opts.hasta_id is not None:
                ids = [i for i in ids if i <= opts.hasta_id]
            if not ids:
                break
            cur.execute(SQL_RELLENAR, (RE_ARTICULO, ids, RE_ARTICULO))
            puestos += cur.rowcount
            conn.commit()
            ultimo = ids[-1]
            docs += len(ids)
            if opts.completo:
                _guardar_estado(ultimo)
            if docs % 6000 < len(ids):
                print(f"  documentos de leyes={docs:,} chunks numerados={puestos:,} "
                      f"({time.time()-t0:.0f}s)", flush=True)
            if len(ids) < PAGINA_DOCS or (opts.hasta_id is not None and ids[-1] >= opts.hasta_id):
                break
        if opts.completo and opts.hasta_id is None:
            _borrar_estado()

    pico = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    print(f"ARTICULOS LISTO: documentos={docs:,} chunks numerados={puestos:,} "
          f"en {time.time()-t0:.0f}s · memoria pico {pico} MB", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
