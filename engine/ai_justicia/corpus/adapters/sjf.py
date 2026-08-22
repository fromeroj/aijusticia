"""Adapter SJF — Semanario Judicial de la Federación.

La mejor fuente para scrapear: API JSON limpia, sin autenticación, permitida
por robots.txt. Jurisprudencia y tesis de la SCJN.

Endpoints (verificados en vivo):
  GET  /services/sjftesismicroservice/api/public/tesis/{ius}  → tesis completa
  POST /services/sjftesismicroservice/api/public/tesis?page=0&size=200  → feed newest-first

GOTCHA CRÍTICO: las tesis `semanal=1` aparecen en búsqueda pero 404 en detalle
durante ~2-4 semanas (lag de promoción de dbSemanal a db principal).
Estrategia: descubrir vía search, guardar slim ahora, backfill semanal.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Iterator

from ai_justicia.corpus.adapters.base import DocumentoMetadata
from ai_justicia.corpus.clean import limpiar_texto
from ai_justicia.corpus.http_client import EducationalHTTPClient
from ai_justicia.corpus.models import Fuente, Materia

logger = logging.getLogger(__name__)

BASE = "https://sjf2.scjn.gob.mx"
REFERER = "https://sjf2.scjn.gob.mx/"
SEARCH_URL = f"{BASE}/services/sjftesismicroservice/api/public/tesis"
DETAIL_URL = f"{BASE}/services/sjftesismicroservice/api/public/tesis/{{ius}}"

# Mapeo de materias del SJF a nuestro enum
_MATERIAS_SJF = {
    "constitucional": Materia.CONSTITUCIONAL,
    "civil": Materia.CIVIL,
    "penal": Materia.PENAL,
    "laboral": Materia.LABORAL,
    "administrativa": Materia.ADMINISTRATIVO,
    "administrativo": Materia.ADMINISTRATIVO,
    "familiar": Materia.FAMILIAR,
    "mercantil": Materia.MERCANTIL,
    "fiscal": Materia.FISCAL,
    "amparo": Materia.AMPARO,
    "electoral": Materia.ELECTORAL,
    "agraria": Materia.AGRARIO,
    "ambiental": Materia.AMBIENTAL,
    "común": None,  # "Común" no es materia específica
    "comun": None,
}


class SJFAdapter:
    """Adapter para el Semanario Judicial de la Federación."""

    fuente = Fuente.SJF

    def __init__(self, page_size: int = 200):
        self.client = EducationalHTTPClient(referer=REFERER)
        self.page_size = page_size

    def listar_desde(
        self,
        fecha_inicio: date | None = None,
        max_pages: int = 50,
        start_page: int = 0,
    ) -> Iterator[DocumentoMetadata]:
        """Lista tesis nuevas desde fecha_inicio (newest-first del API).

        Camina páginas del feed hasta encontrar tesis con fecha <= fecha_inicio.
        Si fecha_inicio es None, lista desde start_page hasta max_pages.
        start_page permite saltar páginas ya descargadas (para backfill).
        """
        for page in range(start_page, start_page + max_pages):
            logger.info("SJF: listando página %d (desde %s)", page, fecha_inicio)
            body = {"criteria": {"searchTerms": [], "classifiers": []}}
            data = self.client.post_json(
                f"{SEARCH_URL}?page={page}&size={self.page_size}",
                json_body=body,
            )
            docs = data.get("documents", [])
            if not docs:
                logger.info("SJF: fin del feed en página %d (sin documentos)", page)
                return

            for doc in docs:
                meta = self._parsear_search_result(doc)
                if meta is None:
                    continue
                # Corte por fecha (el feed es newest-first)
                if fecha_inicio and meta.fecha_publicacion < fecha_inicio:
                    logger.info("SJF: alcanzada fecha watermark %s, parando", fecha_inicio)
                    return
                yield meta

    def obtener_texto(self, metadata: DocumentoMetadata) -> str:
        """Obtiene el texto completo de una tesis vía endpoint de detalle.

        Las tesis `semanal=1` pueden 404 (lag). En ese caso devolvemos el texto
        del search result si lo tenemos, o lanzamos.
        """
        ius = metadata.id_externo
        try:
            data = self.client.get_json(DETAIL_URL.format(ius=ius))
        except Exception as e:
            # 404 = lag semanal, no es un error fatal
            if metadata.extra.get("semanal") == 1:
                logger.info("SJF: tesis %s en lag semanal (404 esperado)", ius)
                # Devolver texto del slim si lo tenemos
                return metadata.extra.get("_texto_slim", "")
            raise

        # Componer texto: rubro + texto + precedentes
        partes = []
        rubro = data.get("rubro", "")
        texto = data.get("texto", "")
        precedentes = data.get("precedentes", "")

        if rubro:
            partes.append(limpiar_texto(rubro, es_html=True))
        if texto:
            partes.append(limpiar_texto(texto, es_html=True))
        if precedentes:
            partes.append("Precedentes: " + limpiar_texto(precedentes, es_html=True))

        return "\n\n".join(p for p in partes if p)

    def _parsear_search_result(self, doc: dict) -> DocumentoMetadata | None:
        """Convierte un resultado de búsqueda (slim) en DocumentoMetadata."""
        ius = str(doc.get("ius", "")).strip()
        if not ius:
            return None

        fecha = self._parsear_fecha(doc.get("fechaPublicacion"))
        # Tesis antiguas (pre-2007, 9a época y anteriores) pueden tener fechaPublicacion=None.
        # No las descartamos: son jurisprudencia histórica valiosa. Usamos fecha mínima.
        if fecha is None:
            fecha = date(1900, 1, 1)

        rubro = limpiar_texto(doc.get("rubro", "") or "", es_html=True) or f"Tesis {ius}"
        materias_str = doc.get("materias", "") or ""
        materia = self._detectar_materia(materias_str)

        # ta_tj: 0 = aislada, 1 = jurisprudencia (vinculante)
        ta_tj = doc.get("ta_tj", 0)
        vinculante = ta_tj == 1

        return DocumentoMetadata(
            id_externo=ius,
            fuente=Fuente.SJF,
            titulo=rubro[:300],  # rubros pueden ser largos
            fecha_publicacion=fecha,
            url_origen=f"{BASE}/detalle/tesis/{ius}",
            materia=materia,
            tipo="jurisprudencia" if vinculante else "tesis_aislada",
            vinculante=vinculante,
            registro_sjf=ius,
            extra={
                "semanal": doc.get("semanal", 0),
                "claveTesis": doc.get("claveTesis", ""),
                "localizacion": doc.get("localizacion", ""),
                "epoca": doc.get("epoca", ""),
                "instancia": doc.get("instancia", ""),
                "_texto_slim": limpiar_texto(doc.get("texto", "") or "", es_html=True),
            },
        )

    def _parsear_fecha(self, fecha_str: str | None) -> date | None:
        """Parsea fechaPublicacion (ISO 8601 o 'YYYY-MM-DD HH:MM:SS.0')."""
        if not fecha_str:
            return None
        try:
            # ISO 8601 con Z
            if "T" in fecha_str:
                return datetime.fromisoformat(fecha_str.replace("Z", "+00:00")).date()
            # Formato antiguo
            return datetime.strptime(fecha_str[:10], "%Y-%m-%d").date()
        except (ValueError, IndexError):
            return None

    def _detectar_materia(self, materias_str: str) -> Materia | None:
        """Detecta la primera materia conocida del string coma-separado."""
        for m in materias_str.lower().split(","):
            m = m.strip()
            if m in _MATERIAS_SJF:
                return _MATERIAS_SJF[m]
        return None
