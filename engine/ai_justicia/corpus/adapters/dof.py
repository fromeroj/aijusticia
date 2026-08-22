"""Adapter DOF — Diario Oficial de la Federación (dof.gob.mx).

Publica leyes, reglamentos, decretos y avisos federales. Es la fuente primaria
de vigencia: una ley no entra en vigor hasta publicarse en el DOF.

Sin API/RSS — todo HTML. Estructura verificada en vivo:
  GET /index_111.php?year=Y&month=M&day=D → lista de notas del día (ISO-8859-1)
  GET /nota_detalle.php?codigo=X&fecha=DD/MM/YYYY → metadata + iframe con texto
  Texto born-digital: https://dof.gob.mx/{YYYY}/{ORG}/{ORG}_{DDMMYY}.html (UTF-8)
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Iterator

from ai_justicia.corpus.adapters.base import DocumentoMetadata
from ai_justicia.corpus.clean import limpiar_texto
from ai_justicia.corpus.http_client import EducationalHTTPClient
from ai_justicia.corpus.models import Fuente, Materia

logger = logging.getLogger(__name__)

BASE = "https://www.dof.gob.mx"
INDEX_URL = f"{BASE}/index_111.php"
NOTA_DETALLE_URL = f"{BASE}/nota_detalle.php"


class DOFAdapter:
    """Adapter para el Diario Oficial de la Federación."""

    fuente = Fuente.DOF

    def __init__(self):
        self.client = EducationalHTTPClient(verify_tls=False)  # DOF tiene cert SSL conflictivo

    def listar_desde(self, fecha_inicio: date | None = None, max_days: int = 7) -> Iterator[DocumentoMetadata]:
        """Lista notas del DOF desde fecha_inicio (hacia atrás, día por día).

        Por defecto, lista los últimos 7 días (suficiente para actualización diaria).
        """
        if fecha_inicio is None:
            fecha_inicio = date.today()

        for i in range(max_days):
            dia = fecha_inicio - timedelta(days=i)
            logger.info("DOF: listando %s", dia)
            yield from self._listar_dia(dia)

    def _listar_dia(self, dia: date) -> Iterator[DocumentoMetadata]:
        """Lista todas las notas publicadas en un día específico."""
        html = self.client.get_text(
            INDEX_URL,
            params={"year": dia.year, "month": dia.month, "day": dia.day},
            fallback_encoding="iso-8859-1",
        )

        # Extraer códigos de notas y dependencias del HTML
        # Patrón: nota_detalle.php?codigo=XXXXX
        codigos = re.findall(r"nota_detalle\.php\?codigo=(\d+)", html)
        # Extraer dependencias y títulos del HTML (entre tags)
        notas_raw = re.findall(
            r'nota_detalle\.php\?codigo=(\d+)[^>]*>([^<]*)',
            html,
        )

        vistos = set()
        for codigo, titulo_raw in notas_raw:
            if codigo in vistos:
                continue
            vistos.add(codigo)

            # Decodificar entidades HTML del título (&uacute; → ú)
            import html as _html
            titulo = _html.unescape(titulo_raw).strip()
            if not titulo or len(titulo) < 5:
                titulo = f"Nota DOF {codigo}"

            yield DocumentoMetadata(
                id_externo=codigo,
                fuente=Fuente.DOF,
                titulo=titulo[:300],
                fecha_publicacion=dia,
                url_origen=f"{NOTA_DETALLE_URL}?codigo={codigo}&fecha={dia.strftime('%d/%m/%Y')}",
                tipo="publicacion",
                extra={"fecha_dof": dia.isoformat(), "codigo": codigo},
            )

    def obtener_texto(self, metadata: DocumentoMetadata) -> str:
        """Obtiene el texto completo de una nota del DOF.

        El DOF requiere el header Referer para responder en nota_detalle.php
        (sin él devuelve cuerpo vacío). El contenido está directamente en el
        HTML de la página de detalle (class 'Texto').
        """
        dia = metadata.fecha_publicacion
        fecha_param = dia.strftime("%d/%m/%Y")
        referer = f"{INDEX_URL}?year={dia.year}&month={dia.month}&day={dia.day}"

        # GET nota_detalle con Referer (requerido por el DOF).
        # IMPORTANTE: el DOF exige la URL completa como string — si se usa
        # params={...} el encoding de la query difiere y devuelve cuerpo vacío.
        detalle_url = f"{NOTA_DETALLE_URL}?codigo={metadata.id_externo}&fecha={fecha_param}"
        detalle_html = self.client.get_text(
            detalle_url,
            fallback_encoding="iso-8859-1",
            referer=referer,
        )

        if not detalle_html or len(detalle_html) < 200:
            logger.warning("DOF: respuesta vacía para %s (¿falta referer?)", metadata.id_externo)
            return ""

        # Buscar iframe con texto born-digital (versión moderna del DOF)
        iframe_match = re.search(
            r'(https?://[^"\']*dof\.gob\.mx/\d{4}/[^"\']+\.html)',
            detalle_html,
            re.IGNORECASE,
        )
        if iframe_match:
            articulo_url = iframe_match.group(1)
            texto = self.client.get_text(articulo_url, fallback_encoding="utf-8", referer=referer)
            if texto and len(texto) > 100:
                return limpiar_texto(texto, es_html=True)

        # Contenido embebido en el HTML de detalle (caso común)
        return limpiar_texto(detalle_html, es_html=True)
