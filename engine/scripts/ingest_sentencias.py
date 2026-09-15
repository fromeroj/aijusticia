#!/usr/bin/env python3
"""Ingestor genérico de sentencias estatales (JSONL -> corpus).

Uso (en el server):
  python3 ingest_sentencias.py <fuente> <glob_jsonl>
Ejemplo:
  python3 ingest_sentencias.py SentenciasCDMX '/opt/aijusticia/corpus_downloads/sivepj/sivepj_sentencias_*.jsonl'
  python3 ingest_sentencias.py SentenciasEdomex '/opt/aijusticia/corpus_downloads/edomex/sentencias_edomex.jsonl'
Idempotente: registro_sjf = hash del texto (upsert deduplica).
"""
import glob
import hashlib
import json
import sys

sys.path.insert(0, "/opt/aijusticia/engine")
from ai_justicia.corpus.models import Documento, Fuente
from ai_justicia.corpus.store import batch_upsert_documentos

fuente = Fuente(sys.argv[1])
pattern = sys.argv[2]

total = 0
lote = []
vistos = set()
for path in sorted(glob.glob(pattern)):
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
        h = hashlib.md5(texto.encode()).hexdigest()[:16]
        if h in vistos:
            continue
        vistos.add(h)
        titulo = (d.get("titulo") or d.get("name") or f"Sentencia {fuente}")[:300]
        lote.append(Documento(
            fuente=fuente,
            titulo=titulo,
            texto=texto,
            registro_sjf=f"{fuente}:{h}",
            url_origen=d.get("url") or d.get("pdf") or None,
            raw={k: d.get(k) for k in ("materia", "anio", "juzgado", "organ_o", "organo",
                                       "fecha_sentencia", "juez", "tipo_juicio", "paginas")
                 if d.get(k)},
        ))
        if len(lote) >= 500:
            total += batch_upsert_documentos(lote)
            print(f"lote acumulado: {total}", flush=True)
            lote = []
if lote:
    total += batch_upsert_documentos(lote)
print(f"INGEST {fuente}: {total} documentos procesados", flush=True)
