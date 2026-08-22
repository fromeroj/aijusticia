"""Adapter Nuevo León — Leyes del H. Congreso de Nuevo León.

Sitio: hcnl.gob.mx/trabajo_legislativo/leyes/
Cada ley tiene su propia página con el texto HTML completo + PDFs descargables.
URLs: /trabajo_legislativo/leyes/leyes/{nombre_slug}/

Stack: Apache + PHP server-rendered. El HTML contiene el texto de la ley.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Iterator

from ai_justicia.corpus.adapters.base import DocumentoMetadata
from ai_justicia.corpus.clean import limpiar_texto
from ai_justicia.corpus.http_client import EducationalHTTPClient
from ai_justicia.corpus.models import Fuente

logger = logging.getLogger(__name__)

INDEX_URL = "https://www.hcnl.gob.mx/trabajo_legislativo/leyes/"


class NuevoLeonAdapter:
    """Adapter para leyes del H. Congreso de Nuevo León."""

    fuente = Fuente.GACETA_ESTATAL

    def __init__(self):
        self.client = EducationalHTTPClient(verify_tls=False)

    def listar_desde(self, fecha_inicio: date | None = None, max_days: int = 30) -> Iterator[DocumentoMetadata]:
        """Lista las leyes vigentes del Congreso de Nuevo León.

        Scrapea el listado principal y extrae el enlace a cada ley individual.
        """
        html = self.client.get_text(INDEX_URL, fallback_encoding="utf-8")

        # Extraer enlaces a leyes individuales (URLs completas o relativas)
        pattern = r'href="([^"]*leyes/leyes/[^"]+)"[^>]*>([^<]+)'
        matches = re.findall(pattern, html)

        vistos = set()
        for url_raw, titulo_raw in matches:
            url_raw = url_raw.strip()
            # Normalizar a URL completa
            if url_raw.startswith('/'):
                url = f"https://www.hcnl.gob.mx{url_raw}"
            else:
                url = url_raw

            if url in vistos:
                continue
            vistos.add(url)

            titulo = titulo_raw.strip()
            # Limpiar TEXTO/PDF del título
            titulo = re.sub(r'\s*(TEXTO|PDF)\s*$', '', titulo).strip()
            # Saltar enlaces de navegación
            if len(titulo) < 8 or titulo in ("REGLAMENTOS", "LEYES ABROGADAS", "LEYES"):
                continue

            yield DocumentoMetadata(
                id_externo=f"nl_{url.rstrip('/').split('/')[-1][:50]}",
                fuente=Fuente.GACETA_ESTATAL,
                titulo=titulo[:200],
                fecha_publicacion=date.today(),
                url_origen=url,
                entidad="Nuevo León",
                tipo="ley",
                extra={"slug": url.rstrip("/").split("/")[-1]},
            )

    def obtener_texto(self, metadata: DocumentoMetadata) -> str:
        """Obtiene el texto completo de la ley desde la página HTML."""
        html = self.client.get_text(metadata.url_origen, fallback_encoding="utf-8")

        # El texto de la ley está en el HTML (server-rendered)
        # Limpiar el HTML y extraer texto
        texto = limpiar_texto(html, es_html=True)

        # El HTML incluye CSS, navegación, etc. Filtrar: quedarnos con lo que
        # empiece con el título o "Artículo" y termine antes del footer
        # Buscar el inicio del contenido legal
        idx_art = texto.find("Artículo")
        if idx_art > 0:
            texto = texto[idx_art:]

        # Truncar basura del final (footer, navegación)
        for marker in ["\n\nIr al contenido", "\n\nSaltar al", "\n\nBuscar", "\n\nInicio\n"]:
            idx = texto.rfind(marker)
            if idx > 0 and idx > len(texto) * 0.5:
                texto = texto[:idx]

        return texto.strip()
