"""Export CPT de Tlamatini — consolida todo el corpus en JSONL para Vast.ai.

Corre en el SERVER (lee NFS /opt/aijusticia/corpus_downloads).

Mix 80/15/5:
  80% — derecho mexicano (JSONLs de cosecha + dump RAG + leyes de hoy)
  15% — harness pairs (lawinstruct limpio: instrucción → respuesta)
   5% — replay general español (prevenir olvido catastrófico)

Formato de salida: JSONL {"text": ..., "source": ..., "tipo": ...}
  — un registro = un documento completo (CPT no usa chat-ml por documento;
    el harness mixing se hace a nivel de secuencia con plantillas).

Deduplicación: hash sha256 de los primeros 4KB normalizados de cada texto.
  Si el mismo documento aparece en dump_texto y en un JSONL de cosecha,
  gana el JSONL de cosecha (más fresco).

Uso:
    cd /opt/aijusticia/engine && .venv/bin/python scripts/export_cpt.py [--sample 0.005]
"""
import hashlib
import json
import os
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path

NFS = Path("/opt/aijusticia/corpus_downloads")
OUT_DIR = NFS / "cpt_export"
SAMPLE = 0.005 if "--sample" in sys.argv else 1.0
random.seed(42)

# ── fuentes de derecho MX (80%) ────────────────────────────────────────────

# JSONLs de cosecha: {archivo: tipo}
JSONLS_DERECHO = {
    "edomex/sentencias_edomex.jsonl": "sentencia",
    "queretaro/sentencias_qro.jsonl": "sentencia",
    "unam_tesis/unam_tesis_texto.jsonl": "tesis_doctoral",
    "unam_tesis/tesis_texto.jsonl": "tesis_doctoral",
    "reglamentos_federales.jsonl": "reglamento",
    "reglamentos_edomex.jsonl": "reglamento",
    "reglamentos_fed_v2.jsonl": "reglamento",
    "lexmx_leyes.jsonl": "ley",
    "cdmx_leyes.jsonl": "ley",
    "leyes_guerrero.jsonl": "ley",
    "leyes_puebla.jsonl": "ley",
    "leyes_justia_sonora.jsonl": "ley",
    "leyes_justia_col.jsonl": "ley",
    "leyes_veracruz.jsonl": "ley",
    "ocr_cdmx.jsonl": "doctrina",
    "sivepj_sentencias_1.jsonl": "sentencia",
    "derechoenmexico/derechoenmexico.jsonl": "doctrina",
    # leyes federales de hoy (316 frescas)
    "leyes_federales_hoy.jsonl": "ley",
}

# dump RAG (SJF, DOF, etc. — el texto completo que se vació de Postgres)
DUMP_RAG = "dump_texto_rag_sources.jsonl"

# ── harness pairs (15%) ────────────────────────────────────────────────────

LAWINSTRUCT_LIMPIO = "lawinstruct_instructivos/limpio"

# ── replay general (5%) ────────────────────────────────────────────────────
# texto general en español: usamos las tesis de BJV no-ingresadas a RAG
# y un sample del propio dump (SJF con texto más general).
# Para v1: mismo dump con sample del 5% marcado como replay.

# ── helpers ────────────────────────────────────────────────────────────────

def _hash_dedup(texto: str) -> str:
    """Hash de los primeros 4KB normalizados para deduplicación rápida."""
    normalizado = re.sub(r"\s+", " ", texto[:4096]).strip().lower()
    return hashlib.sha256(normalizado.encode()).hexdigest()


def _texto_valido(texto: str | None) -> bool:
    if not texto or len(texto) < 200:  # mínimo 200 chars = ~50 tokens
        return False
    # rechazar basura binaria o OCR fallido
    alfa = sum(1 for c in texto[:1000] if c.isalpha() or c.isspace())
    return alfa / max(len(texto[:1000]), 1) > 0.6


