"""Limpieza de texto del corpus (patrones de SaulLM-7B).

Aplica las técnicas de limpieza que SaulLM validó para corpus legal:
- Normalización Unicode NFKC.
- Filtros de artefactos comunes en PDFs/scrapes (líneas de guiones, asteriscos,
  números de página, líneas rotas).
- Strip de HTML (SJF y DOF traen <p> tags).
- Dedup de espacios y líneas vacías.

La etapa de filtro de perplejidad (KenLM) se añadirá cuando tengamos un subconjunto
curado del corpus MX; por ahora los filtros de reglas cubren lo crítico.
"""

from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

# Artefactos que SaulLM encontró en sus top-10 10-gramas del corpus legal.
# Líneas repetidas de guiones, asteriscos, puntos, signos de igual.
_PATRON_ARTEFACTOS = re.compile(
    r"""
    [-=_*•·]{4,}            # líneas de guiones/asteriscos/puntos (4+)
    | \.{5,}                # secuencias largas de puntos
    | \*{5,}                # secuencias largas de asteriscos
    | P[aá]gina\s+\d+       # "Página 1", "Pagina 12"
    | ^\s*\d+\s*$           # líneas que son solo un número (número de página)
    """,
    re.VERBOSE | re.MULTILINE,
)

# Etiquetas HTML que el SJF y DOF traen embebidas
_TAG_HTML = re.compile(r"<[^>]+>")
_TAG_P = re.compile(r"</?p[^>]*>", re.IGNORECASE)
_TAG_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)

# Espacios/whitespace excesivos
_MULTI_ESPACIO = re.compile(r"[ \t]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")

# Líneas rotas: un punto final seguido de salto + minúscula (continuación de oración)
# Solo aplica para texto de leyes donde los artículos pueden partirse por ancho de página.
_LINEA_ROTA = re.compile(r"([.;:])\n([a-záéíóúñ])")


def limpiar_texto(texto: str, *, es_html: bool = False) -> str:
    """Pipeline de limpieza.

    Args:
        texto: texto crudo del scraper.
        es_html: si True, hace strip de tags HTML primero (SJF, DOF).

    Returns:
        Texto limpio, listo para chunking + embeddings.
    """
    if not texto:
        return ""

    # 1. Normalización Unicode NFKC (SaulLM paso 1)
    texto = unicodedata.normalize("NFKC", texto)

    # 2. Strip HTML si aplica
    if es_html:
        texto = _strip_html(texto)

    # 3. Quitar artefactos (líneas de guiones, números de página)
    texto = _PATRON_ARTEFACTOS.sub("", texto)

    # 4. Reparar líneas rotas (punto + newline + minúscula → punto + espacio)
    texto = _LINEA_ROTA.sub(r"\1 \2", texto)

    # 5. Normalizar espacios
    texto = _MULTI_ESPACIO.sub(" ", texto)
    texto = _MULTI_NEWLINE.sub("\n\n", texto)

    return texto.strip()


def _strip_html(texto: str) -> str:
    """Convierte HTML a texto plano preservando estructura de párrafos."""
    # Quitar <script> y <style> completos (JS/menús del DOF)
    texto = re.sub(r"<script[^>]*>.*?</script>", " ", texto, flags=re.DOTALL | re.IGNORECASE)
    texto = re.sub(r"<style[^>]*>.*?</style>", " ", texto, flags=re.DOTALL | re.IGNORECASE)
    texto = re.sub(r"<!--.*?-->", " ", texto, flags=re.DOTALL)
    # <br> → newline
    texto = _TAG_BR.sub("\n", texto)
    # </p> → doble newline (separador de párrafo)
    texto = _TAG_P.sub("\n\n", texto)
    # resto de tags → quitar
    texto = _TAG_HTML.sub("", texto)
    # Entidades HTML — usar html.unescape (cubre TODAS incl. &Aacute; &Uuml; &#225;)
    import html as _html
    texto = _html.unescape(texto)
    return texto


def detectar_no_espanol(texto: str, umbral: float = 0.15) -> bool:
    """Heurística rápida: ¿el texto parece no ser español?

    Cuenta caracteres no-ASCII que no son acentos españoles (áéíóúñü¿¡).
    Si supera el umbral, probablemente es ruido (inglés, OCR malo, encoding roto).
    """
    if not texto:
        return True
    # Tomar muestra de los primeros 1000 caracteres
    muestra = texto[:1000]
    permitidos = set("áéíóúñü¿¡ÁÉÍÓÚÑÜ")
    no_ascii = sum(1 for c in muestra if ord(c) > 127 and c not in permitidos)
    return (no_ascii / len(muestra)) > umbral
