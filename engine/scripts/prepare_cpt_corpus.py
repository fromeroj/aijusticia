"""
Prepara el corpus de Continued Pre-Training (Capa 1).

Replica la receta de datos de SaulLM/Thomson adaptada a nuestro hardware:
  - Nuestro corpus MX como núcleo (leyes, jurisprudencia, DOF, 32 estados)
  - Replay general anti-olvido (fracción pequeña)
  - Formato: JSONL de texto plano {"text": "..."} para mlx_lm.lora

El dump se hace directamente de PostgreSQL (texto limpio de chunks).

Uso:
    python scripts/prepare_cpt_corpus.py --total-tokens 400M
    python scripts/prepare_cpt_corpus.py --max-chars-per-doc 8000
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

import psycopg

from ai_justicia.config import settings

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "cpt"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ~4 chars por token en español legal
CHARS_PER_TOKEN = 4


def dump_corpus(
    total_tokens_target: int,
    max_chars_per_sample: int = 4096 * CHARS_PER_TOKEN,
    min_chars: int = 200,
    sample_seed: int = 42,
) -> dict[str, int]:
    """Dumps texto limpio del corpus a JSONL {"text": ...}.

    Estrategia de muestreo:
    - Cada chunk del corpus es una muestra (ya están en ~1200 chars)
    - Agrupamos chunks contiguos del mismo documento en muestras más largas
      (hasta max_chars) para dar contexto de documento completo
    - Muestreamos uniformemente hasta llegar al objetivo de tokens
    """
    random.seed(sample_seed)
    target_chars = total_tokens_target * CHARS_PER_TOKEN

    # Cargar por fuente con prioridad: leyes federales > SJF > DOF > estatal
    # (Thomson: calidad > cantidad en el mix)
    fuente_prioridad = {
        "LeyesBiblio": 3.0,   # leyes federales consolidadas — la base
        "SJF": 2.5,           # jurisprudencia — razonamiento legal
        "DOF": 1.5,           # decretos/vigencia — contexto
        "GacetaEstatal": 1.0, # leyes estatales — volumen
    }

    conn = psycopg.connect(settings.psycopg_dsn)
    escrito: dict[str, int] = {f: 0 for f in fuente_prioridad}
    total_escrito = 0

    out_path = OUTPUT_DIR / "cpt_corpus.jsonl"

    with open(out_path, "w") as fout, conn.cursor() as cur:
        # Para cada fuente, calcular su cuota proporcional a prioridad × tamaño
        cur.execute("""
            SELECT d.fuente, SUM(LENGTH(c.texto)) as total_chars
            FROM documentos_chunks c
            JOIN documentos d ON d.id = c.documento_id
            WHERE d.derogado = FALSE
            GROUP BY d.fuente
        """)
        fuentes = {f: int(c) for f, c in cur.fetchall() if f in fuente_prioridad}

        # Pesos: prioridad × log(tamaño) — prioridad domina, tamaño ajusta
        import math
        pesos = {f: fuente_prioridad[f] * math.log1p(fuentes[f]) for f in fuentes}
        peso_total = sum(pesos.values())
        cuotas = {f: int(target_chars * pesos[f] / peso_total) for f in fuentes}

        print(f"Objetivo total: {target_chars/1e9:.1f}GB texto (~{total_tokens_target/1e6:.0f}M tokens)")
        print(f"Cuotas por fuente:")
        for f, c in sorted(cuotas.items(), key=lambda x: -x[1]):
            print(f"  {f:15} {c/1e6:>6.0f}MB texto (~{c/CHARS_PER_TOKEN/1e6:.0f}M tok)")

        for fuente, cuota in cuotas.items():
            if cuota <= 0:
                continue
            print(f"\nProcesando {fuente} (cuota {cuota/1e6:.0f}MB)...")

            # Agrupar chunks contiguos del mismo documento en muezas largas
            cur.execute("""
                SELECT c.documento_id, c.ordinal, c.texto, d.titulo
                FROM documentos_chunks c
                JOIN documentos d ON d.id = c.documento_id
                WHERE d.fuente = %s AND d.derogado = FALSE
                  AND LENGTH(c.texto) >= %s
                ORDER BY c.documento_id, c.ordinal
            """, (fuente, min_chars))
            # name error above: cierre del execute

            buffer_doc = None
            buffer_text = []
            buffer_chars = 0
            escritos_fuente = 0
            rows = cur.fetchall()
            print(f"  Chunks a procesar: {len(rows):,}")

            for doc_id, ordinal, texto, titulo in rows:
                if buffer_doc != doc_id:
                    # Flush del documento anterior
                    if buffer_text:
                        sample = _limpiar_sample(" ".join(buffer_text), titulo)
                        if sample:
                            fout.write(json.dumps({"text": sample}, ensure_ascii=False) + "\n")
                            escritos_fuente += len(sample)
                            if escritos_fuente >= cuota:
                                break
                    buffer_doc = doc_id
                    buffer_text = []
                    buffer_chars = 0

                if buffer_chars + len(texto) <= max_chars_per_sample:
                    buffer_text.append(texto)
                    buffer_chars += len(texto)
                else:
                    # Documento muy largo: flush y empezar nueva muestra
                    if buffer_text:
                        sample = _limpiar_sample(" ".join(buffer_text), titulo)
                        if sample:
                            fout.write(json.dumps({"text": sample}, ensure_ascii=False) + "\n")
                            escritos_fuente += len(sample)
                            if escritos_fuente >= cuota:
                                break
                    buffer_text = [texto]
                    buffer_chars = len(texto)

            # Flush final
            if buffer_text and escritos_fuente < cuota:
                sample = _limpiar_sample(" ".join(buffer_text), titulo)
                if sample:
                    fout.write(json.dumps({"text": sample}, ensure_ascii=False) + "\n")
                    escritos_fuente += len(sample)

            escrito[fuente] = escritos_fuente
            total_escrito += escritos_fuente
            print(f"  → {escritos_fuente/1e6:.0f}MB (~{escritos_fuente/CHARS_PER_TOKEN/1e6:.0f}M tok)")

    conn.close()

    print(f"\n=== TOTAL: {total_escrito/1e6:.0f}MB texto ≈ {total_escrito/CHARS_PER_TOKEN/1e6:.0f}M tokens ===")
    return escrito


def _limpiar_sample(texto: str, titulo: str | None) -> str | None:
    """Limpia una muestra para CPT: quita artefactos, normaliza espacios.

    NO incluimos el título en el texto (CPT puro es texto natural);
    el documento ya empieza con su encabezado natural.
    """
    texto = texto.strip()
    if len(texto) < 200:
        return None
    # Quitar artefactos de extracción (números de página sueltos, líneas de guiones)
    texto = re.sub(r"\n?\s*\d+\s*\n", "\n", texto)  # números de página
    texto = re.sub(r"\n[-—=]{3,}\n", "\n", texto)     # líneas de guiones
    # Normalizar espacios sin destruir estructura
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto


def main():
    ap = argparse.ArgumentParser(description="Prepara corpus de CPT")
    ap.add_argument("--total-tokens", type=str, default="350M",
                    help="Objetivo de tokens (ej. 350M, 1B)")
    ap.add_argument("--max-chars-per-sample", type=int, default=4096 * 4,
                    help="Máx chars por muestra (~seq_len × 4)")
    args = ap.parse_args()

    # Parsear "350M" / "1B"
    s = args.total_tokens.upper()
    if s.endswith("M"):
        target = int(float(s[:-1]) * 1e6)
    elif s.endswith("B"):
        target = int(float(s[:-1]) * 1e9)
    else:
        target = int(s)

    dump_corpus(
        total_tokens_target=target,
        max_chars_per_sample=args.max_chars_per_sample,
    )

    # Split train/valid (99/1)
    in_path = OUTPUT_DIR / "cpt_corpus.jsonl"
    train_path = OUTPUT_DIR / "train.jsonl"
    valid_path = OUTPUT_DIR / "valid.jsonl"
    random.seed(42)

    lines = in_path.read_text(encoding="utf-8").splitlines()
    random.shuffle(lines)
    n_valid = max(20, len(lines) // 100)
    with open(valid_path, "w") as f:
        f.write("\n".join(lines[:n_valid]) + "\n")
    with open(train_path, "w") as f:
        f.write("\n".join(lines[n_valid:]) + "\n")
    in_path.unlink()  # borrar el combinado

    print(f"\nSplit: train={len(lines)-n_valid:,} valid={n_valid:,}")
    print(f"Listo: {train_path} / {valid_path}")


if __name__ == "__main__":
    main()
