"""
Pipeline para procesar preguntas reales (internacionales + nacionales) y convertirlas
en ejemplos de entrenamiento con respuestas ancladas en ley mexicana.

Etapas:
  1. Filtra ruido (preguntas demasiado cortas, nombres propios, spam)
  2. Filtra preguntas demasiado específicas de EE.UU. (baja transferencia)
  3. Lote 1: traduce EN→ES + clasifica materia + determina jurisdicción
  4. Lote 2: para cada pregunta, recupera pasajes relevantes del corpus (FTS+vectorial)
     y genera respuesta anclada con citas [n]
  5. Guarda JSONL listo para LoRA

Uso:
  python -m scripts.process_questions [--max N] [--source international|combined]
"""
from __future__ import annotations
import argparse, json, os, re, sys, time
from pathlib import Path
from typing import Any

import requests

# Paths
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TRAIN_DIR = DATA / "training"
TRAIN_DIR.mkdir(parents=True, exist_ok=True)

LM_URL = "http://localhost:1234/v1/chat/completions"
MODEL = "qwen3.6-35b-a3b"
EMBED_MODEL = "text-embedding-nomic-embed-text-v1.5"

# Materias válidas (deben coincidir con query_analysis.py)
MATERIAS = {
    "laboral", "civil", "familiar", "penal", "administrativo",
    "mercantil", "constitucional", "amparo", "fiscal", "agrario",
    "electoral", "migratorio", "ambiental", "consumidor", "propiedad",
    "salud", "educativo", "otro",
}

# Patrones para descartar ruido obvio
NOISE_RE = re.compile(
    r"^(angel|juan|jose|maria|pedro|luis|carlos|antonio|manuel|francisco|jorge|ricardo|miguel|raul)\b",
    re.IGNORECASE,
)
US_HEAVY_RE = re.compile(
    r"\b(2nd amendment|first amendment|IRS|USPS|FAFSA|Fourth Amendment|Fifth Amendment|"
    r"Sixth Amendment|Eighth Amendment|Fourteenth Amendment|Social Security|Medicare|Medicaid|"
    r"Green Card|FAA|FCC|FTC|SEC|ATF|FBI|CIA|Sheriff|DMV|property tax|sales tax|income tax|"
    r"Congress|Senate|House of Representatives|Supreme Court|White House|President)\b",
    re.IGNORECASE,
)


def is_question_valid(q: str, language: str) -> bool:
    """Filtra preguntas que no aportan valor de entrenamiento."""
    q = q.strip()
    if len(q) < 12 or len(q) > 250:
        return False
    # Nombres propios sueltos
    if NOISE_RE.match(q) and len(q.split()) < 6:
        return False
    # Demasiado específico de EE.UU.
    if language == "en" and len(US_HEAVY_RE.findall(q)) >= 2:
        return False
    # Spam / off-topic
    spam = ["http", "www.", ".com", "@", "whatsapp", "facebook"]
    if any(s in q.lower() for s in spam):
        return False
    return True


