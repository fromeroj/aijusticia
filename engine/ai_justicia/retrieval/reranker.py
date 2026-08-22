"""Reranking jurídico (etapa 3 del pipeline).

Prioriza pasajes por relevancia jurídica real, no solo por similitud de texto.
Criterios (según el plan, sección 7.5 etapa 3):
  1. Jerarquía normativa (artículo 133 constitucional): Constitución > tratados > leyes > reglamentos
  2. Vigencia: vigente > derogado
  3. Precedente vinculante vs. persuasivo (jurisprudencia vs. tesis aislada)
  4. Coincidencia de jurisdicción (federal vs. estatal)

El score final combina la similitud (de la búsqueda híbrida) con estos bonos.
"""

from __future__ import annotations

import logging

from ai_justicia.retrieval.vector_index import Resultado

logger = logging.getLogger(__name__)

# Bonos (aditivos sobre el score normalizado [0,1])
BONO_JERARQUIA_BAJA = 0.15     # Constitución/jurisprudencia (jerarquia 0-15)
BONO_JERARQUIA_MEDIA = 0.07    # Leyes federales (jerarquia 16-40)
BONO_VINCULANTE = 0.10         # jurisprudencia obligatoria vs tesis persuasiva
BONO_VIGENTE = 0.05            # vigente sobre derogado
PENALIZACION_DEROGADO = -0.30  # texto derogado muy penalizado


def rerankear(resultados: list[Resultado], jurisdiccion: str | None = None) -> list[Resultado]:
    """Reordena resultados aplicando criterios jurídicos.

    Args:
        resultados: salida de la búsqueda híbrida.
        jurisdiccion: 'federal' o entidad (ej. 'CDMX'). Si coincide con la
            entidad del documento, bonifica (la ley local aplica ahí).
    """
    reranked = []
    for r in resultados:
        bonus = 0.0
        # Jerarquía
        if r.jerarquia <= 15:
            bonus += BONO_JERARQUIA_BAJA
        elif r.jerarquia <= 40:
            bonus += BONO_JERARQUIA_MEDIA
        # Vinculante vs persuasivo
        if r.vinculante:
            bonus += BONO_VINCULANTE
        # Vigencia
        if r.derogado:
            bonus += PENALIZACION_DEROGADO
        else:
            bonus += BONO_VIGENTE
        # Coincidencia de jurisdicción (estatal)
        if jurisdiccion and r.entidad and r.entidad.lower() == jurisdiccion.lower():
            bonus += 0.08

        nuevo = Resultado(**{**r.__dict__, "score": r.score + bonus})
        reranked.append(nuevo)

    reranked.sort(key=lambda x: x.score, reverse=True)
    logger.debug(
        "Reranking: top='%s' (score=%.3f, jer=%d, vinc=%s)",
        reranked[0].titulo[:50] if reranked else "—",
        reranked[0].score if reranked else 0,
        reranked[0].jerarquia if reranked else 0,
        reranked[0].vinculante if reranked else None,
    )
    return reranked
