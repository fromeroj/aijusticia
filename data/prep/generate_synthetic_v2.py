"""
Genera ejemplos sintéticos de Q&A de ALTA CALIDAD para entrenamiento.

A diferencia de generate_synthetic_ift.py (que tomaba chunks aleatorios y
emparejaba preguntas genéricas inconexas), este script:

  1. Selecciona chunks SOLO de leyes federales principales (LFT, CFPC, CC,
     CPF, LFPDPPP, etc.) — no gazetas estatales ruidosas.
  2. Para cada chunk, extrae el tema central (artículo + concepto).
  3. Genera una pregunta ciudadana ESPECÍFICA que ese chunk responde.
  4. La respuesta incluye el artículo exacto + explicación ciudadana.

Esto produce ejemplos donde pregunta y respuesta están genuinamente
relacionadas, lo que es crítico para que el modelo aprenda patrones útiles.

Uso:
    python scripts/generate_synthetic_v2.py --count 5000
    python scripts/generate_synthetic_v2.py --count 5000 --use-llm  # más lento pero mejor
"""
from __future__ import annotations
import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

import psycopg
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ai_justicia.config import settings

OUTPUT_DIR = ROOT / "data" / "training"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LM_URL = "http://localhost:1234/v1/chat/completions"
MODEL = "qwen3.6-35b-a3b"

# Solo leyes de alta calidad para entrenamiento
LEYES_CALIDAD = [
    # Laboral
    ("Ley Federal del Trabajo", "Laboral"),
    # Civil federal
    ("Código Civil Federal", "Civil"),
    # Procedural civil
    ("Código Federal de Procedimientos Civiles", "Civil"),
    # Penal
    ("Código Penal Federal", "Penal"),
    # Procedural penal
    ("Código Nacional de Procedimientos Penales", "Penal"),
    # Consumidor
    ("Ley Federal de Protección al Consumidor", "Consumidor"),
    ("Ley Federal de Protección de Datos Personales", "Consumidor"),
    # Familiar (del CC)
    ("Código Civil Federal", "Familiar"),  # doble propósito
    # Constitucional
    ("Constitución Política de los Estados Unidos Mexicanos", "Constitucional"),
    # Amparo
    ("Ley de Amparo", "Amparo"),
    # Mercantil
    ("Código de Comercio", "Mercantil"),
    ("Ley General de Sociedades Mercantiles", "Mercantil"),
    # Administrativo
    ("Ley Federal de Procedimiento Administrativo", "Administrativo"),
    # Salud
    ("Ley General de Salud", "Salud"),
    # Educativo
    ("Ley General de Educación", "Educativo"),
    # Agrario
    ("Ley Agraria", "Agrario"),
    # Ambiental
    ("Ley General del Equilibrio Ecológico", "Ambiental"),
    # Migratorio
    ("Ley de Migración", "Migratorio"),
    # Electoral
    ("Ley General de Instituciones y Procedimientos Electorales", "Electoral"),
    # Fiscal
    ("Código Fiscal de la Federación", "Fiscal"),
    ("Ley del Impuesto al Valor Agregado", "Fiscal"),
    ("Ley del Impuesto Sobre la Renta", "Fiscal"),
]

# También algunos códigos civiles estatales clave (alta transferencia)
LEYES_ESTATALES_CALIDAD = [
    ("Ciudad de México", "Código Civil para el Distrito Federal", "Familiar"),
    ("Ciudad de México", "Código Civil para el Distrito Federal", "Civil"),
    ("Estado de México", "Código Civil del Estado de México", "Civil"),
    ("Jalisco", "Código Civil del Estado de Jalisco", "Civil"),
    ("Nuevo León", "Código Civil para el Estado de Nuevo León", "Civil"),
]

PROMPT_GEN = """Eres un generador de datos de entrenamiento para un asistente jurídico mexicano.

Te daré un fragmento de una ley mexicana. Tu trabajo:
1. Identificar qué concepto jurídico específico aborda el fragmento.
2. Generar UNA pregunta ciudadana natural (como la haría una persona común, en español mexicano coloquial).
3. Escribir una respuesta clara (máximo 200 palabras) que:
   - Cite el artículo exacto del fragmento con [1]
   - Explique en lenguaje ciudadano qué significa
   - Dé un paso concreto a seguir

La pregunta debe ser respondible EXCLUSIVAMENTE con el fragmento dado. No inventes información.

Fragmento:
---
{chunk}
---

Devuelve SOLO un JSON:
{{"pregunta": "...", "respuesta": "...texto con [1]...", "materia": "laboral|civil|penal|familiar|consumidor|constitucional|amparo|mercantil|administrativo|salud|educativo|agrario|ambiental|migratorio|electoral|fiscal", "calidad": "alta|media|baja"}}

Marca calidad "baja" si el fragmento es: tabla, índice, reformatorio, transitorio, o no contiene una norma sustantiva clara."""


