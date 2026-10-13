#!/usr/bin/env python3
"""Ingiere los JSONL de SIVEPJ (sentencias CDMX) en el corpus. Idempotente."""
import glob
import json
import sys

sys.path.insert(0, "/opt/aijusticia/engine")
from ai_justicia.corpus.models import Documento, Fuente
from ai_justicia.corpus.store import batch_upsert_documentos

total = 0
lote = []
for path in sorted(glob.glob("/opt/aijusticia/corpus_downloads/sivepj/sivepj_sentencias_*.jsonl")):
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        texto = d.get("texto") or ""
        if len(texto) < 200:
            continue
        titulo = (d.get("titulo") or "Sentencia SIVEPJ")[:300]
        lote.append(Documento(
            fuente=Fuente.SentenciasCDMX,
            titulo=titulo,
            texto=texto,
            url_origen="sivepj",
            extra_keys={"juzgado": d.get("juzgado"), "materia": d.get("materia"),
                        "anio": d.get("anio"), "fecha": d.get("fecha_sentencia")},
        ))
        if len(lote) >= 500:
            total += batch_upsert_documentos(lote)
            print(f"lote: {total}", flush=True)
            lote = []
if lote:
    total += batch_upsert_documentos(lote)
print(f"SIVEPJ ingest total: {total}", flush=True)
