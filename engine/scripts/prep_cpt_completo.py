#!/usr/bin/env python3
"""Preparación completa del corpus CPT para Tlamatini.

Paso 1: Export universal (TODO el corpus DB → JSONL plaintext)
Paso 2: Wikipedia es + replay (2-5% del mix)
Paso 3: Harness pairs a escala (considerandos → artículos)

Salida: /opt/aijusticia/corpus_downloads/cpt_final/
  ├── derecho_mx.jsonl      (corpus principal, ~3-5B tokens)
  ├── replay_general.jsonl  (Wikipedia es + código + instruct, ~2-5%)
  ├── harness_mx.jsonl      (pares anclados, ~50K)
  └── MANIFIESTO.json       (números finales para el config de entrenamiento)
"""
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, "/opt/aijusticia/engine")
from ai_justicia.config import settings

OUT = Path("/opt/aijusticia/corpus_downloads/cpt_final")
OUT.mkdir(parents=True, exist_ok=True)
MIN_TEXTO = 200
DEDUP = set()

import psycopg
conn = psycopg.connect(settings.psycopg_dsn, application_name="cpt_prep")
cur = conn.cursor(name="cpt_full")
cur.itersize = 5000


def dedup(texto):
    h = hashlib.md5(texto.encode()).hexdigest()[:16]
    if h in DEDUP:
        return False
    DEDUP.add(h)
    return True


# ═══════════════════════════════════════════════════════════════════════
# PASO 1: Export universal — TODO el corpus DB → derecho_mx.jsonl
# ═══════════════════════════════════════════════════════════════════════
print("=" * 60, flush=True)
print("PASO 1: Export universal del corpus DB", flush=True)
print("=" * 60, flush=True)

out_derecho = open(OUT / "derecho_mx.jsonl", "w")
total_derecho = 0
t0 = time.time()

cur.execute("""
    SELECT id, fuente, titulo, texto, entidad
    FROM documentos
    WHERE length(texto) > 200
    ORDER BY fuente, id
""")

while True:
    rows = cur.fetchmany(2000)
    if not rows:
        break
    for doc_id, fuente, titulo, texto, entidad in rows:
        if not texto or len(texto.strip()) < MIN_TEXTO:
            continue
        if not dedup(texto):
            continue
        # documento como plaintext — el tokenizador no necesita formato especial
        # para CPT: el texto crudo ES el dato de entrenamiento
        out_derecho.write(json.dumps({"text": texto.strip()}, ensure_ascii=False) + "\n")
        total_derecho += 1
    elapsed = time.time() - t0
    if total_derecho % 10000 == 0 and total_derecho > 0:
        print(f"  {total_derecho:,} docs exportados ({elapsed:.0f}s)", flush=True)

out_derecho.close()
conn.commit()
print(f"PASO 1 completo: {total_derecho:,} documentos → derecho_mx.jsonl", flush=True)

# ═══════════════════════════════════════════════════════════════════════
# PASO 2: General replay — Wikipedia es + código + instruct
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60, flush=True)
print("PASO 2: General replay", flush=True)
print("=" * 60, flush=True)

out_replay = open(OUT / "replay_general.jsonl", "w")
total_replay = 0

# Wikipedia es — descargar subset desde HuggingFace (primeras shards)
try:
    from datasets import load_dataset
    print("  Descargando Wikipedia es (subset)...", flush=True)
    ds = load_dataset("wikimedia/wikipedia", "20231101.es", split="train", streaming=True)
    wiki_count = 0
    wiki_target = 50000  # artículos de Wikipedia
    for art in ds:
        if wiki_count >= wiki_target:
            break
        texto = art.get("text", "").strip()
        if len(texto) < 200:
            continue
        if not dedup(texto):
            continue
        out_replay.write(json.dumps({"text": f"{art.get('title', '')}\n\n{texto}"}, ensure_ascii=False) + "\n")
        wiki_count += 1
        if wiki_count % 5000 == 0:
            print(f"  Wikipedia: {wiki_count}", flush=True)
    total_replay += wiki_count
    print(f"  Wikipedia es: {wiki_count} artículos", flush=True)
except Exception as e:
    print(f"  Wikipedia ERR: {str(e)[:100]}", flush=True)

# código (GitHub public en español o general)
try:
    from datasets import load_dataset
    print("  Descargando code replay...", flush=True)
    ds = load_dataset("codeparrot/github-code", "python", split="train", streaming=True)
    code_count = 0
    code_target = 5000
    for art in ds:
        if code_count >= code_target:
            break
        texto = art.get("code", "").strip()
        if len(texto) < 200 or len(texto) > 10000:
            continue
        if not dedup(texto):
            continue
        out_replay.write(json.dumps({"text": texto}, ensure_ascii=False) + "\n")
        code_count += 1
    total_replay += code_count
    print(f"  Código: {code_count} archivos", flush=True)
except Exception as e:
    print(f"  Código ERR: {str(e)[:80]}", flush=True)

