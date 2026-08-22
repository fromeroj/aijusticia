"""Adapter Jalisco — Leyes del Congreso del Estado de Jalisco.

Sitio: congresoweb.congresojal.gob.mx/bibliotecavirtual/busquedasleyes/Listado'2.cfm
El listado contiene enlaces directos a PDFs de códigos, leyes y reglamentos.
Patrón: ../legislacion/{tipo}/Documentos_PDF-{tipo}/{nombre}-{fecha}.pdf

Stack: ColdFusion (.cfm), server-rendered. Los PDFs son born-digital.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Iterator
from urllib.parse import unquote

from ai_justicia.corpus.adapters.base import DocumentoMetadata
from ai_justicia.corpus.clean import limpiar_texto
from ai_justicia.corpus.http_client import EducationalHTTPClient
from ai_justicia.corpus.models import Fuente

logger = logging.getLogger(__name__)

INDEX_URL = "https://congresoweb.congresojal.gob.mx/BibliotecaVirtual/busquedasleyes/Listado'2.cfm"


class JaliscoAdapter:
    """Adapter para leyes del Congreso del Estado de Jalisco."""

    fuente = Fuente.GACETA_ESTATAL

    def __init__(self):
        self.client = EducationalHTTPClient(verify_tls=False)

    def listar_desde(self, fecha_inicio: date | None = None, max_days: int = 30) -> Iterator[DocumentoMetadata]:
        """Lista las leyes vigentes de Jalisco desde el listado del Congreso.

        El listado contiene enlaces directos a PDFs de códigos, leyes y reglamentos.
        Filtramos versiones "anterior" y exposiciones de motivos.
        """
        html = self.client.get_text(INDEX_URL, fallback_encoding="utf-8")

        # Extraer todos los enlaces a PDFs de legislación
        pattern = r'href="([^"]*legislacion/[^"]*Documentos_PDF[^"]*\.pdf)"'
        matches = re.findall(pattern, html, re.IGNORECASE)

        # Normalizar URLs (pueden ser relativas)
        base = "https://congresoweb.congresojal.gob.mx/BibliotecaVirtual/"
        vistos = set()

        for href_raw in matches:
            # Resolver URL relativa
            if href_raw.startswith('http'):
                url = href_raw
            elif href_raw.startswith('../'):
                url = base + href_raw[3:]
            elif href_raw.startswith('/'):
                url = "https://congresoweb.congresojal.gob.mx" + href_raw
            else:
                url = base + href_raw

            # Decodificar para obtener el nombre
            url_decoded = unquote(url)
            filename = url_decoded.split('/')[-1].replace('.pdf', '').strip()

            # Filtar: no versiones anteriores ni exposiciones de motivos
            if 'anterior' in filename.lower() or 'exposici' in filename.lower():
                continue

            # Extraer nombre de la ley y fecha del sufijo (ej: "-240626" = 24 jun 2026)
            nombre_match = re.match(r'(.+?)-(\d{6})$', filename)
            if nombre_match:
                nombre = nombre_match.group(1).strip()
                fecha_code = nombre_match.group(2)
            else:
                nombre = filename
                fecha_code = ""

            if nombre in vistos or len(nombre) < 5:
                continue
            vistos.add(nombre)

            yield DocumentoMetadata(
                id_externo=f"jal_{nombre[:50]}",
                fuente=Fuente.GACETA_ESTATAL,
                titulo=nombre[:200],
                fecha_publicacion=date.today(),
                url_origen=url,
                entidad="Jalisco",
                tipo="codigo" if "código" in nombre.lower() or "codigo" in nombre.lower() else "ley",
                extra={"filename": filename, "fecha_code": fecha_code},
            )

    def obtener_texto(self, metadata: DocumentoMetadata) -> str:
        """Descarga el PDF y extrae texto."""
        from io import BytesIO

        resp = self.client.get(metadata.url_origen)
        if resp.status_code != 200:
            return ""

        try:
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(resp.content))
            textos = [page.extract_text() or "" for page in reader.pages]
            return limpiar_texto("\n\n".join(t for t in textos if t))
        except Exception as e:
            logger.warning("Jalisco: error extrayendo PDF %s: %s", metadata.id_externo, e)
            return ""
