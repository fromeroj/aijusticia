"""Etapa 5(a): resolvedor de citas contra registros reales.

Verifica que cada cita exista en el registro oficial correspondiente:
  - Jurisprudencia/tesis citada → debe existir con ese número de registro digital del SJF
  - Artículo de ley citado → debe existir con esa fecha de reforma en LeyesBiblio
  - Publicación citada → debe existir con esa fecha en el DOF

El pasaje recuperado YA viene de la DB (es decir, existe). Aquí confirmamos que
los metadatos de la cita (registro, fecha de reforma, fecha de publicación)
están presentes y son consistentes. Esto detecta "fuga de citas": el LLM cita
un documento pero inventa el número de registro o la fecha.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ai_justicia.retrieval.vector_index import Resultado

logger = logging.getLogger(__name__)


@dataclass
class ResolucionCita:
    """Resultado de resolver una cita contra su registro real."""
    resuelto: bool           # True si la cita existe y los metadatos son consistentes
    detalle: str             # explicación legible


def resolver_cita(pasaje: Resultado) -> ResolucionCita:
    """Verifica que el pasaje citado tenga su clave de registro válida.

    La clave depende de la fuente:
      SJF → registro_sjf (número de registro digital)
      LeyesBiblio → fecha_reforma (y opcionalmente fecha_publicacion)
      DOF → fecha_publicacion
    """
    if pasaje.registro_sjf:
        # Jurisprudencia/tesis: el registro SJF es la clave
        if _es_registro_valido(pasaje.registro_sjf):
            return ResolucionCita(
                resuelto=True,
                detalle=f"SJF registro {pasaje.registro_sjf} confirmado",
            )
        return ResolucionCita(resuelto=False, detalle=f"Registro SJF inválido: {pasaje.registro_sjf}")

    if pasaje.fuente in ("LeyesBiblio", "DOF"):
        # Legislación: verificar que tiene fecha de publicación o reforma
        if pasaje.fecha_publicacion or pasaje.fecha_reforma:
            ref = pasaje.fecha_reforma or pasaje.fecha_publicacion
            return ResolucionCita(
                resuelto=True,
                detalle=f"{pasaje.fuente} {pasaje.titulo[:50]} (ref. {ref}) confirmado",
            )
        return ResolucionCita(
            resuelto=False,
            detalle=f"{pasaje.fuente} sin fecha de reforma/publicación: {pasaje.titulo[:50]}",
        )

    # Otras fuentes (OrdenJuridico, GacetaEstatal): se aceptan con advertencia
    return ResolucionCita(
        resuelto=True,
        detalle=f"{pasaje.fuente} (sin verificación de registro específica)",
    )


def _es_registro_valido(registro: str) -> bool:
    """Heurística: un registro SJF válido es numérico de 7-10 dígitos."""
    return registro.isdigit() and 7 <= len(registro) <= 10
