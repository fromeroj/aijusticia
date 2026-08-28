#!/usr/bin/env python3
"""Evalúa Thomson-1.0-Small (LM Studio) contra las 30 preguntas de prueba.

Sin RAG: capacidad intrínseca del modelo en derecho mexicano.
Salida: engine/data/thomson_test_results.json + resumen por consola.
"""
import json
import re
import time
import urllib.request

API = "http://localhost:1234/v1/chat/completions"
MODEL = "qwen3.8-27b-mlx"
OUT = "/Users/fabianromero/workspace/aijusticia/engine/data/qwen38_test_results.json"

SYSTEM = (
    "Eres un asistente de orientación jurídica para personas en México. "
    "Responde en español, de forma clara y directa, citando la ley mexicana aplicable "
    "(nombre y artículo cuando lo sepas). Si no estás seguro, dilo. Máximo 200 palabras."
)


def preguntar(q: str) -> dict:
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": q}],
        "temperature": 0.3,
        "max_tokens": 4000,
    }).encode()
    req = urllib.request.Request(API, data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=240) as r:
        d = json.load(r)
    contenido = d["choices"][0]["message"]["content"] or ""
    razonamiento = d["choices"][0]["message"].get("reasoning_content") or ""
    # algunos modelos qwen ponen <think> en content
    think = ""
    m = re.search(r"<think>(.*?)</think>", contenido, re.S)
    if m:
        think = m.group(1)
        contenido = contenido[m.end():].strip()
    return {
        "respuesta": contenido.strip(),
        "razonamiento": (razonamiento or think)[:2000],
        "tokens": d.get("usage", {}).get("completion_tokens", 0),
        "segs": round(time.time() - t0, 1),
    }


def main():
    qs = json.load(open("/Users/fabianromero/workspace/aijusticia/engine/data/questions_curated.json"))
    resultados = []
    for i, q in enumerate(qs, 1):
        try:
            r = preguntar(q["question"])
        except Exception as e:
            r = {"respuesta": f"ERROR: {e}", "razonamiento": "", "tokens": 0, "segs": 0}
        resultados.append({"n": i, **q, **r})
        marca = "✓" if r["respuesta"] and "ERROR" not in r["respuesta"] else "✗"
        print(f"[{i:02d}/30] {marca} {r['segs']}s {r['tokens']}t — {q['question'][:50]}", flush=True)
    with open(OUT, "w") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=1)
    # resumen
    ok = sum(1 for r in resultados if "ERROR" not in r["respuesta"])
    con_ley = sum(1 for r in resultados
                  if re.search(r"(art[ií]culo|art\.|ley|c[oó]digo|nmx|reglamento)", r["respuesta"], re.I))
    con_desc = sum(1 for r in resultados if re.search(r"no est[ooy]|no s[eé]|verifica|consulta", r["respuesta"], re.I))
    print(f"\nRESUMEN: {ok}/30 respondieron | {con_ley} citan ley | {con_desc} con descargos")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
