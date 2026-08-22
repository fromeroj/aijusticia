"""Diagnóstico LLM: clasifica una abstención en Caso A o Caso B.

Tras la abstención (etapa 5), una llamada LLM adicional determina:
  - Caso A (EVIDENCIA_INSUFICIENTE): no hay una norma específica descargable que falte.
    Derivar a abogado.
  - Caso B (NORMA_FALTANTE): falta una norma/jurisprudencia específica que sí podemos
    descargar. Disparar ingesta on-demand + reintentar.

El LLM (Qwen3.6) entiende el dominio jurídico mexicano y puede inferir:
  - "El usuario pregunta sobre el art. 14 de la Ley Fintech pero solo tenemos
    tesis del SJF que la citan, no la ley misma" → Caso B, fuente=LeyesBiblio
  - "El usuario pregunta sobre su caso concreto de divorcio contencioso y no hay
    norma que resuelva directamente" → Caso A (derivemos a abogado)
"""

from __future__ import annotations

import json
import logging
import re

from ai_justicia.llm.client import get_llm_client
from ai_justicia.verification.abstention import DecisionAbstencion, TipoAbstencion

logger = logging.getLogger(__name__)


PROMPT_DIAGNOSTICO = """\
Eres un diagnóstico experto del sistema jurídico mexicano. El sistema se abstuvo \
de responder una consulta porque no encontró suficiente respaldo en las fuentes \
oficiales indexadas. Tu tarea es determinar POR QUÉ se abstuvo y si existe una \
norma o fuente específica que, de descargarse, permitiría responder.

CONSULTA DEL USUARIO:
{consulta}

PASAJES RECUPERADOS (titulos):
{pasajes}

ORACIONES NO SUSTENTADAS (el LLM las marcó [NO SUSTENTADO] por falta de fuente):
{no_sustentadas}

FUENTES DISPONIBLES PARA DESCARGA:
- SJF (Semanario Judicial de la Federación): tesis y jurisprudencia por número de registro digital
- LeyesBiblio (diputados.gob.mx): leyes federales consolidadas (Constitución, códigos, leyes)
- DOF (dof.gob.mx): publicaciones del Diario Oficial de la Federación

Analiza y devuelve SOLO un JSON con esta forma exacta (sin texto adicional):
{{
  "caso": "A" o "B",
  "norma_faltante": "nombre preciso de la ley/tésis/norma que falta" o null,
  "fuente": "SJF" o "LeyesBiblio" o "DOF" o null,
  "id_externo": "número de registro SJF o código de ley si lo conoces" o null,
  "explicacion": "una frase explicando tu diagnóstico"
}}

REGLAS:
- caso="B" SOLO si existe una norma específica y descargable cuya ausencia explica \
la abstención (ej. falta la Ley Fintech, falta el registro SJF 2024156789).
- caso="A" si la abstención se debe a la naturaleza del caso (requiere análisis de \
hechos, opinión profesional, o no hay norma que resuelva directamente).
- Si la consulta menciona una ley específica por nombre y no aparece en los pasajes \
recuperados, es casi seguro Caso B.
- No inventes números de registro SJF si no estás seguro; deja id_externo=null.

JSON:"""


def clasificar_abstencion(
    consulta: str,
    pasajes: list[str],
    no_sustentadas: list[str],
    decision: DecisionAbstencion,
) -> DecisionAbstencion:
    """Clasifica una abstención en Caso A o B usando el LLM.

    Modifica y devuelve la `decision` recibida con tipo/norma_faltante/etc rellenados.
    Si el diagnóstico falla, deja Caso A (safe default: derivar a abogado).
    """
    if not decision.abstenido:
        return decision

    prompt = PROMPT_DIAGNOSTICO.format(
        consulta=consulta[:500],
        pasajes="\n".join(f"- {p[:120]}" for p in pasajes[:8]) or "(ninguno)",
        no_sustentadas="\n".join(f"- {n[:150]}" for n in no_sustentadas[:6]) or "(ninguna)",
    )

    client = get_llm_client()
    try:
        resp = client.chat(
            [{"role": "user", "content": prompt}],
            max_tokens=8192, temperature=0.0,
        )
        diagnostico = _parsear_json(resp)
    except Exception as e:  # noqa: BLE001
        logger.warning("Diagnóstico falló (%s); default Caso A", e)
        diagnostico = {"caso": "A", "explicacion": "diagnóstico no disponible"}

    # Aplicar el diagnóstico a la decision
    if diagnostico.get("caso", "A") == "B":
        decision.tipo = TipoAbstencion.NORMA_FALTANTE
        decision.norma_faltante = diagnostico.get("norma_faltante")
        decision.fuente_faltante = diagnostico.get("fuente")
        decision.id_externo = diagnostico.get("id_externo")
        decision.explicacion = diagnostico.get("explicacion", "Norma faltante identificada.")
        logger.info(
            "Diagnóstico Caso B: falta %s (fuente=%s, id=%s)",
            decision.norma_faltante, decision.fuente_faltante, decision.id_externo,
        )
    else:
        decision.tipo = TipoAbstencion.EVIDENCIA_INSUFICIENTE
        decision.explicacion = diagnostico.get("explicacion", "Evidencia insuficiente.")
        logger.info("Diagnóstico Caso A: %s", decision.explicacion)

    return decision


def _parsear_json(texto: str) -> dict:
    """Extrae el JSON del diagnóstico (el LLM puede envolverlo en texto o ```json)."""
    # Quitar bloque ```json ... ```
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texto, re.DOTALL)
    if m:
        texto = m.group(1)
    else:
        # Buscar el primer { ... } balanceado
        m = re.search(r"\{.*\}", texto, re.DOTALL)
        if m:
            texto = m.group(0)

    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        logger.warning("JSON de diagnóstico inválido: %s", texto[:200])
        return {"caso": "A", "explicacion": "JSON de diagnóstico inválido"}
