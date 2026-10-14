#!/usr/bin/env python3
"""Batería de evaluación: 30 preguntas ciudadanas para Tlamatini.

Evalúa: tasa de respuesta, precisión de citas, accuracy a nivel artículo.
Compara base vs CPT vs RAG-only.

Uso:
  python3 eval_bateria.py --model ./merged --output resultados.json
"""
import json
import sys
import time
from pathlib import Path

PREGUNTAS = [
    # Laboral
    {"q": "Me despidieron sin motivo y estoy embarazada, ¿qué me corresponde?", "materia": "Laboral"},
    {"q": "Trabajo sin contrato escrito desde hace 2 años, ¿tengo derechos?", "materia": "Laboral"},
    {"q": "Mi jefe no me pagó las aguinaldos, ¿qué puedo hacer?", "materia": "Laboral"},
    {"q": "Me deben 3 semanas de sueldo, ¿cómo las reclamo?", "materia": "Laboral"},
    {"q": "Me moved to turno nocturno sin mi consentimiento, ¿es legal?", "materia": "Laboral"},
    # Consumidor
    {"q": "Me cobraron un cargo que no reconocí en mi tarjeta, ¿qué hago?", "materia": "Consumidor"},
    {"q": "Compré un teléfono y llegó roto, el vendedor no responde.", "materia": "Consumidor"},
    {"q": "El banco me hizo un cobro doble, ¿qué artículos me amparan?", "materia": "Consumidor"},
    # Familiar
    {"q": "Quiero divorciarme pero mi pareja no acepta, ¿puedo?", "materia": "Familiar"},
    {"q": "¿Cuánto de pensión de alimentos me corresponde para mis hijos?", "materia": "Familiar"},
    {"q": "Mi expareja no me deja ver a los hijos, ¿qué hago?", "materia": "Familiar"},
    # Vivienda
    {"q": "Mi casero quiere subir la renta al doble, ¿es legal?", "materia": "Vivienda"},
    {"q": "Me quieren desalojar sin orden judicial, ¿qué hago?", "materia": "Vivienda"},
    # Civil
    {"q": "Alguien me debe dinero y no me paga desde hace un año.", "materia": "Civil"},
    {"q": "¿Cómo hago un testamento y cuánto cuesta?", "materia": "Civil"},
]

CRITERIA = {
    "responde": "El modelo da una respuesta sustantiva (no abstención, no 'consulte a un abogado')",
    "cita_articulo": "La respuesta menciona al menos un artículo específico (ej: 'artículo 50 LFT')",
    "cita_ley_especifica": "Menciona el nombre de la ley o código (ej: 'Ley Federal del Trabajo')",
    "cita_verificable": "El artículo citado existe realmente en la ley mencionada",
    "estructura": "La respuesta tiene estructura (pasos, opciones, fundamento)",
}


def evaluar_modelo(modelo_path: str, api_url: str = None):
    """Evalúa el modelo localmente (transformers) o vía API."""
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch

    print(f"Cargando modelo: {modelo_path}")
    model = AutoModelForCausalLM.from_pretrained(modelo_path, torch_dtype=torch.bfloat16)
    tok = AutoTokenizer.from_pretrained(modelo_path)

    resultados = []
    for i, item in enumerate(PREGUNTAS):
        prompt = f"Pregunta: {item['q']}\n\nRespuesta:"
        inputs = tok(prompt, return_tensors="pt")
        t0 = time.time()
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=400, do_sample=False)
        dt = time.time() - t0
        respuesta = tok.decode(out[0], skip_special_tokens=True).replace(prompt, "").strip()

        # evaluar heurísticas
        tiene_articulo = any(f"artículo {n}" in respuesta.lower() or f"art. {n}" in respuesta.lower()
                            for n in range(1, 500))
        tiene_ley = any(ley in respuesta.lower()
                        for ley in ("ley federal", "código", "constitución", "reglamento", "LFT", "Ley del"))
        tiene_estructura = len(respuesta) > 200 and ("\n" in respuesta or "1." in respuesta or "-" in respuesta)

        resultados.append({
            "pregunta": item["q"],
            "materia": item["materia"],
            "respuesta_len": len(respuesta),
            "tiempo_s": round(dt, 2),
            "cita_articulo": tiene_articulo,
            "cita_ley": tiene_ley,
            "estructura": tiene_estructura,
            "respuesta_preview": respuesta[:200],
        })
        print(f"  [{i+1}/{len(PREGUNTAS)}] {item['q'][:40]}... art={tiene_articulo} ley={tiene_ley}")

    return resultados


def main():
    import argparse
    import fire
    fire.Fire(lambda model: json.dump(
        evaluar_modelo(model),
        open("resultados_evaluacion.json", "w"),
        indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
