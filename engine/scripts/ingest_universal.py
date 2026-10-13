#!/usr/bin/env python3
"""Ingestor universal: procesa TODOS los JSONL pendientes en corpus_downloads.

Cada archivo se mapea a una Fuente del corpus y se ingiere con dedup por hash.
Idempotente: puede correrse múltiples veces sin duplicar.

Uso (server):  nohup python3 ingest_universal.py > log 2>&1 &
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, "/opt/aijusticia/engine")
from ai_justicia.corpus.models import Documento, Fuente
from ai_justicia.corpus.store import batch_upsert_documentos

BASE = "/opt/aijusticia/corpus_downloads"
LOTE_SIZE = 300

# (archivo, fuente, entidad_default, tipo_doc)
SOURCES = [
    ("leyes_guerrero.jsonl",        "OrdenJuridico",        "Guerrero",             "Ley estatal"),
    ("leyes_justia_col.jsonl",      "OrdenJuridico",        "Colima",               "Ley estatal"),
    ("leyes_justia_sonora.jsonl",   "OrdenJuridico",        "Sonora",               "Ley estatal"),
    ("leyes_puebla.jsonl",          "OrdenJuridico",        "Puebla",               "Ley estatal"),
    ("leyes_veracruz.jsonl",        "OrdenJuridico",        "Veracruz",             "Ley estatal"),
    ("lexmx_leyes.jsonl",           "LeyesBiblio",          None,                   "Ley federal"),
    ("cdmx_leyes.jsonl",            "OrdenJuridico",        "Ciudad de México",     "Ley CDMX"),
    ("ocr_cdmx.jsonl",              "GacetaCDMX",           "Ciudad de México",     "Documento OCR"),
    ("ocr_scjn.jsonl",              "SCJN-Libros",          None,                   "Documento OCR SCJN"),
    ("reglamentos_federales.jsonl", "OrdenJuridico",        None,                   "Reglamento federal"),
    ("reglamentos_edomex.jsonl",    "OrdenJuridico",        "Estado de México",     "Reglamento Edomex"),
    ("reglamentos_fed_v2.jsonl",    "OrdenJuridico",        None,                   "Reglamento federal v2"),
    ("preguntas_all.jsonl",         "PreguntasEntrenamiento", None,                 "Pregunta"),
    ("preguntas_traducidas.jsonl",  "PreguntasEntrenamiento", None,                 "Pregunta traducida"),
]

MIN_TEXTO = 300


def dedup_key(texto):
    return hashlib.md5(texto.encode()).hexdigest()[:16]


def main():
    global_total = 0
    vistos = set()

    for fname, fuente_str, entidad, tipo_doc in SOURCES:
        path = os.path.join(BASE, fname)
        if not os.path.isfile(path):
            print(f"SKIP {fname}: no existe", flush=True)
            continue
        size = os.path.getsize(path)
        print(f"\n=== {fname} ({size/1e6:.1f} MB) fuente={fuente_str} ===", flush=True)

        fuente = Fuente(fuente_str)
        lote = []
        total_arch = 0
        err = 0

        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue

                texto = (d.get("texto") or d.get("text") or "").replace(chr(0), "")
                if len(texto.strip()) < MIN_TEXTO:
                    continue

                titulo = (d.get("titulo") or d.get("title") or tipo_doc).replace(chr(0), "")[:300]
                url = d.get("url") or d.get("url_origen") or ""

                # dedup global por hash del texto
                h = dedup_key(texto)
                if h in vistos:
                    continue
                vistos.add(h)

                raw = {k: str(v)[:200] for k, v in d.items()
                       if k not in ("texto", "text", "titulo", "title", "url") and v}

                lote.append(Documento(
                    fuente=fuente,
                    titulo=titulo,
                    texto=texto,
                    registro_sjf=f"ING:{h}",
                    url_origen=url or None,
                    entidad=d.get("entidad") or entidad,
                    raw=raw,
                ))
                total_arch += 1

                if len(lote) >= LOTE_SIZE:
                    n = batch_upsert_documentos(lote)
                    global_total += n
                    total_arch_ingested = global_total
                    print(f"  lote +{n} (acumulado archivo: {total_arch})", flush=True)
                    lote = []

        if lote:
            n = batch_upsert_documentos(lote)
            global_total += n
            print(f"  final {fname}: +{n}", flush=True)

        print(f"  {fname}: {total_arch} docs procesados", flush=True)

    print(f"\n=== INGEST UNIVERSAL COMPLETADO: {global_total} documentos ===", flush=True)


if __name__ == "__main__":
    main()
