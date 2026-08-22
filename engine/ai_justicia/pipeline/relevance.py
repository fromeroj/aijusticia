"""Filtro de relevancia LLM — etapa 3.5 del pipeline.

Después de recuperar y rerankear (etapa 3), el LLM verifica cuáles de los
pasajes recuperados son realmente relevantes para la pregunta del ciudadano.
Esto elimina el ruido de pasajes que coinciden en términos pero no abordan
el problema legal planteado.

Flujo:
  recuperar → rerankear → **filtrar_relevantes** → generar

Si el LLM marca todos como irrelevantes, se devuelve lista vacía para que
el pipeline intente reformular o abstenerse correctamente.
"""
from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from ai_justicia.config import settings

if TYPE_CHECKING:
    from ai_justicia.retrieval.vector_index import Resultado

logger = logging.getLogger(__name__)

PROMPT_FILTRO = """Eres un filtro de relevancia jurídica. Te daré una pregunta de un ciudadano y varios pasajes legales recuperados de un corpus. Tu trabajo es identificar cuáles pasajes son RELEVANTES para responder la pregunta.

Un pasaje es relevante si:
- Contiene una norma, artículo o criterio que aborda directamente el problema legal planteado.
- Define un concepto clave para entender la situación del ciudadano.
- Establece un procedimiento, derecho u obligación aplicable.

Un pasaje NO es relevante si:
- Es un manual administrativo, tabla contable o índice.
- Trata de un tema distinto aunque comparta palabras (ej: "pago" en contabilidad vs "pago de salario" en derecho laboral).
- Es demasiado genérico o no aporta información específica.
{contexto_bloque}
Pregunta del ciudadano: {consulta}

Pasajes:
{pasajes_texto}

Devuelve SOLO un JSON: {{"relevantes": [1, 3, 5]}}
Donde los números son los índices de los pasajes relevantes (1-based).
Si ninguno es relevante, devuelve: {{"relevantes": []}}"""


def filtrar_relevantes(
    consulta: str,
    pasajes: list["Resultado"],
    contexto_conversacion: str | None = None,
) -> list["Resultado"]:
    """Filtra pasajes usando el LLM para verificar relevancia.

    Args:
        consulta: Pregunta del ciudadano (idealmente ya contextualizada).
        pasajes: Lista de pasajes recuperados (post-reranking).
        contexto_conversacion: Tema del caso en curso (primera pregunta del
            usuario). Permite juzgar relevancia relativa a la conversación,
            no solo a la pregunta aislada.

    Returns:
        Sublista de pasajes que el LLM considera relevantes.
        Si el LLM no responde o falla, devuelve los pasajes originales
        (fail-open: mejor responder con algo que abstenerse por error técnico).
    """
    if not pasajes:
        return pasajes

    # Construir texto de pasajes
    pasajes_texto = "\n\n".join(
        f"[{i+1}] ({p.fuente} / {p.titulo[:60]}) {p.texto[:400]}"
        for i, p in enumerate(pasajes)
    )

    # Bloque de contexto conversacional (solo si hay conversación en curso)
    if contexto_conversacion:
        contexto_bloque = (
            f"\nContexto de la conversación en curso: {contexto_conversacion}\n"
            "Un pasaje es relevante si aborda el problema legal de ESTA conversación, "
            "aunque la pregunta actual solo lo mencione de forma indirecta.\n"
        )
    else:
        contexto_bloque = ""

    prompt = PROMPT_FILTRO.format(
        consulta=consulta[:300],
        pasajes_texto=pasajes_texto,
        contexto_bloque=contexto_bloque,
    )

    try:
        from ai_justicia.llm.client import get_llm_client

        client = get_llm_client()
        response = client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=256,
        )

        # Parsear JSON de respuesta
        response = response.strip()
        # Quitar markdown code fences
        response = re.sub(r"^```(?:json)?\s*", "", response)
        response = re.sub(r"\s*```$", "", response).strip()

        # Extraer JSON balanceado
        for start in range(len(response)):
            if response[start] == "{":
                depth = 0
                in_str = False
                escape = False
                for end in range(start, len(response)):
                    ch = response[end]
                    if escape:
                        escape = False
                        continue
                    if ch == "\\":
                        escape = True
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
                            try:
                                result = json.loads(response[start : end + 1])
                                relevantes = result.get("relevantes", [])
                                # Convertir a 0-based indices
                                idx_set = {int(r) - 1 for r in relevantes if isinstance(r, (int, str)) and str(r).isdigit()}
                                filtrados = [p for i, p in enumerate(pasajes) if i in idx_set]

                                logger.info(
                                    "Filtro relevancia: %d/%d pasajes relevantes",
                                    len(filtrados), len(pasajes),
                                )
                                return filtrados if filtrados else pasajes  # fail-open if all filtered
                            except (json.JSONDecodeError, ValueError):
                                break
                break

        # Si no se pudo parsear, devolver originales
        logger.warning("Filtro relevancia: no se pudo parsear respuesta, devolviendo todos")
        return pasajes

    except Exception as e:
        logger.warning("Filtro relevancia: error (%s), devolviendo todos", str(e)[:80])
        return pasajes
