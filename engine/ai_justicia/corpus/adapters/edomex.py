"""Adapter Edomex — Leyes vigentes del Estado de México.

Sitio: legislacion.edomex.gob.mx
PDFs en patrón fijo: /sites/.../files/files/pdf/ley/vig/leyvig{NNN}.pdf

El sitio tiene 252 leyes vigentes con PDFs descargables. Como el sitio es
JS-renderado (Drupal), no podemos scrapear el listado con curl. Pero el patrón
de URL es secuencial (leyvig001 a leyvig268 aprox), así que podemos enumerar.

La página de cada ley (ej: /constitucion_local) muestra el nombre + link al PDF.
Para obtener los nombres, descargamos cada PDF y leemos el título del documento.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Iterator

from ai_justicia.corpus.adapters.base import DocumentoMetadata
from ai_justicia.corpus.clean import limpiar_texto
from ai_justicia.corpus.http_client import EducationalHTTPClient
from ai_justicia.corpus.models import Fuente

logger = logging.getLogger(__name__)

BASE = "https://legislacion.edomex.gob.mx"
PDF_BASE = f"{BASE}/sites/legislacion.edomex.gob.mx/files/files/pdf/ley/vig/"


class EdomexAdapter:
    """Adapter para leyes vigentes del Estado de México."""

    fuente = Fuente.GACETA_ESTATAL

    def __init__(self):
        self.client = EducationalHTTPClient(verify_tls=False)

    def listar_desde(self, fecha_inicio: date | None = None, max_days: int = 270) -> Iterator[DocumentoMetadata]:
        """Lista leyes vigentes del Edomex.

        El patrón es leyvig001.pdf a leyvig268.pdf (aprox). Enumeramos los
        números y verificamos cuáles existen (HTTP 200).
        """
        # Rango basado en lo que vimos en el sitio: 252 leyes
        for n in range(1, 271):
            pdf_file = f"leyvig{n:03d}.pdf"
            url = PDF_BASE + pdf_file

            # HEAD request para verificar existencia sin descargar
            resp = self.client.get(url, headers={"Range": "bytes=0-0"})
            if resp.status_code in (200, 206):
                yield DocumentoMetadata(
                    id_externo=f"edomex_leyvig{n:03d}",
                    fuente=Fuente.GACETA_ESTATAL,
                    titulo=f"Ley vigente del Estado de México #{n:03d}",  # se actualiza al extraer texto
                    fecha_publicacion=date.today(),
                    url_origen=url,
                    entidad="Estado de México",
                    tipo="ley",
                    extra={"n": n, "pdf_file": pdf_file},
                )

    def obtener_texto(self, metadata: DocumentoMetadata) -> str:
        """Descarga el PDF y extrae texto. Actualiza el título desde el contenido."""
        from io import BytesIO

        resp = self.client.get(metadata.url_origen)
        if resp.status_code != 200:
            return ""

        try:
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(resp.content))
            textos = []
            for page in reader.pages:
                t = page.extract_text() or ""
                textos.append(t)
            texto_completo = "\n\n".join(t for t in textos if t)

            # Extraer título del primer fragmento (usualmente está en la primera página)
            lineas = texto_completo.strip().split('\n')
            if lineas:
                # El título suele ser la primera línea significativa
                titulo_real = lineas[0].strip()[:100]
                if titulo_real and len(titulo_real) > 5:
                    metadata.titulo = titulo_real

            return limpiar_texto(texto_completo)
        except Exception as e:
            logger.warning("Edomex: error extrayendo PDF %s: %s", metadata.id_externo, e)
            return ""
