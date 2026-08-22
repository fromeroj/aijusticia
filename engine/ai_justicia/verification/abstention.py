"""Etapa 5 (final): umbral de abstención + clasificación A/B.

Si la proporción de oraciones con respaldo fuerte (cita resuelta + NLI entails)
cae debajo del umbral ABSTENTION_MIN_BACKED_RATIO, el sistema se abstiene.

La abstención se clasifica en dos casos:
  - Caso A (EVIDENCIA_INSUFICIENTE): derivar a abogado (comportamiento clásico).
  - Caso B (NORMA_FALTANTE): deferred — descargar la norma faltante y reintentar.
    El diagnóstico lo hace un LLM experto en `diagnostico.py`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from ai_justicia.config import settings

logger = logging.getLogger(__name__)


class TipoAbstencion(str, Enum):
    """Clasificación del motivo de abstención."""
    NINGUNA = "NINGUNA"                                   # no hubo abstención
    EVIDENCIA_INSUFICIENTE = "EVIDENCIA_INSUFICIENTE"     # Caso A: derivar a abogado
    NORMA_FALTANTE = "NORMA_FALTANTE"                     # Caso B: descargar + reintentar


@dataclass
class DecisionAbstencion:
    abstenido: bool
    ratio_sustento: float        # n_sustentadas / n_oraciones
    razon: str                   # explicación legible
    tipo: TipoAbstencion = TipoAbstencion.NINGUNA  # se rellena tras clasificación
    norma_faltante: str | None = None              # Caso B: norma identificada
    fuente_faltante: str | None = None             # Caso B: 'SJF' | 'LeyesBiblio' | 'DOF'
    id_externo: str | None = None                  # Caso B: registro/ley code
    explicacion: str | None = None                 # Caso B: explicación del diagnóstico


def decidir_abstencion(n_oraciones: int, n_sustentadas: int) -> DecisionAbstencion:
    """Decide si el sistema debe abstenerse de responder (sin clasificar A/B todavía).

    La clasificación A vs B se hace después con `clasificar_abstencion`.
    """
    if n_oraciones == 0:
        return DecisionAbstencion(
            abstenido=True,
            ratio_sustento=0.0,
            razon="La respuesta no contiene oraciones verificables.",
            tipo=TipoAbstencion.EVIDENCIA_INSUFICIENTE,  # default; el diagnóstico puede reclasificar
        )

    ratio = n_sustentadas / n_oraciones
    if ratio < settings.abstention_min_backed_ratio:
        return DecisionAbstencion(
            abstenido=True,
            ratio_sustento=ratio,
            razon=(
                f"Solo {n_sustentadas} de {n_oraciones} oraciones tienen respaldo "
                f"fuerte ({ratio:.0%}), por debajo del umbral "
                f"({settings.abstention_min_backed_ratio:.0%})."
            ),
            tipo=TipoAbstencion.EVIDENCIA_INSUFICIENTE,  # default; reclasificar tras diagnóstico
        )

    return DecisionAbstencion(
        abstenido=False,
        ratio_sustento=ratio,
        razon=f"{n_sustentadas} de {n_oraciones} oraciones respaldadas ({ratio:.0%}).",
        tipo=TipoAbstencion.NINGUNA,
    )


MENSAJE_ABSTENCION = (
    "No encuentro base suficiente en las fuentes oficiales para responder con "
    "la precisión que mereces. Te recomiendo validar tu caso con un abogado "
    "con cédula de nuestra red — la orientación inicial es gratuita y la "
    "validación cuesta desde $100 MXN, pagable en OXXO."
)

MENSAJE_DEFERIDO = (
    "Requiero actualizar la información legal para poder responder adecuadamente "
    "a tu consulta. Estoy descargando la norma pertinente ({norma}) desde fuentes "
    "oficiales y la procesaré en breve. Tu consulta quedó registrada con el "
    "identificador {job_id} — puedes consultar su estado cuando quieras."
)