def _leer_jsonl(ruta: Path, campo_texto: str = "texto") -> list[dict]:
    """Lee un JSONL y devuelve [{text, source, tipo}]."""
    registros = []
    if not ruta.exists():
        print(f"  ⚠ no existe: {ruta}", flush=True)
        return registros
    with open(ruta, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                texto = d.get(campo_texto) or d.get("text") or d.get("contenido") or ""
                if _texto_valido(texto):
                    registros.append({
                        "text": texto,
                        "source": ruta.stem[:30],
                        "tipo": d.get("tipo") or d.get("materia") or "",
                    })
            except (json.JSONDecodeError, KeyError):
                continue
    return registros


def main():
    t0 = time.time()
    OUT_DIR.mkdir(exist_ok=True)
    vistos: set[str] = set()
    total_derecho = 0
    total_harness = 0
    total_replay = 0
    fuentes_contador: Counter = Counter()
    tamano_contador: Counter = Counter()

    # ═══ 1. DERECHO MX (80%) ═══
    print("═══ FASE 1: Derecho mexicano ═══", flush=True)

    # 1a. JSONLs de cosecha (prioridad — más frescos)
    for archivo, tipo_default in JSONLS_DERECHO.items():
        ruta = NFS / archivo
        if not ruta.exists():
            print(f"  ⚠ skip: {archivo}", flush=True)
            continue
        n = 0
        with open(ruta, encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                    texto = d.get("texto") or d.get("text") or ""
                    if not _texto_valido(texto):
                        continue
                    h = _hash_dedup(texto)
                    if h in vistos:
                        continue
                    vistos.add(h)
                    fuentes_contador[ruta.stem[:25]] += 1
                    tamano_contador[ruta.stem[:25]] += len(texto)
                    if random.random() <= SAMPLE:
                        yield_derecho = {"text": texto, "source": archivo[:40], "tipo": tipo_default}
                        with open(OUT_DIR / "derecho_mx.jsonl", "a", encoding="utf-8") as out:
                            out.write(json.dumps(yield_derecho, ensure_ascii=False) + "\n")
                    total_derecho += 1
                    n += 1
                except (json.JSONDecodeError, KeyError):
                    continue
        print(f"  ✓ {archivo}: {n:,} docs ({n * 100 // max(total_derecho, 1)}% acumulado)", flush=True)

    # 1b. dump RAG (SJF, DOF, etc. — lo que NO está en JSONLs de cosecha)
    dump_path = NFS / DUMP_RAG
    if dump_path.exists():
        n = 0
        with open(dump_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                    texto = d.get("texto") or ""
                    if not _texto_valido(texto):
                        continue
                    h = _hash_dedup(texto)
                    if h in vistos:
                        continue
                    vistos.add(h)
                    fuente = (d.get("fuente") or "RAG")[:25]
                    fuentes_contador[fuente] += 1
                    tamano_contador[fuente] += len(texto)
                    if random.random() <= SAMPLE:
                        yield_doc = {"text": texto, "source": fuente, "tipo": d.get("tipo") or ""}
                        with open(OUT_DIR / "derecho_mx.jsonl", "a", encoding="utf-8") as out:
                            out.write(json.dumps(yield_doc, ensure_ascii=False) + "\n")
                    total_derecho += 1
                    n += 1
                except (json.JSONDecodeError, KeyError):
                    continue
        print(f"  ✓ {DUMP_RAG}: {n:,} docs nuevos (dedup aplicado)", flush=True)

    # ═══ 2. HARNESS PAIRS (15%) ═══
    print("\n═══ FASE 2: Harness pairs (lawinstruct) ═══", flush=True)
    limpio_dir = NFS / LAWINSTRUCT_LIMPIO
    if limpio_dir.exists():
        for jf in sorted(limpio_dir.glob("*.jsonl")):
            n = 0
            with open(jf, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        d = json.loads(line)
                        # lawinstruct usa campos variados: buscar el par
                        q = d.get("question") or d.get("instruction") or d.get("input") or ""
                        a = d.get("answer") or d.get("response") or d.get("output") or ""
                        texto = (d.get("text") or d.get("document") or
                                 d.get("context") or d.get("passage") or "")
                        if a and q:
                            # par instrucción → respuesta
                            contenido = f"{q}\n\n{a}"
                        elif texto:
                            contenido = texto
                        else:
                            continue
                        if len(contenido) < 50:
                            continue
                        h = _hash_dedup(contenido)
                        if h in vistos:
                            continue
                        vistos.add(h)
                        fuentes_contador[jf.stem[:25]] += 1
                        tamano_contador[jf.stem[:25]] += len(contenido)
                        if random.random() <= SAMPLE:
                            yield_h = {"text": contenido, "source": jf.stem[:30], "tipo": "harness"}
                            with open(OUT_DIR / "harness_pairs.jsonl", "a", encoding="utf-8") as out:
                                out.write(json.dumps(yield_h, ensure_ascii=False) + "\n")
                        total_harness += 1
                        n += 1
                    except (json.JSONDecodeError, KeyError):
                        continue
            print(f"  ✓ {jf.name}: {n:,} pairs", flush=True)

    # ═══ 3. REPLAY (5%) — texto general español ═══
    # Para v1: sample del corpus de derecho con etiqueta "replay"
    # (en la práctica el replay real se hace con datos genéricos del
    #  pretraining base; esto marca el slot para cuando lleguen)
    print("\n═══ FASE 3: Replay ═══", flush=True)
    print("  (slot reservado — el replay real se configura en Tohil al armar la secuencia)", flush=True)

    # ═══ RESUMEN ═══
    duracion = time.time() - t0
    total = total_derecho + total_harness
    print(f"\n═══ RESUMEN ═══")
    print(f"Derecho MX:  {total_derecho:,} docs")
    print(f"Harness:     {total_harness:,} pairs")
    print(f"Total:       {total:,} registros únicos (dedup {len(vistos):,} hashes)")
    print(f"Duración:    {duracion:.0f}s")

    # distribución del mix real
    if total:
        pct_derecho = total_derecho / total * 100
        pct_harness = total_harness / total * 100
        print(f"Mix: {pct_derecho:.0f}% derecho / {pct_harness:.0f}% harness")

    # top fuentes
    print("\nTop 12 fuentes por docs:")
    for fuente, n in fuentes_contador.most_common(12):
        mb = tamano_contador[fuente] / 1e6
        print(f"  {fuente}: {n:,} docs ({mb:.0f} MB)")

    # manifiesto
    manifiesto = {
        "fecha": time.strftime("%Y-%m-%d %H:%M"),
        "total_docs": total,
        "derecho": total_derecho,
        "harness": total_harness,
        "dedup_hashes": len(vistos),
        "sample_rate": SAMPLE,
        "fuentes": dict(fuentes_contador.most_common(30)),
        "nota": "Mix objetivo 80/15/5 (derecho/harness/replay). "
                "Replay se configura en Tohil a nivel de secuencia. "
                "Formato: JSONL {text, source, tipo}. "
                "Dedup: sha256 de primeros 4KB normalizados.",
    }
    with open(OUT_DIR / "manifiesto.json", "w") as f:
        json.dump(manifiesto, f, indent=2, ensure_ascii=False)
    print(f"\n✓ Manifiesto: {OUT_DIR / 'manifiesto.json'}")
    print(f"✓ Output: {OUT_DIR}/derecho_mx.jsonl + harness_pairs.jsonl")


if __name__ == "__main__":
    main()
