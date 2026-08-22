"""Adapter genérico para congresos estatales.

La mayoría de los congresos estatales siguen patrones similares:
- Una página de listado con enlaces a PDFs/DOCs
- Los documentos están en patrones predecibles

Este adapter descubre los PDFs/DOCs del portal, los descarga y extrae texto.
Es configurable por estado vía el catálogo ESTADOS.

Para estados con patrones únicos (SJF, DOF, etc.) hay adapters dedicados.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from io import BytesIO
from typing import Iterator
from urllib.parse import urljoin, unquote

from ai_justicia.corpus.adapters.base import DocumentoMetadata
from ai_justicia.corpus.clean import limpiar_texto
from ai_justicia.corpus.http_client import EducationalHTTPClient
from ai_justicia.corpus.models import Fuente

logger = logging.getLogger(__name__)

# Catálogo de URLs de los 28 estados restantes
# Cada estado tiene: URL del portal de leyes, verificar TLS
ESTADOS_URLS: dict[str, dict] = {
    "Puebla": {"url": "https://www.congresopuebla.gob.mx/legislacion/", "tls": False},
    "Veracruz": {"url": "https://www.legisver.gob.mx/", "tls": False},
    "Guanajuato": {"url": "https://www.congresogto.gob.mx/legislacion/", "tls": False},
    "Chiapas": {"url": "https://web.congresochiapas.gob.mx/trabajo-legislativo/legislacion-vigente", "tls": False},
    "Michoacán": {"url": "https://congresomich.site/normatividad-aplicable/", "tls": False},
    "Oaxaca": {"url": "https://www.congresooaxaca.gob.mx/", "tls": False},
    "Guerrero": {"url": "https://congresogro.gob.mx/inicio/", "tls": False},
    "Hidalgo": {"url": "https://www.congresohidalgo.gob.mx/", "tls": False},
    "San Luis Potosí": {"url": "http://congresosanluis.gob.mx/legislacion/leyes", "tls": False},
    "Sonora": {"url": "https://congresoson.gob.mx/leyes", "tls": False},
    "Coahuila": {"url": "https://www.congresocoahuila.gob.mx/portal/leyes-estatales-vigentes/", "tls": False},
    "Tamaulipas": {"url": "https://www.congresotamaulipas.gob.mx/", "tls": False},
    "Chihuahua": {"url": "https://www.congresochihuahua.gob.mx/", "tls": False},
    "Sinaloa": {"url": "https://www.congresosinaloa.gob.mx/", "tls": False},
    "Baja California": {"url": "https://www.congresobc.gob.mx/", "tls": False},
    "Tabasco": {"url": "https://congresotabasco.gob.mx/", "tls": False},
    "Querétaro": {"url": "http://legislaturaqueretaro.gob.mx/", "tls": False},
    "Morelos": {"url": "https://congresomorelos.gob.mx/documentos-legislativos/", "tls": False},
    "Quintana Roo": {"url": "https://www.congresoqroo.gob.mx/", "tls": False},
    "Durango": {"url": "https://congresodurango.gob.mx/", "tls": False},
    "Zacatecas": {"url": "https://www.congresozac.gob.mx/65/inicio", "tls": False},
    "Aguascalientes": {"url": "https://congresoags.gob.mx/", "tls": False},
    "Tlaxcala": {"url": "https://congresodetlaxcala.gob.mx/legislacion/", "tls": False},
    "Nayarit": {"url": "https://congresonayarit.gob.mx/", "tls": False},
    "Campeche": {"url": "https://www.congresocam.gob.mx/", "tls": False},
    "Colima": {"url": "https://congresocol.gob.mx/web/www/index.php", "tls": False},
    "Baja California Sur": {"url": "https://www.cbcs.gob.mx/index.php/trabajos-legislativos/leyes", "tls": False},
    "Yucatán": {"url": "https://www.congresoyucatan.gob.mx/", "tls": False},
}


class EstadoGenericoAdapter:
    """Adapter genérico para congresos estatales.

    Lee la URL del portal desde source_health en la DB (campo portal_url).
    Si no está en la DB, usa el catálogo ESTADOS_URLS como fallback.
    """

    fuente = Fuente.GACETA_ESTATAL

    def __init__(self, entidad: str):
        self.entidad = entidad

        # Intentar leer URL de la DB primero
        self.portal_url = self._leer_url_db(entidad)

        # Fallback al catálogo hardcodeado
        if not self.portal_url:
            config = ESTADOS_URLS.get(entidad)
            if config:
                self.portal_url = config["url"]
                self._verify_tls = config.get("tls", False)
            else:
                raise ValueError(f"No hay URL configurada para {entidad} (ni en DB ni en catálogo)")
        else:
            self._verify_tls = self._leer_tls_db(entidad)

        self.client = EducationalHTTPClient(verify_tls=self._verify_tls)

    def _leer_url_db(self, entidad: str) -> str | None:
        """Lee portal_url desde source_health."""
        import psycopg
        from ai_justicia.config import settings
        try:
            with psycopg.connect(settings.psycopg_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT portal_url FROM source_health WHERE fuente = %s AND entidad = %s",
                        ("GacetaEstatal", entidad),
                    )
                    row = cur.fetchone()
                    return row[0] if row else None
        except Exception:
            return None

    def _leer_tls_db(self, entidad: str) -> bool:
        """Lee portal_verify_tls desde source_health."""
        import psycopg
        from ai_justicia.config import settings
        try:
            with psycopg.connect(settings.psycopg_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT portal_verify_tls FROM source_health WHERE fuente = %s AND entidad = %s",
                        ("GacetaEstatal", entidad),
                    )
                    row = cur.fetchone()
                    return row[0] if row else False
        except Exception:
            return False

    def listar_desde(self, fecha_inicio: date | None = None, max_days: int = 1) -> Iterator[DocumentoMetadata]:
        """Descubre PDFs/DOCs en el portal del estado."""
        # Fetch del portal
        try:
            html = self.client.get_text(self.portal_url, fallback_encoding="utf-8")
        except Exception as e:
            logger.warning("%s: no se pudo cargar portal: %s", self.entidad, e)
            return

        # Buscar todos los enlaces a PDFs, DOCs y DOCXs
        base = self.portal_url
        pattern = r'href="([^"]+\.(?:pdf|doc|docx))"'
        raw_links = re.findall(pattern, html, re.IGNORECASE)

        # Normalizar URLs
        vistos = set()
        for href in raw_links:
            url = urljoin(base, href)

            # Fix: algunos estados tienen dominios viejos que ya no responden
            # Mapear dominios conocidos como muertos a los activos
            dead_domains = {
                'congresomich.gob.mx': 'congresomich.site',
            }
            for dead, alive in dead_domains.items():
                if dead in url:
                    url = url.replace(dead, alive)

            if url in vistos:
                continue
            vistos.add(url)

            # Extraer nombre del archivo
            filename = unquote(url.split("/")[-1])
            nombre = re.sub(r"\.(pdf|doc|docx)$", "", filename, flags=re.IGNORECASE).strip()
            # Limpiar fechas/sufijos del nombre
            nombre = re.sub(r"[-_]\d{6,8}.*$", "", nombre).strip()
            if len(nombre) < 3:
                nombre = filename

            yield DocumentoMetadata(
                id_externo=f"{self.entidad[:3].lower()}_{hash(url) % 100000}",
                fuente=Fuente.GACETA_ESTATAL,
                titulo=nombre[:200],
                fecha_publicacion=date.today(),
                url_origen=url,
                entidad=self.entidad,
                tipo="ley",
                extra={"url": url, "filename": filename},
            )

    def obtener_texto(self, metadata: DocumentoMetadata) -> str:
        """Descarga el documento (PDF/DOC/DOCX) y extrae texto."""
        resp = self.client.get(metadata.url_origen)
        if resp.status_code != 200 or len(resp.content) < 1000:
            return ""

        url_lower = metadata.url_origen.lower()

        if url_lower.endswith(".pdf"):
            try:
                from pypdf import PdfReader
                reader = PdfReader(BytesIO(resp.content))
                textos = [page.extract_text() or "" for page in reader.pages]
                texto = "\n\n".join(t for t in textos if t)
                return limpiar_texto(texto)
            except Exception as e:
                logger.warning("%s: error extrayendo PDF %s: %s", self.entidad, metadata.id_externo, e)
                return ""

        elif url_lower.endswith((".doc", ".docx")):
            # Guardar temporalmente y convertir con textutil (macOS nativo)
            import tempfile, subprocess, os
            ext = ".docx" if url_lower.endswith(".docx") else ".doc"
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(resp.content)
                tmp_path = f.name
            try:
                result = subprocess.run(
                    ["textutil", "-convert", "txt", "-stdout", tmp_path],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return limpiar_texto(result.stdout)
                return ""
            except Exception:
                return ""
            finally:
                os.unlink(tmp_path)

        return ""
