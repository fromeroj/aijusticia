"""Modelos de datos del corpus oficial mexicano.

Un `Documento` es la unidad atómica de conocimiento jurídico: un artículo, una
tesis, un acuerdo. Cada uno trae los metadatos que alimentan los filtros del
índice híbrido (fuente, jerarquía, vigencia, jurisdicción) y las claves de
verificación de citas (registro SJF, fecha de reforma, fecha de publicación).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class Fuente(str, Enum):
    """Fuentes oficiales del derecho mexicano (Capa 1 del motor)."""
    DOF = "DOF"                        # Diario Oficial de la Federación
    LEYES_BIBLIO = "LeyesBiblio"       # Legislación federal consolidada (diputados.gob.mx)
    SJF = "SJF"                        # Semanario Judicial de la Federación
    ORDEN_JURIDICO = "OrdenJuridico"   # ordenjuridico.gob.mx
    GACETA_ESTATAL = "GacetaEstatal"   # Gacetas de las 32 entidades


class Materia(str, Enum):
    """Materias jurídicas principales."""
    CONSTITUCIONAL = "Constitucional"
    CIVIL = "Civil"
    PENAL = "Penal"
    LABORAL = "Laboral"
    ADMINISTRATIVO = "Administrativo"
    FAMILIAR = "Familiar"
    MERCANTIL = "Mercantil"
    FISCAL = "Fiscal"
    AMPARO = "Amparo"
    ELECTORAL = "Electoral"
    AGRARIO = "Agrario"
    AMBIENTAL = "Ambiental"
    OTRA = "Otra"


# Pesos jerárquicos según el artículo 133 constitucional.
# Menor = mayor jerarquía. El reranker usa este valor para ordenar pasajes.
class Jerarquia:
    CONSTITUCION = 0
    TRATADO_INTERNACIONAL = 10
    LEY_FEDERAL = 20
    REGLAMENTO_FEDERAL = 30
    LEY_ESTATAL = 40
    REGLAMENTO_ESTATAL = 50
    NORMA_OFICIAL = 60
    JURISPRUDENCIA = 15          # vinculante (interrupción)
    TESIS_AISLADA = 25           # persuasiva
    ACUERDO = 35
    DOCTRINA = 70
    CIRCULAR = 45


@dataclass
class Documento:
    """Un documento del corpus oficial.

    Atributos de verificación de citas (Capa 3):
        registro_sjf: número de registro digital del SJF (jurisprudencia/tesis)
        fecha_reforma: fecha de reforma en LeyesBiblio (legislación)
        fecha_publicacion: fecha de publicación en el DOF
    """
    fuente: Fuente
    titulo: str
    texto: str
    materia: Materia | None = None
    entidad: str | None = None        # entidad federativa; None = federal
    tipo: str | None = None           # 'ley', 'reglamento', 'jurisprudencia', 'tesis_aislada', ...
    # Verificación de citas
    registro_sjf: str | None = None
    fecha_reforma: date | None = None
    fecha_publicacion: date | None = None
    fecha_vigencia: date | None = None
    derogado: bool = False
    jerarquia: int = Jerarquia.LEY_FEDERAL
    vinculante: bool = True
    # Metadatos extra
    url_origen: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def dedup_key(self) -> str:
        """Clave de idempotencia: identifica unívocamente al documento."""
        if self.registro_sjf:
            return self.registro_sjf
        pub = self.fecha_publicacion.isoformat() if self.fecha_publicacion else "sinf"
        return f"{self.titulo}_{pub}"

    @property
    def clave_cita(self) -> str:
        """Clave de cita legible para mostrar al usuario (y verificar)."""
        if self.registro_sjf:
            return f"SJF {self.registro_sjf}"
        if self.fecha_reforma:
            return f"{self.titulo} (ref. {self.fecha_reforma.isoformat()})"
        if self.fecha_publicacion:
            return f"{self.titulo} (DOF {self.fecha_publicacion.isoformat()})"
        return self.titulo


@dataclass
class Chunk:
    """Un fragmento (pasaje) de un documento, listo para indexar vectorialmente."""
    documento_id: int
    ordinal: int
    texto: str
    embedding: list[float] | None = None  # se rellena al indexar
