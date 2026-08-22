"""Convierte el dataset del foro a formato JSONL para entrenamiento.

Genera tres tipos de ejemplos:
  1. Q&A directo (pregunta → respuesta ciudadana)
  2. Clasificación de materia (pregunta → materia)
  3. Detección de jurisdicción (pregunta → federal/estatal)

Uso:
    python scripts/build_training_dataset.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INPUT = DATA_DIR / "foro_dataset.json"
OUTPUT_DIR = DATA_DIR / "training"

# Keywords para clasificar materas
MATERIA_KEYWORDS = {
    "Civil": ["civil", "renta", "contrato", "propiedad", "divorcio", "pensión", "alimentos", "herencia", "testamento", "escritura", "arrendamiento", "deuda", "pagaré", "condómino", "servidumbre"],
    "Penal": ["penal", "robo", "delito", "denuncia", "ministerio público", "preso", "cárcel", "acusación", "fraude", "abuso", "lesiones", "homicidio", "narco"],
    "Laboral": ["trabajo", "laboral", "despido", "finiquito", "aguinaldo", "patrón", "empleado", "salario", "jornada", "sindical", "renuncia", "despido injustificado"],
    "Mercantil": ["banco", "tarjeta", "cargo", "condusef", "crédito", "deuda bancaria", "comercio", "empresa", "sociedad", "quiebra"],
    "Familiar": ["familia", "hijos", "custodia", "visitas", "matrimonio", "divorcio", "pensión alimenticia", "paternidad", "adopción"],
    "Administrativo": ["acta", "registro civil", "curp", "rfc", "ine", "pasaporte", "licencia", "permiso", "trámite", "gobierno", "autoridad"],
    "Constitucional": ["amparo", "constitución", "derechos humanos", "garantías", "inconstitucional"],
    "Fiscal": ["impuesto", "sat", "iva", "isr", "factura", "hacienda", "fiscal"],
}


def detectar_materia(text: str) -> str:
    text_lower = text.lower()
    for materia, keywords in MATERIA_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return materia
    return "Otra"


def detectar_jurisdiccion(text: str) -> str:
    """Detecta si la pregunta es federal o estatal."""
    text_lower = text.lower()
    estados = ["cdmx", "ciudad de méxico", "estado de méxico", "edomex", "jalisco", "nuevo león",
               "puebla", "veracruz", "oaxaca", "chiapas", "guerrero", "michoacán", "guanajuato",
               "sonora", "coahuila", "tamaulipas", "chihuahua", "baja california", "yucatán",
               "quintana roo", "sinaloa", "durango", "zacatecas", "aguascalientes", "nayarit",
               "colima", "tlaxcala", "querétaro", "morelos", "tabasco", "campeche", "hidalgo"]
    for est in estados:
        if est in text_lower:
            return "Estatal"
    return "Federal"


def clean_text(text: str) -> str:
    """Limpia HTML entities y whitespace."""
    text = text.replace("&aacute;", "á").replace("&eacute;", "é").replace("&iacute;", "í")
    text = text.replace("&oacute;", "ó").replace("&uacute;", "ú").replace("&ntilde;", "ñ")
    text = text.replace("&Aacute;", "Á").replace("&Eacute;", "É").replace("&Iacute;", "Í")
    text = text.replace("&Oacute;", "Ó").replace("&Uacute;", "Ú").replace("&Ntilde;", "Ñ")
    text = text.replace("&quot;", '"').replace("&amp;", "&").replace("&#39;", "'")
    text = text.replace("&iquest;", "¿").replace("&iexcl;", "¡").replace("&nbsp;", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(INPUT) as f:
        data = json.load(f)

    print(f"Dataset: {len(data)} Q&A pairs")

    # 1. Q&A en formato chat (para instruction tuning)
    qa_dataset = []
    for d in data:
        pregunta = clean_text(d.get("question", ""))
        if len(pregunta) < 20:
            continue
        respuestas = [clean_text(r) for r in d.get("responses", []) if len(clean_text(r)) > 30]
        if not respuestas:
            continue

        materia = detectar_materia(d["title"] + " " + pregunta)
        jurisdiccion = detectar_jurisdiccion(d["title"] + " " + pregunta)

        qa_dataset.append({
            "messages": [
                {"role": "system", "content": f"Eres AI Justicia, un asistente jurídico mexicano. La consulta es de materia {materia}, jurisdicción {jurisdiccion}. Responde en español, en lenguaje claro y ciudadano."},
                {"role": "user", "content": pregunta},
                {"role": "assistant", "content": respuestas[0]},  # mejor respuesta
            ],
            "metadata": {
                "materia": materia,
                "jurisdiccion": jurisdiccion,
                "source": "justiciamexico.mx/foro",
                "id": d["id"],
            },
        })

    # 2. Clasificación de materia (para evaluar el modelo)
    materia_dataset = []
    for d in data:
        text = clean_text(d["title"] + " " + d.get("question", ""))
        if len(text) < 20:
            continue
        materia = detectar_materia(text)
        materia_dataset.append({
            "input": text[:500],
            "expected_materia": materia,
        })

    # 3. Detección de jurisdicción
    jurisdiccion_dataset = []
    for d in data:
        text = clean_text(d["title"] + " " + d.get("question", ""))
        if len(text) < 20:
            continue
        jur = detectar_jurisdiccion(text)
        jurisdiccion_dataset.append({
            "input": text[:500],
            "expected_jurisdiccion": jur,
        })

    # Guardar JSONL
    qa_path = OUTPUT_DIR / "ift_qa.jsonl"
    with open(qa_path, "w") as f:
        for item in qa_dataset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    mat_path = OUTPUT_DIR / "eval_materia.jsonl"
    with open(mat_path, "w") as f:
        for item in materia_dataset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    jur_path = OUTPUT_DIR / "eval_jurisdiccion.jsonl"
    with open(jur_path, "w") as f:
        for item in jurisdiccion_dataset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"\n=== Datasets generados ===")
    print(f"  IFT Q&A:     {len(qa_dataset):>5} ejemplos → {qa_path}")
    print(f"  Eval materia: {len(materia_dataset):>5} ejemplos → {mat_path}")
    print(f"  Eval jurisd:  {len(jurisdiccion_dataset):>5} ejemplos → {jur_path}")

    # Distribución de materias
    from collections import Counter
    mat_counts = Counter(item["metadata"]["materia"] for item in qa_dataset)
    print(f"\n=== Distribución por materia ===")
    for m, n in mat_counts.most_common():
        print(f"  {m:<15} {n:>4}")

    jur_counts = Counter(item["metadata"]["jurisdiccion"] for item in qa_dataset)
    print(f"\n=== Distribución por jurisdicción ===")
    for j, n in jur_counts.most_common():
        print(f"  {j:<10} {n:>4}")

    print(f"\n=== Sample Q&A ===")
    print(f"Q: {qa_dataset[0]['messages'][1]['content'][:100]}...")
    print(f"A: {qa_dataset[0]['messages'][2]['content'][:100]}...")


if __name__ == "__main__":
    main()
