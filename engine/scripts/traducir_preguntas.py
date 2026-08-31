#!/usr/bin/env python3
"""Traduce las preguntas EN → ES con Qwen3-30B-A3B (LM Studio, Mac).

Batches de 20 preguntas por llamada (el A3B es rápido), salida JSONL
{ids, traducciones} que se sube al server y hace UPDATE.
CORRER EN LA MAC con LM Studio vivo. Uso: python3 traducir_preguntas.py
"""
import json
import re
import time
import urllib.request

API = "http://localhost:1234/v1/chat/completions"
MODEL = "qwen3-30b-a3b-instruct-2507"
ENTRADA = "/Users/fabianromero/workspace/aijusticia/engine/data/preguntas_en_pendientes.json"
SALIDA = "/Users/fabianromero/workspace/aijusticia/engine/data/preguntas_traducidas.jsonl"
BATCH = 20

SYSTEM = (
    "Traduce preguntas legales del inglés al español latinoamericano neutro. "
    "Traducción LITERAL: conserva el significado jurídico exacto, no adaptes a leyes mexicanas. "
    "Devuelve SOLO un array JSON con las traducciones en el mismo orden, sin numeración ni comentarios."
)


def traducir_lote(lote):
    prompt = "Traduce estas preguntas a español. Devuelve un array JSON con las 20 traducciones en orden:\n\n"
    for i, p in enumerate(lote, 1):
        prompt += f"{i}. {p['texto']}\n"
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 3000,
    }).encode()
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.load(r)
    contenido = d["choices"][0]["message"]["content"] or ""
    # limpiar think si viene
    contenido = re.sub(r"<think>.*?</think>\s*", "", contenido, flags=re.S)
    # extraer array JSON
    m = re.search(r"\[.*\]", contenido, re.S)
    if not m:
        return None
    try:
        arr = json.loads(m.group(0))
        return arr if isinstance(arr, list) and len(arr) == len(lote) else None
    except json.JSONDecodeError:
        return None


def main():
    pendientes = json.load(open(ENTRADA))
    print(f"a traducir: {len(pendientes)}", flush=True)
    ok = fallidas = 0
    with open(SALIDA, "w") as out:
        for i in range(0, len(pendientes), BATCH):
            lote = pendientes[i:i + BATCH]
            for intento in range(2):
                arr = traducir_lote(lote)
                if arr:
                    break
                time.sleep(3)
            if arr:
                for p, t in zip(lote, arr):
                    if isinstance(t, str) and len(t.strip()) > 5:
                        out.write(json.dumps({"id": p["id"], "texto_es": t.strip()[:1000]},
                                             ensure_ascii=False) + "\n")
                        ok += 1
                    else:
                        fallidas += 1
            else:
                fallidas += len(lote)
            if (i // BATCH + 1) % 5 == 0:
                out.flush()
                print(f"  {i + len(lote)}/{len(pendientes)} ok={ok} fallidas={fallidas}", flush=True)
    print(f"FINAL: {ok} traducidas, {fallidas} fallidas -> {SALIDA}", flush=True)


if __name__ == "__main__":
    main()
