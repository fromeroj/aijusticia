"""Batería de comparación: mismas 30 preguntas por el pipeline completo (PG+RAG).

Uso en el server:
    # MiniMax (config por defecto del .env):
    python scripts/batch_compare.py minimax
    # Thomson via túnel inverso (localhost:1234 = LM Studio de la Mac):
    LMSTUDIO_BASE_URL=http://localhost:1234/v1 LMSTUDIO_LLM_MODEL=thomson-1.0-small-mlx \
        python scripts/batch_compare.py thomson
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ai_justicia.pipeline.orchestrator import ejecutar_consulta  # noqa: E402

TAG = sys.argv[1] if len(sys.argv) > 1 else "run"
QS = Path("/opt/aijusticia/engine/data/questions_curated.json")
OUT = Path(f"/opt/aijusticia/engine/data/compare_{TAG}.jsonl")

qs = json.load(open(QS))
hechas = set()
if OUT.exists():
    hechas = {json.loads(l)["question"] for l in open(OUT)}
    print(f"resume: {len(hechas)} ya hechas", flush=True)

with open(OUT, "a") as f:
    for i, q in enumerate(qs, 1):
        pregunta = q["question"]
        if pregunta in hechas:
            continue
        t0 = time.time()
        try:
            r = ejecutar_consulta(pregunta, nivel="Nivel0")
            rec = {
                "n": i,
                "question": pregunta,
                "abstenido": r.abstenido,
                "respuesta": r.respuesta,
                "materia": (r.analisis or {}).get("materia"),
                "n_sustentadas": (r.verificacion or {}).get("n_sustentadas"),
                "n_oraciones": (r.verificacion or {}).get("n_oraciones"),
                "pasajes": [{"fuente": p["fuente"], "titulo": p["titulo"][:80]} for p in (r.pasajes or [])[:5]],
                "duracion_s": round(time.time() - t0, 1),
                "traza_id": r.traza_id,
            }
        except Exception as e:
            rec = {"n": i, "question": pregunta, "error": str(e)[:200],
                   "duracion_s": round(time.time() - t0, 1)}
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        estado = rec.get("abstenido")
        marca = "ABST" if estado else ("ERR" if "error" in rec else "RESP")
        print(f"[{i:02d}/30] {marca} {rec['duracion_s']}s — {pregunta[:50]}", flush=True)

print(f"LISTO -> {OUT}", flush=True)
