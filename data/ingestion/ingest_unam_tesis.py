#!/usr/bin/env python3
"""Ingiere las tesis de la UNAM (Repositorio Institucional) al corpus.

Fuente: UNAM-Tesis, jerarquía DOCTRINA (70) — consulta y CPT, nunca citación
de ley (el Bibliotecario solo cita LeyesBiblio/LexMX/DOF).
Entrada: /mnt/corpus_storage/unam_tesis/unam_tesis_texto.jsonl
         {"titulo": …, "texto": …} — dedup por md5(texto).
Idempotente. Niced por quien lo lance.
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, "/opt/aijusticia/engine")
from ai_justicia.corpus.models import Documento, Fuente, Jerarquia
from ai_justicia.corpus.store import batch_upsert_documentos, count_documentos

ENTRADA = Path("/mnt/corpus_storage/unam_tesis/unam_tesis_texto.jsonl")
MIN_CHARS = 500

total = saltos_cortos = dup = nuevos = 0
vistos = set()
lote = []
for line in open(ENTRADA, encoding="utf-8", errors="replace"):
    line = line.strip()
    if not line:
        continue
    total += 1
    try:
        import json
        d = json.loads(line)
    except Exception:
        continue
    texto = (d.get("texto") or "").strip()
    if len(texto) < MIN_CHARS:
        saltos_cortos += 1
        continue
    h = hashlib.md5(texto.encode()).hexdigest()[:16]
    if h in vistos:
        dup += 1
        continue
    vistos.add(h)
    titulo = (d.get("titulo") or "Tesis UNAM").strip()[:300]
    lote.append(Documento(
        fuente=Fuente.UNAM_TESIS,
        titulo=titulo,
        texto=texto,
        registro_sjf=f"UNAM:{h}",
        jerarquia=Jerarquia.DOCTRINA,
        vinculante=False,
        tipo="tesis",
    ))
    if len(lote) >= 50:
        batch_upsert_documentos(lote)
        nuevos += len(lote)
        print(f"+{nuevos:,} de {total:,} leídas (dup {dup:,}, cortos {saltos_cortos:,}) "
              f"| DB: {count_documentos():,}", flush=True)
        lote = []
if lote:
    batch_upsert_documentos(lote)
    nuevos += len(lote)
print(f"FIN: {nuevos:,} tesis ingestadas de {total:,} líneas "
      f"(dup {dup:,}, cortos {saltos_cortos:,})", flush=True)
