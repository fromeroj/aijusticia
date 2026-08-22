"""Contrato base para adapters de fuentes del corpus.

Cada fuente oficial (DOF, LeyesBiblio, SJF, gacetas estatales) implementa esta
interfaz. El orquestador `ingest.py` llama a los adapters sin acoplarse a la
fuente específica.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterator, Protocol

from ai_justicia.corpus.models import Fuente, Materia


@dataclass
class DocumentoMetadata:
    """Metadata de un documento recuperable (antes de obtener el texto completo).

    Es lo que `listar_desde` devuelve: suficiente para identificar el documento
    y para que `obtener_texto` sepa cómo descargarlo.
    """
    id_externo: str             # identificador en la fuente (codigo DOF, ius SJF, etc.)
    fuente: Fuente
    titulo: str
    fecha_publicacion: date
    url_origen: str | None = None
    # Metadatos opcionales que vienen gratis en el listado (SJF los trae)
    materia: Materia | None = None
    entidad: str | None = None  # entidad federativa (estados)
    tipo: str | None = None     # 'ley' | 'jurisprudencia' | 'tesis_aislada' | 'acuerdo' | ...
    vinculante: bool = True
    registro_sjf: str | None = None
    fecha_reforma: date | None = None
    extra: dict = field(default_factory=dict)  # datos crudos adicionales


class CorpusAdapter(Protocol):
    """Contrato que toda fuente del corpus implementa."""

    @property
    def fuente(self) -> Fuente:
        """Identificador de la fuente."""
        ...

    def listar_desde(self, fecha_inicio: date | None = None) -> Iterator[DocumentoMetadata]:
        """Lista documentos desde fecha_inicio (inclusive).

        Si fecha_inicio es None, lista lo más reciente disponible.
        Devuelve un iterador (puede ser lazy para volúmenes grandes como SJF).
        """
        ...

    def obtener_texto(self, metadata: DocumentoMetadata) -> str:
        """Obtiene el texto completo (limpio) de un documento.

        Devuelve texto plano listo para chunking + embeddings.
        Lanza si el documento no está disponible (404, lag semanal, etc.).
        """
        ...


def metadata_a_documento(meta: DocumentoMetadata, texto: str):
    """Convierte metadata + texto en un Documento listo para persistir.

    Helper compartido por el orquestador. La jerarquía se deriva del tipo.
    """
    from ai_justicia.corpus.models import Documento, Jerarquia  # evitar import circular

    # Derivar jerarquía del tipo de documento
    tipo = meta.tipo or ""
    if "jurisprudencia" in tipo:
        jerarquia = Jerarquia.JURISPRUDENCIA
    elif "tesis_aislada" in tipo:
        jerarquia = Jerarquia.TESIS_AISLADA
    elif "constitucion" in tipo:
        jerarquia = Jerarquia.CONSTITUCION
    elif "reglamento" in tipo:
        jerarquia = Jerarquia.REGLAMENTO_FEDERAL if meta.fuente != Fuente.GACETA_ESTATAL else Jerarquia.REGLAMENTO_ESTATAL
    else:
        jerarquia = Jerarquia.LEY_FEDERAL if meta.fuente != Fuente.GACETA_ESTATAL else Jerarquia.LEY_ESTATAL

    return Documento(
        fuente=meta.fuente,
        titulo=meta.titulo,
        texto=texto,
        materia=meta.materia,
        entidad=meta.entidad,
        tipo=meta.tipo,
        registro_sjf=meta.registro_sjf,
        fecha_reforma=meta.fecha_reforma,
        fecha_publicacion=meta.fecha_publicacion,
        url_origen=meta.url_origen,
        vinculante=meta.vinculante,
        jerarquia=jerarquia,
        raw=meta.extra,
    )