def call_llm(messages: list[dict], temperature: float = 0.1, max_tokens: int = 8192, timeout: int = 180) -> str:
    """Llama a LM Studio y devuelve solo el contenido (no el reasoning)."""
    r = requests.post(
        LM_URL,
        json={"model": MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def call_llm_json(messages: list[dict], temperature: float = 0.1, max_tokens: int = 8192, timeout: int = 180) -> Any:
    """Llama a LLM y parsea respuesta JSON (extrae el primer {...} o [...])."""
    text = call_llm(messages, temperature, max_tokens, timeout)
    # Quitar bloque de código markdown
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Buscar el primer { o [ y hacer parseo balanceado
        start_chars = {"{": "}", "[": "]"}
        for start_idx in range(len(text)):
            if text[start_idx] in start_chars:
                open_ch = text[start_idx]
                close_ch = start_chars[open_ch]
                depth = 0
                in_str = False
                escape = False
                for end_idx in range(start_idx, len(text)):
                    c = text[end_idx]
                    if escape:
                        escape = False
                        continue
                    if c == "\\":
                        escape = True
                        continue
                    if c == '"':
                        in_str = not in_str
                        continue
                    if in_str:
                        continue
                    if c == open_ch:
                        depth += 1
                    elif c == close_ch:
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(text[start_idx : end_idx + 1])
                            except json.JSONDecodeError:
                                break
                break
        raise ValueError(f"No se pudo parsear JSON: {text[:300]}")


def embed(text: str) -> list[float]:
    r = requests.post(
        "http://localhost:1234/v1/embeddings",
        json={"model": EMBED_MODEL, "input": text[:8000]},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["data"][0]["embedding"]


# ---------- ETAPA 1+2+3: Filtrar + Traducir + Clasificar ----------

PROMPT_TC = """Eres un asistente jurídico mexicano. Para cada pregunta, devuelve un JSON con:
- "pregunta_es": la pregunta en español mexicano coloquial (como la preguntaría un ciudadano). Si ya está en español, normalízala (corrige errores, mayúsculas, puntuación).
- "materia": una de: laboral, civil, familiar, penal, administrativo, mercantil, constitucional, amparo, fiscal, agrario, electoral, migratorio, ambiental, consumidor, propiedad, salud, educativo, otro.
- "jurisdiccion": "federal" si es sobre leyes federales (ej. LFT, CFPC, CPEUM), "estatal" si depende del estado (ej. Código Civil estatal), "mixta" si ambas.
- "valida": true si es una pregunta jurídica real y aplicable al contexto mexicano; false si es off-topic, spam, demasiado específica de otro país, o no es jurídica.

Devuelve SOLO un arreglo JSON con {n} objetos, uno por pregunta, en el mismo orden. Sin texto adicional."""

def batch_translate_classify(questions: list[dict], batch_size: int = 15) -> list[dict]:
    """Para cada lote de preguntas, traduce + clasifica + valida en una sola llamada."""
    out: list[dict] = []
    for i in range(0, len(questions), batch_size):
        batch = questions[i : i + batch_size]
        items = "\n".join(f"{j+1}. ({q['language']}) {q['question']}" for j, q in enumerate(batch))
        messages = [
            {"role": "system", "content": PROMPT_TC},
            {"role": "user", "content": f"{items}\n\nDevuelve un JSON array de {len(batch)} objetos."},
        ]
        try:
            results = call_llm_json(messages, temperature=0.1, max_tokens=6144)
            if not isinstance(results, list):
                results = [results]
            for j, q in enumerate(batch):
                if j < len(results):
                    r = results[j]
                    out.append({
                        **q,
                        "pregunta_es": str(r.get("pregunta_es", q["question"]))[:300],
                        "materia": str(r.get("materia", "otro")).lower()[:30],
                        "jurisdiccion": str(r.get("jurisdiccion", "mixta")).lower()[:10],
                        "valida": bool(r.get("valida", True)),
                    })
                else:
                    out.append({**q, "pregunta_es": q["question"], "materia": "otro", "jurisdiccion": "mixta", "valida": False})
        except Exception as e:
            print(f"  batch {i}: ERROR {str(e)[:80]}")
            for q in batch:
                out.append({**q, "pregunta_es": q["question"], "materia": "otro", "jurisdiccion": "mixta", "valida": False})
        if (i // batch_size) % 4 == 0:
            print(f"  lote {i}: {len(out)} procesadas")
        time.sleep(0.3)
    return out


# ---------- ETAPA 4: Respuesta anclada con RAG ----------

PROMPT_ANSWER = """Eres AI Justicia, un asistente jurídico mexicano. Responde la pregunta del ciudadano basándote EXCLUSIVAMENTE en los pasajes legales proporcionados.

Reglas estrictas:
1. Cita cada afirmación con [n] donde n es el número del pasaje.
2. Si los pasajes no abordan la pregunta, di "No encontré normas que respondan tu pregunta" y abstente.
3. No inventes artículos, fracciones ni números.
4. Usa lenguaje claro y coloquial. Máximo 250 palabras.
5. Estructura: situación general → norma aplicable → pasos a seguir.

Devuelve SOLO un JSON: {{"respuesta": "...texto con [n]...", "citas_usadas": [n1, n2, ...]}}"""


def retrieve_passages(query: str, materia: str, top_k: int = 5) -> list[dict]:
    """Recupera pasajes del corpus vía FTS + vectorial híbrido + reranking."""
    try:
        from ai_justicia.pipeline.retrieve import recuperar_y_rerankear
        from ai_justicia.pipeline.query_analysis import analizar_consulta
        analisis = analizar_consulta(query)
        resultados = recuperar_y_rerankear(query, analisis)
        return [
            {
                "fuente": r.fuente,
                "titulo": r.titulo,
                "texto": r.texto,
                "materia": r.materia,
                "entidad": r.entidad,
                "jerarquia": r.jerarquia,
                "vinculante": r.vinculante,
                "score": r.score,
            }
            for r in resultados[:top_k]
        ]
    except Exception as e:
        print(f"    retrieve error: {str(e)[:80]}")
        return []


def generate_answer(question: str, materia: str) -> dict | None:
    """Recupera pasajes y genera respuesta anclada. Devuelve {respuesta, pasajes, citas_usadas}."""
    pasajes = retrieve_passages(question, materia, top_k=5)
    if not pasajes:
        return None

    context = "\n\n".join(
        f"[{i+1}] ({p.get('fuente','')} / {p.get('titulo','')[:60]}) {p.get('texto','')[:600]}"
        for i, p in enumerate(pasajes)
    )
    messages = [
        {"role": "system", "content": PROMPT_ANSWER},
        {"role": "user", "content": f"Pregunta: {question}\n\nMateria: {materia}\n\nPasajes:\n{context}"},
    ]
    try:
        result = call_llm_json(messages, temperature=0.2, max_tokens=8192, timeout=300)
        return {
            "respuesta": str(result.get("respuesta", ""))[:2000],
            "citas_usadas": result.get("citas_usadas", []),
            "pasajes": [
                {
                    "fuente": p.get("fuente", ""),
                    "titulo": p.get("titulo", "")[:100],
                    "texto": p.get("texto", "")[:600],
                    "jerarquia": p.get("jerarquia", 99),
                }
                for i, p in enumerate(pasajes)
                if (i + 1) in (result.get("citas_usadas") or [])
            ],
        }
    except Exception as e:
        print(f"    answer error: {str(e)[:80]}")
        return None


# ---------- MAIN ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0, help="Máximo número de preguntas (0=todas)")
    ap.add_argument("--source", choices=["international", "combined", "all"], default="all")
    ap.add_argument("--skip-translate", action="store_true", help="Saltar traducción/clasificación")
    ap.add_argument("--skip-answer", action="store_true", help="Saltar generación de respuestas")
    ap.add_argument("--batch-size", type=int, default=15)
    ap.add_argument("--output", default=str(TRAIN_DIR / "real_qa_dataset.jsonl"))
    args = ap.parse_args()

    # Cargar preguntas de todas las fuentes
    all_qs: list[dict] = []
    files = [
        ("data/international_questions.json", "international"),
        ("data/extra_questions.json", "profi"),
        ("data/extra_questions_unanswered.json", "profi"),
        ("data/foro_dataset.json", "foro"),
    ]
    for path, src_tag in files:
        p = ROOT / path
        if p.exists():
            with open(p) as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    q = item.get("question") or item.get("titulo") or item.get("q") or ""
                    if q:
                        all_qs.append({
                            "question": str(q)[:250],
                            "language": item.get("language", "es"),
                            "source": item.get("source", src_tag),
                        })
            print(f"  {path}: {len(data)} crudas")

    # Deduplicar por pregunta normalizada
    seen: set[str] = set()
    unique: list[dict] = []
    for q in all_qs:
        key = re.sub(r"\s+", " ", q["question"].lower().strip())[:100]
        if key not in seen:
            seen.add(key)
            unique.append(q)
    print(f"\nTotal únicas: {len(unique)}")

    # Filtrar ruido
    valid = [q for q in unique if is_question_valid(q["question"], q["language"])]
    print(f"Tras filtro de validez: {len(valid)}")

    if args.max > 0:
        valid = valid[: args.max]
        print(f"Limitando a --max: {len(valid)}")

    # ETAPA 1+2+3: Traducir + Clasificar
    if not args.skip_translate:
        print(f"\n=== ETAPA 1+2+3: Traducir + Clasificar ({len(valid)} preguntas) ===")
        processed = batch_translate_classify(valid, batch_size=args.batch_size)
        # Filtrar las marcadas como inválidas
        processed = [q for q in processed if q.get("valida", True)]
        print(f"Válidas tras clasificación: {len(processed)}")
        # Guardar intermedio
        with open(DATA / "processed_questions.json", "w") as f:
            json.dump(processed, f, ensure_ascii=False, indent=2)
        print(f"Guardado intermedio: data/processed_questions.json")
    else:
        with open(DATA / "processed_questions.json") as f:
            processed = json.load(f)
        print(f"Cargadas {len(processed)} preguntas procesadas")

    # ETAPA 4: Generar respuestas ancladas
    if not args.skip_answer:
        print(f"\n=== ETAPA 4: Generar respuestas ancladas con RAG ({len(processed)} preguntas) ===")
        out_path = Path(args.output)
        n_done = 0
        n_abstain = 0
        with open(out_path, "w") as fout:
            for i, q in enumerate(processed):
                pregunta = q["pregunta_es"]
                materia = q.get("materia", "otro")
                ans = generate_answer(pregunta, materia)
                if ans is None or not ans["respuesta"]:
                    n_abstain += 1
                    continue
                # Detectar abstención
                abstencion = "no encontré" in ans["respuesta"].lower() or "abstengo" in ans["respuesta"].lower()
                if abstencion:
                    n_abstain += 1
                    continue

                example = {
                    "instruction": pregunta,
                    "input": "",
                    "output": ans["respuesta"],
                    "materia": materia,
                    "jurisdiccion": q.get("jurisdiccion", "mixta"),
                    "source": q.get("source", ""),
                    "language": q.get("language", "es"),
                    "pasajes": ans["pasajes"],
                    "tipo": "real",
                }
                fout.write(json.dumps(example, ensure_ascii=False) + "\n")
                n_done += 1
                if n_done % 20 == 0:
                    print(f"  [{i+1}/{len(processed)}] {n_done} respuestas, {n_abstain} abstenciones")
                time.sleep(0.2)

        print(f"\n=== COMPLETADO ===")
        print(f"Respuestas generadas: {n_done}")
        print(f"Abstenciones (sin norma): {n_abstain}")
        print(f"Output: {out_path}")


if __name__ == "__main__":
    main()
