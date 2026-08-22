"""Etapa 4 del pipeline: generación anclada con atribución a nivel de oración.

El LLM genera la respuesta usando SOLO los pasajes recuperados, con una cita [n]
por oración. Este módulo parsea la salida para extraer, por cada oración:
  - el texto de la oración
  - el índice del pasaje citado (o None si marcó NO SUSTENTADO)

Salida consumida por la etapa 5 (verificación de citas).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from ai_justicia.llm.client import get_llm_client
from ai_justicia.llm.prompts import NO_SUSTENTADO, construir_messages
from ai_justicia.retrieval.vector_index import Resultado

logger = logging.getLogger(__name__)

# Patrón de cita: [n] o [n,m] o [NO SUSTENTADO]
_PATRON_CITA = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]|\[(NO SUSTENTADO)\]", re.IGNORECASE)
# Patrón de oración (hasta punto, seguido de cita opcional)
_SPLIT_ORACION = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Oracion:
    """Una oración de la respuesta generada, con su cita."""
    texto: str
    cita_idx: int | None          # índice (1-based) del pasaje citado, o None
    sustentado: bool              # False si marcó NO SUSTENTADO o no tiene cita


@dataclass
class RespuestaGenerada:
    """Salida completa de la etapa 4."""
    texto_completo: str           # el texto crudo del LLM
    oraciones: list[Oracion]      # oraciones parseadas con sus citas
    n_sustentadas: int            # cuántas tienen cita válida


def generar(consulta: str, pasajes: list[Resultado], nivel: str = "Nivel0") -> RespuestaGenerada:
    """Genera la respuesta anclada y la parsea en oraciones con citas.

    nivel: 'Nivel0' (ciudadano) usa prompt en lenguaje llano;
           'Nivel1'/'Nivel2' (abogado) usa prompt técnico sin disclaimers.
    """
    client = get_llm_client()
    messages = construir_messages(consulta, pasajes, nivel=nivel)
    logger.info("Generando respuesta anclada (%d pasajes, nivel=%s)", len(pasajes), nivel)

    # max_tokens muy generoso: el modelo soporta 262144 de contexto y es de
    # razonamiento, así que puede usar 10000-30000 tokens en reasoning_content
    # antes de producir la respuesta final. Optimizaremos después.
    texto = client.chat(messages, max_tokens=65536, temperature=0.1)
    oraciones = _parsear_oraciones(texto)
    n_sustentadas = sum(1 for o in oraciones if o.sustentado)

    logger.info(
        "Respuesta: %d oraciones, %d sustentadas (%.0f%%)",
        len(oraciones), n_sustentadas,
        (n_sustentadas / len(oraciones) * 100) if oraciones else 0,
    )
    return RespuestaGenerada(texto_completo=texto, oraciones=oraciones, n_sustentadas=n_sustentadas)


def _parsear_oraciones(texto: str) -> list[Oracion]:
    """Divide el texto en oraciones y extrae la cita de cada una.

    El LLM pone [n] o [NO SUSTENTADO] al final de cada oración.
    """
    # Quitar saltos de línea excesivos
    texto_limpio = re.sub(r"\n{3,}", "\n\n", texto.strip())

    oraciones: list[Oracion] = []
    # Partir por oración (punto/signo + espacio)
    partes = _SPLIT_ORACION.split(texto_limpio)
    for parte in partes:
        parte = parte.strip()
        if not parte or len(parte) < 5:
            continue

        # Buscar cita al final de la oración
        match = _PATRON_CITA.search(parte)
        if match:
            cita_str = match.group(0)
            texto_oracion = parte[: match.start()].strip().rstrip(",;:")
            if match.group(2):  # [NO SUSTENTADO]
                oraciones.append(Oracion(texto=texto_oracion, cita_idx=None, sustentado=False))
            else:
                # Tomar el primer índice si hay varios [1,2]
                primer_idx = int(re.search(r"\d+", match.group(1)).group())
                oraciones.append(Oracion(texto=texto_oracion, cita_idx=primer_idx, sustentado=True))
        else:
            # Oración sin cita: tratamos como no sustentada
            oraciones.append(Oracion(texto=parte, cita_idx=None, sustentado=False))

    return oraciones
