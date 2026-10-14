"""Genera ejemplos sintéticos de Q&A para entrenamiento desde el corpus real.

Estrategia: toma fragmentos reales de leyes/tesis del corpus y genera
preguntas ciudadanas + respuestas ancladas a esos fragmentos.

Genera 3 tipos de ejemplos:
  1. Pregunta ciudadana + respuesta legal (formato chat)
  2. Pregunta de clasificación de materia
  3. Pregunta de identificación de fuente

Uso:
    python scripts/generate_synthetic_ift.py --count 15000
"""

from __future__ import annotations

import argparse
import json
import random
import re
from datetime import date
from pathlib import Path

import psycopg

import sys; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ai_justicia.config import settings

OUTPUT_DIR = DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "training"

# Plantillas de preguntas ciudadanas por materia
PLANTILLAS_PREGUNTAS = {
    "Civil": [
        "Mi casero quiere subir la renta {detalle}, ¿es legal?",
        "Firmé un contrato de arrendamiento y {detalle}, ¿qué puedo hacer?",
        "Me deben dinero por {detalle} y no me pagan, ¿cómo lo recupero?",
        "Mi vecino {detalle}, ¿qué derechos tengo?",
        "Quiero divorciarme y {detalle}, ¿cómo procedo?",
        "Mi familiar falleció y dejó {detalle}, ¿cómo heredo?",
        "Compré una propiedad y {detalle}, ¿qué hago?",
        "Me vendieron algo defectuoso y {detalle}, ¿puedo demandar?",
    ],
    "Penal": [
        "Me acusan falsamente de {detalle}, ¿qué hago?",
        "Robaron {detalle}, ¿cómo pongo una denuncia?",
        "Mi familiar está detenido por {detalle}, ¿qué derechos tiene?",
        "Fui víctima de {detalle}, ¿cómo procedo legalmente?",
        "Me amenazaron con {detalle}, ¿es delito?",
        "Me detuvieron sin motivo por {detalle}, ¿qué puedo hacer?",
    ],
    "Laboral": [
        "Me despidieron sin motivo {detalle}, ¿qué tengo derecho?",
        "Mi patrón no me paga {detalle}, ¿cómo lo reclamo?",
        "No me quieren pagar mi finiquito {detalle}, ¿qué hago?",
        "Me deben aguinaldo {detalle}, ¿cómo lo exijo?",
        "Me obligan a trabajar {detalle}, ¿es legal?",
        "Me renunciaron {detalle}, ¿qué indemnización me corresponde?",
    ],
    "Mercantil": [
        "Me cobraron un cargo no autorizado {detalle}, ¿qué hago?",
        "El banco me cobró {detalle} y no lo reconozco, ¿cómo lo reclamo?",
        "Compré algo en línea y {detalle}, ¿puedo pedir reembolso?",
        "Una empresa me debe {detalle}, ¿cómo cobro?",
        "Fui víctima de fraude {detalle}, ¿a dónde acudo?",
    ],
    "Familiar": [
        "Mi ex no me deja ver a mis hijos {detalle}, ¿cómo solicito visitas?",
        "No me pagan pensión alimenticia {detalle}, ¿qué hago?",
        "Quiero la custodia de mi hijo {detalle}, ¿cómo procedo?",
        "Mi pareja y yo queremos divorciarnos {detalle}, ¿qué nos corresponde?",
        "Quiero reconocer a mi hijo {detalle}, ¿cómo lo hago?",
    ],
    "Administrativo": [
        "Necesito mi acta de nacimiento {detalle}, ¿dónde la consigo?",
        "Me equivocaron en mi acta {detalle}, ¿cómo la corrijo?",
        "Mi trámite de {detalle} está demorado, ¿qué puedo hacer?",
        "Me negaron un permiso de {detalle}, ¿cómo lo apelo?",
    ],
    "Fiscal": [
        "El SAT me cobra {detalle}, ¿está correcto?",
        "No estoy de acuerdo con mi declaración de {detalle}, ¿qué hago?",
        "Me llegaron a embargar por {detalle}, ¿cómo lo defiendo?",
        "Quiero facturar {detalle}, ¿cómo me doy de alta?",
    ],
    "Constitucional": [
        "Siento que se violaron mis derechos {detalle}, ¿puedo ampararme?",
        "Una autoridad me {detalle}, ¿es constitucional?",
        "Quiero interponer un amparo contra {detalle}, ¿cómo funciona?",
        "Mis derechos humanos fueron violados {detalle}, ¿a dónde acudo?",
    ],
}

