#!/usr/bin/env python3
"""Genera harness pairs mexicanos: (pasaje de ley del corpus) + pregunta →
respuesta anclada [n], minando las citas artículo→ley de las sentencias.

Salida: data/cpt/harness_mx.jsonl (formato {"text": ...} para CPT).
Corre en el server.
"""
import hashlib
import json
import re
import sys
from collections import defaultdict

sys.path.insert(0, "/opt/aijusticia/engine")
from ai_justicia.config import settings
import psycopg

OUT = "/opt/aijusticia/corpus_downloads/cpt_export/harness_mx.jsonl"

# citación: artículo N (bis/ter/...) de la Ley/Código X
CIT_RE = re.compile(
    r"(?:conforme al|conforme al|de conformidad con el|al|el|los)\s+"
    r"art[íi]culo\s+(\d+[°º]?(?:\s+(?:bis|ter|quater|quinquies))?(?:\s+[A-Z])?)[\.,]?\s+"
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
]


def extraer_pares(texto: str):
    """De un texto de sentencia, extrae (aserto, ley citada, artículo)."""
    oraciones = SENT_SPLIT.split(texto)
    pares = []
    for oracion in oraciones:
        if not (80 < len(oracion) < 600):
            continue
        for m in CIT_RE.finditer(oracion):
            art = m.group(1)
            ley = re.sub(r"\s+", " ", m.group(2)).strip().rstrip(",;")
            if len(ley) < 10:
                continue
            aserto = oracion.strip()
            pares.append((aserto, ley, art))
            break  # una cita por oración
    return pares


def buscar_en_corpus(cur, ley, articulo):
    """Busca el texto del artículo en el corpus (LeyesBiblio/OrdenJuridico)."""
    palabras = [w for w in re.findall(r"[a-záéíóúñü]{4,}", ley.lower())][:4]
    if not palabras:
        return None
    cur.execute("""
        SELECT c.texto FROM documentos_chunks c
        JOIN documentos d ON c.documento_id = d.id
        WHERE d.fuente IN ('LeyesBiblio', 'OrdenJuridico')
          AND d.titulo_search @@ plainto_tsquery('spanish', %s)
          AND c.texto_search @@ to_tsquery('spanish', %s)
        LIMIT 1
    """, (ley, f"articulo & " + re.sub(r"[^0-9]", "", articulo)))
    row = cur.fetchone()
    return row[0][:400] if row else None


def main():
    out = open(OUT, "w")
    total = 0
    con_grounding = 0
    vistos = set()

    with psycopg.connect(settings.psycopg_dsn) as conn:
        cur = conn.cursor(name="sentencias_harness")  # cursor de servidor
        cur.itersize = 1000
        cur.execute("""
            SELECT id, texto FROM documentos
            WHERE fuente IN ('SentenciasEdomex', 'SentenciasCDMX', 'SentenciasBC',
                             'SentenciasQro', 'SJF', 'GacetaEstatal')
              AND length(texto) > 500
            ORDER BY id
        """)
        qi = 0
        while True:
            rows = cur.fetchmany(500)
            if not rows:
                break
            for doc_id, texto in rows:
                qi += 1
                for aserto, ley, art in extraer_pares(texto):
                    excerpt = buscar_en_corpus(cur, ley, art)
                    q = PREGUNTAS[qi % len(PREGUNTAS)]
                    if excerpt:
                        text = (f"[1] {ley}, artículo {art}: {excerpt}\n\n"
                                f"Pregunta: {q}\n\n"
                                f"Respuesta: {aserto} Fundamento: [1].")
                        con_grounding += 1
                    else:
                        text = (f"Pregunta: {q}\n\n"
                                f"Respuesta: {aserto} (fundamento: artículo {art}, {ley}).")
                    h = hashlib.md5(text.encode()).hexdigest()[:12]
                    if h in vistos:
                        continue
                    vistos.add(h)
                    out.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")
                    total += 1
                if qi % 2000 == 0:
                    out.flush()
                    print(f"docs leídos: {qi} | pares: {total} (grounded: {con_grounding})",
                          flush=True)

    out.close()
    print(f"HARNESS MX: {total} pares (con grounding: {con_grounding}) → {OUT}", flush=True)


if __name__ == "__main__":
    main()
