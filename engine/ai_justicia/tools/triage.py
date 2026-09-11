"""Triage jurídico — identifica dominio legal antes de buscar.

Paso 1: LLM identifica ley/institución/términos técnicos desde lenguaje ciudadano
Paso 2: FTS busca con los términos precisos identificados
Paso 3: Izel genera respuesta con los pasajes correctos

Sin esto: "cargo no autorizado" matchea NOM de tiempos compartidos (que repite
"consumidor" y "cobros" densamente) en vez de LFPC art. 56.
"""
from __future__ import annotations

import json
import logging

from ai_justicia.config import settings

logger = logging.getLogger(__name__)

PROMPT_TRIAGE = """Eres un bibliotecario jurídico experto en derecho mexicano. Dada la consulta de un ciudadano, identifica:

1. La LEY o CÓDIGO mexicano más probable que regula el tema
2. La INSTITUCIÓN o autoridad competente
3. Los TÉRMINOS JURÍDICOS técnicos que aparecen en esa ley (como los usaría un abogado)
4. Los ARTÍCULOS probables de esa ley

Consulta del ciudadano: "{consulta}"

Responde SOLO un JSON (sin texto adicional):
{{"ley": "nombre de la ley o código", "institucion": "autoridad competente", "materia": "área del derecho", "terminos": ["término técnico 1", "término 2", "..."], "articulos": ["56", "92"], "fuente_busqueda": "texto para buscar en la ley"}}

Si el tema no es claramente jurídico o no sabes, responde: {{"ley": "", "terminos": []}}
"""

IDENT_PROMPT = """Eres un bibliotecario jurídico. Dada esta consulta ciudadana, identifica la ley mexicana aplicable y los términos técnicos para buscarla.

Consulta: "{consulta}"

Responde SOLO JSON:
{{"ley": "nombre de la ley", "institucion": "CONDUSEF/PROFECO/SAT/etc", "terminos_busqueda": ["término 1 para FTS", "término 2"], "articulos": ["56"]}}
"""


def identificar_dominio(query: str) -> dict:
    """LLM rápido (sin thinking, max_tokens=200) identifica el dominio legal.

    Retorna: {ley, institucion, terminos_busqueda, articulos} o {} si falla.
    """
    from openai import OpenAI

    client = OpenAI(
        base_url=settings.lmstudio_base_url,
        api_key=settings.lmstudio_api_key,
        timeout=15.0,
    )
    try:
        resp = client.chat.completions.create(
            model=settings.lmstudio_llm_model,
            messages=[{
                "role": "user",
                "content": IDENT_PROMPT.format(consulta=query[:1000]),
            }],
            temperature=0.0,
            max_tokens=300,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        raw = resp.choices[0].message.content or ""
        # limpiar thinking si se cuela
        import re
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
        # extraer JSON
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            return json.loads(m.group())
        return {}
    except Exception as e:
        logger.warning("triage fallo: %s", str(e)[:200])
        return {}
