"""
Procesa un conjunto de preguntas a través del pipeline RAG completo:
  1. Recupera pasajes relevantes (FTS + vectorial)
  2. Genera respuesta anclada con LoRA (mlx_lm.server)
  3. Guarda resultado en JSONL

Uso:
    python scripts/batch_rag.py --input data/questions_to_process.json --output data/rag_results.jsonl --limit 0
    python scripts/batch_rag.py --input data/questions_to_process.json --output data/rag_results.jsonl --limit 100 --spanish-only
"""
from __future__ import annotations
import argparse, json, re, sys, time, os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
LLM_URL = "http://localhost:1235/v1/chat/completions"
MODEL = os.environ.get("AIJ_MODEL", "/Users/fabianromero/.lmstudio/models/mlx-community/Qwen3.6-35B-A3B-bf16")

SYSTEM_PROMPT = (
    "Eres AI Justicia, un asistente jurídico mexicano especializado en orientar a "
    "ciudadanos. Respondes en español mexicano, en lenguaje claro y directo (tuteo).\n\n"
    "REGLAS DE CITAS:\n"
    "- Después de cada afirmación legal, coloca la cita [n] del pasaje que la respalda.\n"
    "- NO escribas [NO SUSTENTADO] salvo que la oración afirme algo que NINGÚN pasaje toca.\n"
    "- Explicaciones, contexto y pasos prácticos pueden usar conocimiento general del "
    "derecho mexicano, pero la afirmación legal central debe llevar [n].\n"
    "- IMPORTANTE: no digas 'no hay base suficiente' cuando sí la hay. Si los pasajes "
    "tocan el tema, responde con confianza citándolos.\n\n"
    "ESTILO:\n"
    "- Responde directamente a la pregunta.\n"
    "- Termina con máximo 2 oraciones de cierre, sugiriendo consultar un abogado con "
    "cédula si necesita actuar legalmente.\n"
    "- Tu orientación es estrictamente informativa."
)


def call_llm_json(prompt: str, temperature: float = 0.2, max_tokens: int = 8192) -> str:
    """Llama al LLM (mlx_lm.server con LoRA) y devuelve content.
    Usa enable_thinking=False para respuesta directa (18x más rápido).
    """
    r = requests.post(
        LLM_URL,
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        timeout=300,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def retrieve(query: str, top_k: int = 5) -> tuple[list[dict], list]:
    """Recupera pasajes del corpus y filtra por relevancia con LLM.
    Returns (pasajes_dict, pasajes_resultado) — los filtrados.
    """
    try:
        from ai_justicia.pipeline.query_analysis import analizar_consulta
        from ai_justicia.pipeline.retrieve import recuperar_y_rerankear
        from ai_justicia.pipeline.relevance import filtrar_relevantes
        analisis = analizar_consulta(query)
        pasajes_raw = recuperar_y_rerankear(query, analisis)

        # Filtro de relevancia LLM
        pasajes_filtrados = filtrar_relevantes(query, pasajes_raw)

        return (
            [
                {
                    "fuente": p.fuente, "titulo": p.titulo, "texto": p.texto,
                    "materia": p.materia, "entidad": p.entidad, "jerarquia": p.jerarquia,
                }
                for p in pasajes_filtrados[:top_k]
            ],
            pasajes_filtrados[:top_k],
        )
    except Exception as e:
        print(f"    retrieve error: {str(e)[:60]}")
        return [], []


def translate_if_needed(question: str, language: str) -> str:
    """Traduce al español si está en inglés."""
    if language == "es":
        return question
    # Simple: use the LLM to translate
    try:
        text = call_llm_json(
            f"Traduce al español mexicano esta pregunta jurídica. Responde SOLO la traducción:\n\n{question}",
            temperature=0.1, max_tokens=512,
        )
        text = re.sub(r"^<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()
        return text if len(text) > 10 else question
    except:
        return question


def process_question(item: dict, idx: int) -> dict:
    """Procesa una pregunta: traduce, recupera, genera respuesta."""
    question = item["question"]
    language = item.get("language", "es")
    source = item.get("source", "?")

    # Translate if needed
    if language != "es":
        question_es = translate_if_needed(question, language)
    else:
        question_es = question

    # Retrieve + filter
    pasajes, pasajes_raw = retrieve(question_es, top_k=5)

    # Build context
    if pasajes:
        context = "\n\n".join(
            f"[{i+1}] ({p['fuente']} / {p['titulo'][:50]}) {p['texto'][:600]}"
            for i, p in enumerate(pasajes)
        )
        prompt = f"{SYSTEM_PROMPT}\n\nPregunta: {question_es}\n\nPasajes:\n{context}\n\nRESPUESTA:"
    else:
        prompt = f"{SYSTEM_PROMPT}\n\nPregunta: {question_es}\n\n(No se encontraron pasajes relevantes en el corpus. Si sabes la respuesta por conocimiento general del derecho mexicano, respóndela. Si no, di que no encontraste normas.)\n\nRESPUESTA:"

    # Generate
    try:
        respuesta = call_llm_json(prompt, temperature=0.2, max_tokens=8192)
        respuesta = re.sub(r"^<think>.*?</think>\s*", "", respuesta, flags=re.DOTALL).strip()
    except Exception as e:
        respuesta = f"ERROR: {str(e)[:100]}"

    # Detect abstention
    abstencion = bool(re.search(r"no encontré|no hay norma|no encontr|abstengo", respuesta.lower()))

    return {
        "idx": idx,
        "question_original": question,
        "question_es": question_es,
        "language": language,
        "source": source,
        "respuesta": respuesta[:2000],
        "abstencion": abstencion,
        "pasajes": [
            {"fuente": p["fuente"], "titulo": p["titulo"][:100], "texto": p["texto"][:400]}
            for p in pasajes
        ],
        "n_pasajes": len(pasajes),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/questions_to_process.json")
    ap.add_argument("--output", default="data/rag_results.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    ap.add_argument("--spanish-only", action="store_true")
    ap.add_argument("--resume", action="store_true", help="Skip already processed")
    args = ap.parse_args()

    with open(args.input) as f:
        questions = json.load(f)

    if args.spanish_only:
        questions = [q for q in questions if q.get("language") == "es"]
        print(f"Spanish only: {len(questions)}")

    if args.limit > 0:
        questions = questions[:args.limit]

    print(f"Processing {len(questions)} questions → {args.output}")

    # Resume: load existing results
    done_ids = set()
    if args.resume and Path(args.output).exists():
        with open(args.output) as f:
            for line in f:
                try:
                    d = json.loads(line)
                    done_ids.add(d["idx"])
                except:
                    pass
        print(f"Resuming: {len(done_ids)} already processed")

    results_count = 0
    with open(args.output, "a") as fout:
        for i, item in enumerate(questions):
            if i in done_ids:
                continue

            t0 = time.time()
            result = process_question(item, i)
            elapsed = time.time() - t0

            fout.write(json.dumps(result, ensure_ascii=False) + "\n")
            fout.flush()
            results_count += 1

            status = "ABSTAIN" if result["abstencion"] else "ANSWER"
            q_preview = result["question_es"][:50]
            print(f"  [{i+1}/{len(questions)}] {status} ({elapsed:.0f}s) {q_preview}...")

            # Checkpoint every 10
            if results_count % 10 == 0:
                print(f"  --- Checkpoint: {results_count} processed ---")

    print(f"\n=== COMPLETED: {results_count} questions processed ===")
    print(f"Results: {args.output}")


if __name__ == "__main__":
    main()