DETALLES = [
    "sin previo aviso", "y no sé mis derechos", "en la CDMX", "en mi trabajo",
    "y necesito orientación", "hace varios meses", "sin contrato por escrito",
    "y tengo testigos", "y no tengo recursos", "urgentemente", "y soy extranjero",
    "y soy menor de edad", "y no tengo papeles", "y estoy embarazada",
    "con discapacidad", "y soy adulto mayor", "por WhatsApp", "por internet",
    "en el banco", "en una tienda", "en mi casa", "en la calle",
    "y ya pagué", "y tengo recibos", "y tengo contrato firmado",
    "sin razón aparente", "por error administrativo", "y no me dan solución",
]

# Respuestas tipo (se combinan con el fragmento real del corpus)
RESPUESTA_INICIO = [
    "Según la legislación mexicana aplicable:",
    "Con base en lo que establece la ley:",
    "De acuerdo con la normativa vigente:",
    "La ley contempla esta situación de la siguiente manera:",
    "En tu caso, aplica lo siguiente:",
]

RESPUESTA_FIN = [
    "Te recomiendo consultar con un abogado con cédula para revisar tu caso específico.",
    "Si necesitas actuar formalmente, un abogado puede representarte en el procedimiento.",
    "Acude a la defensoría pública o a un abogado de tu confianza para tomar acción.",
    "Considera presentar tu queja ante la autoridad correspondiente si tus derechos fueron vulnerados.",
    "Para tomar acción legal formal, siempre necesitarás asesoría de un abogado con cédula.",
]


def detectar_materia_chunk(titulo: str) -> str:
    t = titulo.lower()
    for materia, keywords in {
        "Civil": ["civil", "arrendamiento", "renta", "contrato", "propiedad", "obligaciones"],
        "Penal": ["penal", "delito", "robo", "fraude", "ejecución", "sanciones"],
        "Laboral": ["trabajo", "laboral", "trabajador", "patrón", "despido", "finiquito"],
        "Mercantil": ["mercantil", "comercio", "bancario", "instituciones de crédito"],
        "Familiar": ["familiar", "familia", "pensión", "alimentos", "custodia", "divorcio"],
        "Administrativo": ["administrativo", "procedimiento administrativo", "autoridad"],
        "Fiscal": ["fiscal", "hacendario", "ingresos", "impuestos"],
        "Constitucional": ["constitucional", "amparo", "derechos humanos", "garantías"],
    }.items():
        if any(k in t for k in keywords):
            return materia
    return random.choice(list(PLANTILLAS_PREGUNTAS.keys()))