def call_llm_json(prompt: str, temperature: float = 0.3, max_tokens: int = 2048) -> dict | None:
    try:
        r = requests.post(
            LM_URL,
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=180,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip()
        # Quitar markdown
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
        # Extraer JSON balanceado
        for i, c in enumerate(text):
            if c == "{":
                depth = 0
                in_str = False
                esc = False
                for j in range(i, len(text)):
                    ch = text[j]
                    if esc:
                        esc = False
                        continue
                    if ch == "\\":
                        esc = True
                        continue
                    if ch == '"':
                        in_str = not in_str
                        continue
                    if in_str:
                        continue
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            return json.loads(text[i : j + 1])
                break
        return None
    except Exception as e:
        return None


def get_chunks_from_law(conn, titulo_pattern: str, entidad: str | None, limit: int) -> list[tuple]:
    """Obtiene chunks sustantivos de una ley específica."""
    with conn.cursor() as cur:
        if entidad:
            cur.execute(
                """
                SELECT c.texto, d.titulo, d.fuente, d.entidad, d.materia
                FROM documentos_chunks c
                JOIN documentos d ON d.id = c.documento_id
                WHERE d.titulo ILIKE %s
                  AND d.entidad = %s
                  AND d.derogado = FALSE
                  AND LENGTH(c.texto) BETWEEN 200 AND 1500
                  AND c.texto !~ '^[0-9\\s\\.\\$,]+$'
                ORDER BY RANDOM()
                LIMIT %s
                """,
                (f"%{titulo_pattern}%", entidad, limit),
            )
        else:
            cur.execute(
                """
                SELECT c.texto, d.titulo, d.fuente, d.entidad, d.materia
                FROM documentos_chunks c
                JOIN documentos d ON d.id = c.documento_id
                WHERE d.titulo ILIKE %s
                  AND (d.entidad = 'Federal' OR d.entidad IS NULL)
                  AND d.derogado = FALSE
                  AND LENGTH(c.texto) BETWEEN 200 AND 1500
                  AND c.texto !~ '^[0-9\\s\\.\\$,]+$'
                ORDER BY RANDOM()
                LIMIT %s
                """,
                (f"%{titulo_pattern}%", limit),
            )
        return cur.fetchall()


def is_chunk_sustantivo(text: str) -> bool:
    """Filtra chunks que no son normas sustantivas."""
    t = text.strip()
    if len(t) < 150:
        return False
    # Tablas, índices, numeración pura
    if re.match(r"^(Artículo\s+\d+\.?\s*$|CAPÍTULO|TÍTULO|SECCIÓN)", t) and len(t) < 100:
        return False
    # Puros números/símbolos
    if re.match(r"^[\d\s\.\,\$\-+%/()]+$", t):
        return False
    # Transitorios
    if "PRIMERO.-" in t[:50] or "TRANSITORIO" in t[:100]:
        return False
    # Debe contener palabras jurídicas significativas
    palabras_juridicas = [
        "derecho", "obligación", "deber", "podrá", "deberá", "tendrá",
        "trabajador", "patrón", "arrendador", "arrendatario", "comprador",
        "vendedor", "deudor", "acreedor", "cónyuge", "concubinario",
        "procedimiento", "sanción", "infracción", "multa", "delito",
        "pena", "prisión", "indemnización", "compensación", "pago",
        "contrato", "obligación", "responsabilidad", "autoridad",
    ]
    t_lower = t.lower()
    return any(p in t_lower for p in palabras_juridicas)


def generar_ejemplo_sin_llm(chunk_text: str, titulo_doc: str, fuente: str, entidad: str, materia: str) -> dict | None:
    """Genera ejemplo sin LLM (más rápido, calidad media). Usa el chunk tal cual."""
    if not is_chunk_sustantivo(chunk_text):
        return None

    # Extraer número de artículo si está presente
    art_match = re.search(r"[Aa]rtículo\s+(\d+[A-Za-z]?)", chunk_text[:300])
    art_num = art_match.group(1) if art_match else None

    # Limpiar pasaje (primeros 400 chars significativos)
    pasaje = re.sub(r"\s+", " ", chunk_text[:400]).strip()
    if len(pasaje) < 100:
        return None

    # Materia del título
    materia_final = materia or "Civil"

    # Extraer tema del chunk (concepto principal tras el artículo)
    tema = ""
    # Buscar: "Artículo X.- <concepto>" — extraer frase corta significativa
    tema_match = re.search(r"[Aa]rtículo\s+\d+[A-Za-z]?\s*\.?-?\s*([A-ZÁÉÍÓÚÑa-záéíóúñ][\wáéíóúñ\s,]{15,80}?)[\.;]", chunk_text[:500])
    if tema_match:
        tema = tema_match.group(1).strip().lower()
        # Quitar artículos iniciales
        tema = re.sub(r"^(el|la|los|las|un|una|de|del|de los|de las)\s+", "", tema)
        # Quitar "trabajador/patrón/etc" repetitivos del inicio
        tema = re.sub(r"^(trabajador|trabajadora|patrón|patron|empleado)\s+(tiene|podrá|deberá|podrá)\s+", "", tema)
        # Validar que sea significativo
        if len(tema) < 10 or tema.startswith(("f ", "i ", "ii ", "iii ")):
            tema = ""

    # Generar pregunta específica según materia y tema detectado
    if tema and art_num:
        preguntas_template = {
            "Laboral": [
                f"¿Qué dice la ley sobre {tema}?",
                f"Tengo una duda sobre {tema}, ¿qué me ampara la ley?",
                f"¿Cuáles son mis derechos respecto a {tema}?",
            ],
            "Civil": [
                f"¿Qué establece la ley sobre {tema}?",
                f"¿Cómo me protege la ley en materia de {tema}?",
                f"Necesito entender qué dice la ley sobre {tema}",
            ],
            "Penal": [
                f"¿Es delito o qué consecuencias tiene {tema}?",
                f"¿Qué pena o sanción aplica para {tema}?",
                f"¿Cómo tipifica la ley el caso de {tema}?",
            ],
            "Familiar": [
                f"¿Qué derechos tengo sobre {tema}?",
                f"¿Cómo procede la ley familiar respecto a {tema}?",
                f"Necesito saber qué dice la ley sobre {tema} en mi familia",
            ],
            "Consumidor": [
                f"¿Qué protecciones tengo como consumidor sobre {tema}?",
                f"Me vulneraron en {tema}, ¿qué puedo hacer?",
                f"¿Qué establece PROFECO sobre {tema}?",
            ],
            "Constitucional": [
                f"¿Qué derecho constitucional tengo sobre {tema}?",
                f"¿Es constitucional lo que pasa con {tema}?",
                f"¿Qué garantía me ampara respecto a {tema}?",
            ],
        }
        pregunta = random.choice(preguntas_template.get(materia_final, preguntas_template["Civil"]))
        referencia = f"Artículo {art_num} de {titulo_doc}"
    elif art_num:
        # Si el título es muy largo (tesis SJF), usar referencia genérica
        if len(titulo_doc) > 60 or titulo_doc.isupper():
            pregunta = f"Tengo una consulta sobre el artículo {art_num} de la ley aplicable, ¿qué me dice?"
            referencia = f"Artículo {art_num}"
        else:
            pregunta = f"Tengo una consulta sobre el artículo {art_num} de {titulo_doc[:40]}, ¿puede orientarme?"
            referencia = f"Artículo {art_num} de {titulo_doc}"
    else:
        # Sin artículo claro: pregunta más genérica pero con materia
        preguntas_genericas = {
            "Laboral": "Tengo una duda sobre mis derechos laborales, ¿qué me dice la ley?",
            "Civil": "¿Cómo me protege la ley en mi situación civil?",
            "Penal": "¿Qué consecuencias penales podría tener esta situación?",
            "Familiar": "¿Qué derechos me da la ley familiar en mi caso?",
            "Consumidor": "¿Qué puedo hacer como consumidor ante esta situación?",
            "Constitucional": "¿Qué derechos constitucionales me amparan?",
        }
        pregunta = preguntas_genericas.get(materia_final, "¿Qué establece la ley sobre mi situación?")
        referencia = titulo_doc[:60]

    respuesta = (
        f"De acuerdo con {referencia}:\n\n"
        f"{pasaje}{'...' if len(chunk_text) > 400 else ''}\n\n"
        f"Esto significa que la ley contempla tu situación de manera específica. "
        f"Para aplicarlo a tu caso concreto y tomar acción legal, te recomiendo "
        f"consultar con un abogado con cédula profesional."
    )

    fuente_legible = (
        f"Ley federal: {titulo_doc[:60]}"
        if fuente == "LeyesBiblio"
        else f"Norma de {entidad}: {titulo_doc[:60]}"
    )

    return {
        "messages": [
            {
                "role": "system",
                "content": f"Eres AI Justicia, un asistente jurídico mexicano especializado en {materia_final}. Da orientación informativa con base en fuentes oficiales. No sustituyes la asesoría legal formal.",
            },
            {"role": "user", "content": pregunta},
            {"role": "assistant", "content": respuesta},
        ],
        "metadata": {
            "materia": materia_final,
            "fuente": fuente,
            "entidad": entidad or "Federal",
            "fuente_legible": fuente_legible,
            "titulo_documento": titulo_doc[:100],
            "pasaje_original": pasaje,
            "synthetic": True,
            "metodo": "no-llm",
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=5000)
    ap.add_argument("--use-llm", action="store_true", help="Usa LLM para generar Q&A (más lento, mejor calidad)")
    ap.add_argument("--output", default=str(OUTPUT_DIR / "synthetic_v2.jsonl"))
    ap.add_argument("--per-law", type=int, default=0, help="Max ejemplos por ley (0=proporcional)")
    args = ap.parse_args()

    print(f"Generando {args.count} ejemplos sintéticos de alta calidad...")
    print(f"Modo: {'LLM' if args.use_llm else 'sin-LLM (rápido)'}")
    print()

    conn = psycopg.connect(settings.psycopg_dsn)

    # Calcular cuántos chunks por ley
    total_leyes = len(LEYES_CALIDAD) + len(LEYES_ESTATALES_CALIDAD)
    per_law = args.per_law if args.per_law > 0 else (args.count // total_leyes) + 50

    all_ejemplos: list[dict] = []

    # Leyes federales
    for titulo, materia in LEYES_CALIDAD:
        if len(all_ejemplos) >= args.count:
            break
        print(f"  Buscando: {titulo[:50]}...")
        chunks = get_chunks_from_law(conn, titulo, None, per_law)
        print(f"    → {len(chunks)} chunks encontrados")

        for chunk_text, doc_titulo, fuente, entidad, materia_db in chunks:
            if len(all_ejemplos) >= args.count:
                break
            if args.use_llm:
                # Generar con LLM
                prompt = PROMPT_GEN.format(chunk=chunk_text[:1500])
                result = call_llm_json(prompt)
                if result and result.get("calidad") in ("alta", "media"):
                    all_ejemplos.append({
                        "messages": [
                            {
                                "role": "system",
                                "content": f"Eres AI Justicia, un asistente jurídico mexicano especializado en {result.get('materia', materia)}. Da orientación informativa con base en fuentes oficiales. No sustituyes la asesoría legal formal.",
                            },
                            {"role": "user", "content": result["pregunta"]},
                            {"role": "assistant", "content": result["respuesta"]},
                        ],
                        "metadata": {
                            "materia": result.get("materia", materia),
                            "fuente": fuente,
                            "entidad": entidad or "Federal",
                            "fuente_legible": doc_titulo[:60],
                            "titulo_documento": doc_titulo[:100],
                            "pasaje_original": chunk_text[:400],
                            "synthetic": True,
                            "metodo": "llm",
                        },
                    })
                time.sleep(0.2)
            else:
                ej = generar_ejemplo_sin_llm(chunk_text, doc_titulo, fuente, entidad or "Federal", materia_db or materia)
                if ej:
                    all_ejemplos.append(ej)

        print(f"    Total acumulado: {len(all_ejemplos)}")

    # Leyes estatales de calidad
    for entidad, titulo, materia in LEYES_ESTATALES_CALIDAD:
        if len(all_ejemplos) >= args.count:
            break
        print(f"  Buscando: {titulo[:40]} ({entidad})...")
        chunks = get_chunks_from_law(conn, titulo, entidad, per_law // 2)
        print(f"    → {len(chunks)} chunks encontrados")
        for chunk_text, doc_titulo, fuente, ent, materia_db in chunks:
            if len(all_ejemplos) >= args.count:
                break
            ej = generar_ejemplo_sin_llm(chunk_text, doc_titulo, fuente, entidad, materia_db or materia)
            if ej:
                all_ejemplos.append(ej)
        print(f"    Total acumulado: {len(all_ejemplos)}")

    conn.close()

    # Mezclar y guardar
    random.shuffle(all_ejemplos)
    with open(args.output, "w") as f:
        for ej in all_ejemplos:
            f.write(json.dumps(ej, ensure_ascii=False) + "\n")

    print(f"\n=== COMPLETADO ===")
    print(f"Ejemplos generados: {len(all_ejemplos)}")
    print(f"Output: {args.output}")

    # Stats por materia
    from collections import Counter
    materias = Counter(ej["metadata"]["materia"] for ej in all_ejemplos)
    print(f"\nPor materia:")
    for m, c in materias.most_common():
        print(f"  {m}: {c}")


if __name__ == "__main__":
    main()