# instruct general (español)
try:
    from datasets import load_dataset
    ds = load_dataset("Iker/OpenHermes-2.5-Spanish", split="train", streaming=True)
    inst_count = 0
    inst_target = 10000
    for art in ds:
        if inst_count >= inst_target:
            break
        conv = art.get("messages", art.get("conversations", []))
        texto = ""
        for turn in conv:
            role = turn.get("role", turn.get("from", ""))
            content = turn.get("content", turn.get("value", ""))
            if content:
                texto += f"{role}: {content}\n\n"
        if len(texto.strip()) < 200:
            continue
        if not dedup(texto):
            continue
        out_replay.write(json.dumps({"text": texto.strip()}, ensure_ascii=False) + "\n")
        inst_count += 1
    total_replay += inst_count
    print(f"  Instruct es: {inst_count}", flush=True)
except Exception as e:
    print(f"  Instruct ERR: {str(e)[:80]}", flush=True)

out_replay.close()
print(f"PASO 2 completo: {total_replay:,} documentos de replay", flush=True)

# ═══════════════════════════════════════════════════════════════════════
# PASO 3: Harness pairs a escala — minar sentencias del corpus
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60, flush=True)
print("PASO 3: Harness pairs", flush=True)
print("=" * 60, flush=True)

out_harness = open(OUT / "harness_mx.jsonl", "w")
total_harness = 0

CIT_RE = re.compile(
    r"(?:conforme al|de conformidad con el|al|el|los)\s+"
    r"art[íi]culo\s+(\d+[°º]?(?:\s+(?:bis|ter|quater))?(?:\s+[A-Z])?)[\.,]?\s+"
    r"(?:fracci[óo]n\s+[IVXLC]+[\s,\.]*)?"
    r"(?:de la|del|de el|de las)\s+"
    r"((?:Ley|C[óo]digo|Reglamento|Constituci[óo]n|Ley General|Ley Federal)[^,;\.\n]{0,120})",
    re.I,
)
SENT_SPLIT = re.compile(r"(?<=[\.\!\?])\s+")
PREGUNTAS = [
    "¿Qué establece la ley sobre esto?",
    "¿Qué dice la ley aplicable?",
    "¿Con qué fundamento legal?",
    "¿Qué artículo aplica aquí?",
    "¿Cuál es el fundamento de esa resolución?",
    "¿Es legal lo que hicieron según la ley?",
    "¿Qué artículo de la ley me ampara?",
    "¿Cuál es el fundamento jurídico?",
]

# minar las sentencias más grandes del corpus (tienen más considerandos)
cur.execute("""
    SELECT id, texto FROM documentos
    WHERE fuente IN ('SentenciasEdomex', 'SentenciasCDMX', 'SentenciasBC',
                     'SentenciasQro', 'SJF', 'GacetaEstatal')
      AND length(texto) > 1000
    ORDER BY length(texto) DESC
    LIMIT 50000
""")

qi = 0
while True:
    rows = cur.fetchmany(1000)
    if not rows:
        break
    for doc_id, texto in rows:
        qi += 1
        oraciones = SENT_SPLIT.split(texto)
        for oracion in oraciones:
            if not (100 < len(oracion) < 800):
                continue
            m = CIT_RE.search(oracion)
            if not m:
                continue
            art = m.group(1)
            ley = re.sub(r"\s+", " ", m.group(2)).strip().rstrip(",;")
            if len(ley) < 10:
                continue
            # construir par harness en el formato de inferencia
            h = hashlib.md5(oracion.encode()).hexdigest()[:12]
            if h in DEDUP:
                continue
            DEDUP.add(h)
            q = PREGUNTAS[qi % len(PREGUNTAS)]
            text = (f"Pasaje de ley: {ley}, artículo {art}.\n\n"
                    f"Pregunta: {q}\n\n"
                    f"Respuesta: {oracion.strip()} Fundamento: artículo {art}, {ley}.")
            out_harness.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")
            total_harness += 1
            if total_harness % 5000 == 0:
                print(f"  harness: {total_harness} pares (docs minados: {qi})", flush=True)
            break  # un par por oración
    if qi % 5000 == 0:
        print(f"  docs minados: {qi} | pares: {total_harness}", flush=True)

out_harness.close()
print(f"PASO 3 completo: {total_harness:,} pares harness", flush=True)

# ═══════════════════════════════════════════════════════════════════════
# MANIFIESTO
# ═══════════════════════════════════════════════════════════════════════
manifiesto = {
    "fecha": time.strftime("%Y-%m-%d %H:%M"),
    "derecho_mx": total_derecho,
    "replay_general": total_replay,
    "harness_mx": total_harness,
    "total_documentos": total_derecho + total_replay + total_harness,
    "dedup_hashes": len(DEDUP),
    "tokens_estimados": "ver tokenizador (estimado 3-6B)",
}
manifiesto_path = OUT / "MANIFIESTO.json"
manifiesto_path.write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False))
print(f"\nMANIFIESTO: {json.dumps(manifiesto, indent=2)}", flush=True)
print("\nPREPARACIÓN COMPLETADA", flush=True)
