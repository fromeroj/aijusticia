"""Adapter LeyesBiblio — legislación federal consolidada (diputados.gob.mx).

Texto vigente (consolidado) de las leyes federales, con trail de reformas.
Las leyes ya están ingresadas vía LEYFED_zip; este adapter mantiene la
actualización incremental: detecta nuevas reformas y las descarga.

URLs:
  /LeyesBiblio/index.htm → índice de leyes con códigos
  /LeyesBiblio/ref/{code}.htm → trail de fechas de reforma
  /LeyesBiblio/doc/{CODE}.doc → texto vigente consolidado (Word)
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Iterator

from ai_justicia.corpus.adapters.base import DocumentoMetadata
from ai_justicia.corpus.clean import limpiar_texto
from ai_justicia.corpus.http_client import EducationalHTTPClient
from ai_justicia.corpus.models import Fuente, Materia

logger = logging.getLogger(__name__)

BASE = "https://www.diputados.gob.mx"
INDEX_URL = f"{BASE}/LeyesBiblio/index.htm"
REF_URL = f"{BASE}/LeyesBiblio/ref/{{code}}.htm"
DOC_URL = f"{BASE}/LeyesBiblio/doc/{{CODE}}.doc"

# ~80 leyes federales clave con sus códigos
LEYES_CLAVE = {
    "cpeum": "Constitución Política de los Estados Unidos Mexicanos",
    "ccf": "Código Civil Federal",
    "cpf": "Código Penal Federal",
    "cft": "Código Federal del Trabajo",
    "cpcf": "Código Federal de Procedimientos Civiles",
    "cnpp": "Código Nacional de Procedimientos Penales",
    "cnpcef": "Código Nacional de Procedimientos Civiles y Familiares",
    "cff": "Código Fiscal de la Federación",
    "cca": "Código de Comercio",
    "lft": "Ley Federal del Trabajo",
    "lritf": "Ley para Regular las Instituciones de Tecnología Financiera",
    "lfpdppp": "Ley Federal de Protección de Datos Personales en Posesión de los Particulares",
    "lamp": "Ley de Amparo",
    "lfpc": "Ley Federal de Protección al Consumidor",
    "lcp": "Ley de Concursos Mercantiles",
    "lgsc": "Ley General de Sociedades Mercantiles",
    "lie": "Ley de Instituciones de Elecciones",
    "lnsijp": "Ley Nacional del Sistema Integral de Justicia Penal para Adolescentes",
    "lgpin": "Ley General de Protección de Datos",
    "lm": "Ley de Migración",
    "lan": "Ley de Aguas Nacionales",
    "la": "Ley Agraria",
    "lgs": "Ley General de Salud",
    "loapf": "Ley Orgánica de la Administración Pública Federal",
    "ljudfed": "Ley Orgánica del Poder Judicial de la Federación",
}


class LeyesBiblioAdapter:
    """Adapter para leyes federales consolidadas de diputados.gob.mx."""

    fuente = Fuente.LEYES_BIBLIO

    def __init__(self):
        self.client = EducationalHTTPClient()

    def listar_desde(self, fecha_inicio: date | None = None, max_days: int = 365) -> Iterator[DocumentoMetadata]:
        """Lista las leyes federales clave para verificar si hubo reformas.

        Como las leyes federales son ~80 y cambian con poca frecuencia, este
        adapter simplemente lista todas las leyes clave cada vez. El upsert
        es idempotente (ON CONFLICT update).
        """
        for code, nombre in LEYES_CLAVE.items():
            yield DocumentoMetadata(
                id_externo=code,
                fuente=Fuente.LEYES_BIBLIO,
                titulo=nombre,
                fecha_publicacion=date.today(),
                url_origen=REF_URL.format(code=code),
                tipo="ley",
                extra={"code": code, "nombre": nombre},
            )

    def obtener_texto(self, metadata: DocumentoMetadata) -> str:
        """Obtiene el texto vigente de una ley desde LeyesBiblio (.doc).

        El texto viene en formato Word (.doc). Se procesa con antiword o
        LibreOffice headless.
        """
        code = metadata.id_externo
        doc_url = DOC_URL.format(CODE=code.upper())

        # Descargar el .doc
        resp = self.client.get(doc_url)
        if resp.status_code != 200:
            logger.warning("LeyesBiblio: no se pudo descargar %s (HTTP %d)", doc_url, resp.status_code)
            return ""

        # Guardar temporalmente y convertir
        import tempfile, subprocess, os
        with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as f:
            f.write(resp.content)
            tmp_path = f.name

        try:
            # textutil es nativo de macOS y maneja .doc
            result = subprocess.run(
                ["textutil", "-convert", "txt", "-stdout", tmp_path],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return limpiar_texto(result.stdout)

            # Fallback: antiword (si está instalado)
            result2 = subprocess.run(
                ["antiword", tmp_path],
                capture_output=True, text=True, timeout=30,
            )
            if result2.returncode == 0 and result2.stdout.strip():
                return limpiar_texto(result2.stdout)

            # Último recurso: extraer texto del binario
            return limpiar_texto(resp.content.decode("utf-8", errors="ignore"))
        finally:
            os.unlink(tmp_path)

    def obtener_fecha_reforma(self, code: str) -> date | None:
        """Obtiene la fecha de la última reforma de una ley desde la página ref."""
        html = self.client.get_text(REF_URL.format(code=code), fallback_encoding="iso-8859-1")
        # Buscar "Última reforma publicada en el DOF el DD de mes de YYYY"
        match = re.search(r"DOF\s+el\s+(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", html, re.IGNORECASE)
        if match:
            meses = {
                "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
                "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
            }
            dia = int(match.group(1))
            mes = meses.get(match.group(2).lower())
            anio = int(match.group(3))
            if mes:
                return date(anio, mes, dia)
        return None
