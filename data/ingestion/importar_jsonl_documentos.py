#!/usr/bin/env python3
"""Importa documentos a la DB canónica desde un JSONL de filas de `documentos`.

Cada línea es un objeto JSON con las columnas de `documentos` tal como las
emite `row_to_json` (ver "Export de origen"). Reglas:
  - NUNCA pisa lo existente: INSERT ... ON CONFLICT (fuente, dedup_key) DO
    NOTHING, conservando la dedup_key de origen. Sólo lo nuevo genera chunks
    (misma lógica que batch_upsert_documentos).
  - Excepción DOF: su dedup_key es titulo_fecha, así que la misma nota con un
    título que difiere en espacios tendría otra clave → además se descarta si
    ya existe una nota DOF con la misma fecha y el mismo título normalizado.
  - Memoria acotada: una línea a la vez, commit cada 20 documentos.

Export de origen (en la DB de donde vienen los documentos, como superuser):
  COPY (SELECT row_to_json(x) FROM (SELECT fuente, entidad, materia, tipo, titulo,
        texto, registro_sjf, fecha_reforma, fecha_publicacion, fecha_vigencia,
        derogado, jerarquia, vinculante, url_origen, raw, dedup_key
        FROM documentos [WHERE ...] ORDER BY fuente, id) x) TO STDOUT;

Uso (en 162, SIEMPRE con tope de memoria y de tiempo — ver run_cap en
infra/cron/mantenimiento_nocturno.sh):
  importar_jsonl_documentos.py <archivo.jsonl[.gz]>
"""
from __future__ import annotations

import gzip
import json
import re
import resource
import sys
import time
from datetime import date

sys.path.insert(0, "/opt/aijusticia/engine")
from ai_justicia.config import settings
from ai_justicia.corpus.models import Documento, Fuente, Jerarquia
from ai_justicia.corpus.store import chunk_documento
import psycopg
from psycopg.types.json import Json

MIN_CHARS = 200
COMMIT_CADA = 20

INSERT_DOC = """
    INSERT INTO documentos (
        fuente, entidad, materia, tipo, titulo, texto,
        registro_sjf, fecha_reforma, fecha_publicacion, fecha_vigencia,
        derogado, jerarquia, vinculante, url_origen, raw, dedup_key)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (fuente, dedup_key) DO NOTHING
    RETURNING id"""
INSERT_CHUNK = """
    INSERT INTO documentos_chunks (documento_id, ordinal, texto, embedding)
    VALUES (%s, %s, %s, NULL)"""
TITULOS_DOF_FECHA = """
    SELECT titulo FROM documentos
    WHERE fuente = 'DOF' AND fecha_publicacion = %s"""


def _fecha(v) -> date | None:
    return date.fromisoformat(v) if v else None


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip().lower()


def main(ruta: str) -> int:
    abrir = gzip.open if ruta.endswith(".gz") else open
    res = {"leidos": 0, "insertados": 0, "ya_existian": 0, "duplicado_dof": 0,
           "vacios": 0, "malformados": 0, "chunks": 0}
    por_fuente: dict[str, int] = {}
    t0 = time.time()
    titulos_dof: dict[date, set[str]] = {}
    sin_comitar = 0
    with psycopg.connect(settings.psycopg_dsn) as conn, abrir(ruta, "rt", encoding="utf-8") as f:
        cur = conn.cursor()
        for linea in f:
            res["leidos"] += 1
            try:
                r = json.loads(linea)
            except json.JSONDecodeError:
                res["malformados"] += 1
                continue
            texto = r.get("texto") or ""
            if len(texto.strip()) < MIN_CHARS:
                res["vacios"] += 1
                continue
            fuente = Fuente(r["fuente"])            # valida contra el enum
            titulo = (r.get("titulo") or "Documento")[:300]
            fecha_pub = _fecha(r.get("fecha_publicacion"))

            if fuente == Fuente.DOF and fecha_pub:
                if fecha_pub not in titulos_dof:
                    cur.execute(TITULOS_DOF_FECHA, (fecha_pub,))
                    titulos_dof[fecha_pub] = {_norm(t) for (t,) in cur.fetchall()}
                if _norm(titulo) in titulos_dof[fecha_pub]:
                    res["duplicado_dof"] += 1
                    continue

            jerarquia = r.get("jerarquia")
            vinculante = r.get("vinculante")
            cur.execute(INSERT_DOC, (
                fuente.value, r.get("entidad"), r.get("materia"), r.get("tipo"),
                titulo, texto, r.get("registro_sjf"), _fecha(r.get("fecha_reforma")),
                fecha_pub, _fecha(r.get("fecha_vigencia")), bool(r.get("derogado")),
                jerarquia if jerarquia is not None else Jerarquia.LEY_FEDERAL,
                True if vinculante is None else bool(vinculante),
                r.get("url_origen"),
                Json(r["raw"]) if r.get("raw") is not None else None,
                r["dedup_key"],
            ))
            fila = cur.fetchone()
            if not fila:
                res["ya_existian"] += 1
                continue
            doc_id = fila[0]
            doc = Documento(fuente=fuente, titulo=titulo, texto=texto)
            for i, trozo in enumerate(chunk_documento(doc)):
                cur.execute(INSERT_CHUNK, (doc_id, i, trozo))
                res["chunks"] += 1
            res["insertados"] += 1
            por_fuente[fuente.value] = por_fuente.get(fuente.value, 0) + 1
            sin_comitar += 1
            if sin_comitar >= COMMIT_CADA:
                conn.commit()
                sin_comitar = 0
            if res["insertados"] % 500 == 0:
                print(f"+{res['insertados']:,} insertados ({res['chunks']:,} chunks) "
                      f"en {time.time()-t0:.0f}s", flush=True)
        conn.commit()

    pico = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    print(f"IMPORTACION LISTA en {time.time()-t0:.0f}s · memoria pico {pico} MB", flush=True)
    print("  leídos={leidos:,} insertados={insertados:,} ya_existian={ya_existian:,} "
          "duplicado_dof={duplicado_dof:,} vacios={vacios:,} malformados={malformados:,} "
          "chunks={chunks:,}".format(**res), flush=True)
    print("  insertados por fuente: " + ", ".join(f"{k}={v:,}" for k, v in sorted(por_fuente.items())), flush=True)
    return 0 if res["insertados"] or res["ya_existian"] else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__.split("\n\n")[-1])
    sys.exit(main(sys.argv[1]))