def generar_ejemplo(chunk_text: str, titulo_doc: str, fuente: str, entidad: str) -> dict:
    """Genera un ejemplo sintético a partir de un chunk real del corpus."""
    materia = detectar_materia_chunk(titulo_doc)

    # Tomar un fragmento significativo del chunk (100-300 chars)
    fragmento = chunk_text.strip()
    if len(fragmento) < 50:
        return None

    inicio = random.randint(0, max(0, len(fragmento) - 300))
    pasaje = fragmento[inicio:inicio + 250].strip()
    if len(pasaje) < 50:
        return None

    # Limpiar el pasaje
    pasaje = re.sub(r'\s+', ' ', pasaje).strip()
    if not pasaje.endswith('.') and not pasaje.endswith(','):
        pasaje += '...'

    # Generar pregunta
    plantilla = random.choice(PLANTILLAS_PREGUNTAS.get(materia, PLANTILLAS_PREGUNTAS["Civil"]))
    detalle = random.choice(DETALLES)
    pregunta = plantilla.format(detalle=detalle)

    # Generar respuesta anclada al pasaje
    inicio_resp = random.choice(RESPUESTA_INICIO)
    fin_resp = random.choice(RESPUESTA_FIN)

    # Formato: explicación + pasaje + cierre
    respuesta = f"{inicio_resp}\n\n{pasaje}\n\nAplica a tu situación específicamente. {fin_resp}"

    # Identificar la fuente de manera legible
    if fuente == "SJF":
        fuente_legible = f"Jurisprudencia del SJF: {titulo_doc[:60]}"
    elif fuente == "LeyesBiblio":
        fuente_legible = f"Ley federal: {titulo_doc[:60]}"
    elif fuente == "GacetaEstatal":
        fuente_legible = f"Ley de {entidad}: {titulo_doc[:60]}"
    elif fuente == "DOF":
        fuente_legible = f"DOF: {titulo_doc[:60]}"
    else:
        fuente_legible = titulo_doc[:60]

    return {
        "messages": [
            {"role": "system", "content": f"Eres AI Justicia, un asistente jurídico mexicano especializado en {materia}. Da orientación informativa con base en fuentes oficiales. No sustituyes la asesoría legal formal."},
            {"role": "user", "content": pregunta},
            {"role": "assistant", "content": respuesta},
        ],
        "metadata": {
            "materia": materia,
            "fuente": fuente,
            "entidad": entidad,
            "fuente_legible": fuente_legible,
            "titulo_documento": titulo_doc[:100],
            "pasaje_original": pasaje,
            "synthetic": True,
        },
    }


def generar_clasificacion_materia(chunk_text: str, titulo: str) -> dict | None:
    """Genera un ejemplo de clasificación de materia."""
    materia = detectar_materia_chunk(titulo)
    texto = re.sub(r'\s+', ' ', chunk_text[:400]).strip()
    if len(texto) < 50:
        return None
    return {
        "input": texto,
        "expected_materia": materia,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=15000, help="Número de ejemplos a generar")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Generando {args.count} ejemplos sintéticos desde el corpus...")
    print(f"Conectando a la DB...")

    # Seleccionar chunks aleatorios del corpus
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.texto, d.titulo, d.fuente, d.entidad, d.materia
                FROM documentos_chunks c
                JOIN documentos d ON d.id = c.documento_id
                WHERE c.texto IS NOT NULL
                  AND LENGTH(c.texto) > 200
                  AND d.derogado = FALSE
                ORDER BY RANDOM()
                LIMIT %s
            """, (args.count * 2,))
            chunks = cur.fetchall()

    print(f"Chunks seleccionados: {len(chunks)}")

    dataset = []
    materia_dataset = []

    for chunk_text, titulo, fuente, entidad, materia_db in chunks:
        if len(dataset) >= args.count:
            break

        ejemplo = generar_ejemplo(chunk_text, titulo, fuente, entidad or "Federal")
        if ejemplo:
            dataset.append(ejemplo)

        mat = generar_clasificacion_materia(chunk_text, titulo)
        if mat:
            materia_dataset.append(mat)

    # Guardar
    qa_path = OUTPUT_DIR / "synthetic_ift.jsonl"
    with open(qa_path, "w") as f:
        for item in dataset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    mat_path = OUTPUT_DIR / "synthetic_materia.jsonl"
    with open(mat_path, "w") as f:
        for item in materia_dataset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"\n=== Dataset generado ===")
    print(f"  IFT sintético: {len(dataset):>6} ejemplos → {qa_path}")
    print(f"  Materia eval:  {len(materia_dataset):>6} ejemplos → {mat_path}")

    # Distribución
    from collections import Counter
    mat_counts = Counter(d["metadata"]["materia"] for d in dataset)
    print(f"\n=== Distribución por materia ===")
    for m, n in mat_counts.most_common():
        print(f"  {m:<15} {n:>5}")

    fuente_counts = Counter(d["metadata"]["fuente"] for d in dataset)
    print(f"\n=== Distribución por fuente ===")
    for f, n in fuente_counts.most_common():
        print(f"  {f:<15} {n:>5}")

    print(f"\n=== Sample ===")
    s = dataset[0]
    print(f"Q: {s['messages'][1]['content'][:80]}")
    print(f"A: {s['messages'][2]['content'][:120]}")
    print(f"Source: {s['metadata']['fuente_legible']}")


if __name__ == "__main__":
    main()
