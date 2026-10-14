"""Extrae e ingesta las leyes federales vigentes del LEYFED_zip.

El zip contiene 2,751 archivos (leyes, reformas, abrogadas, índices).
Este script extrae solo las 315 leyes vigentes de Legislación_Federal/,
les saca el texto con pypdf, e ingesta al corpus con chunking por artículo.

Uso:
    python scripts/ingest_leyfed.py                 # todas
    python scripts/ingest_leyfed.py --limite 10     # solo 10 (prueba)
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_justicia.corpus.models import Documento, Fuente, Jerarquia, Materia
from ai_justicia.corpus.store import batch_upsert_documentos, count_documentos, count_chunks

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("leyfed")

ZIP_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "LEYFED_zip_030326.zip"


def extraer_texto_pdf(pdf_bytes: bytes) -> str:
    """Extrae texto de un PDF desde bytes."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(pdf_bytes))
        textos = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                textos.append(t)
        return "\n\n".join(textos)
    except Exception as e:
        logger.warning("Error extrayendo PDF: %s", e)
        return ""


def detectar_materia_leyfed(nombre: str) -> Materia | None:
    """Detecta la materia por el nombre de la ley federal."""
    n = nombre.lower()
    if "constituc" in n:
        return Materia.CONSTITUCIONAL
    if "amparo" in n:
        return Materia.AMPARO
    if any(w in n for w in ["penal", "delito", "procedimientos penales"]):
        return Materia.PENAL
    if any(w in n for w in ["civil", "familia", "procedimientos civil"]):
        return Materia.CIVIL
    if any(w in n for w in ["trabajo", "laboral", "obrero"]):
        return Materia.LABORAL
    if any(w in n for w in ["comercio", "mercantil", "concursos", "quiebra"]):
        return Materia.MERCANTIL
    if any(w in n for w in ["fiscal", "impuesto", "ingresos", "contribución", "aduanera", "federación"]):
        return Materia.FISCAL
    if any(w in n for w in ["agraria", "agrar", "campo"]):
        return Materia.AGRARIO
    if any(w in n for w in ["electoral", "partidos", "voto"]):
        return Materia.ELECTORAL
    if any(w in n for w in ["ambiental", "medio ambiente", "agua", "biodiversidad"]):
        return Materia.AMBIENTAL
    if any(w in n for w in ["migración", "migrante", "refugiado", "inmigración"]):
        return Materia.OTRA
    return Materia.OTRA


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingesta leyes federales del LEYFED_zip")
    parser.add_argument("--limite", type=int, help="Máximo número de leyes")
    args = parser.parse_args()

    if not ZIP_PATH.exists():
        logger.error("No se encuentra %s", ZIP_PATH)
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("INGESTA LEYES FEDERALES VIGENTES desde LEYFED_zip")
    logger.info("=" * 60)

    zf = zipfile.ZipFile(str(ZIP_PATH))

    # Filtrar solo leyes vigentes en Legislación_Federal/
    leyes_vigentes = [
        info for info in zf.infolist()
        if ".pdf" in info.filename.lower()
        and "Legislaci" in info.filename
        and "Decreto" not in info.filename
        and "Abrogad" not in info.filename
        and "Indice" not in info.filename
        and "Sumarios" not in info.filename
        and info.file_size > 10000  # mínimo 10KB (filtrar basura)
    ]

    logger.info("Leyes vigentes encontradas: %d", len(leyes_vigentes))
    if args.limite:
        leyes_vigentes = leyes_vigentes[: args.limite]
        logger.info("Limitando a %d", len(leyes_vigentes))

    docs_a_ingestar: list[Documento] = []
    procesadas = 0
    fallidas = 0

    for i, info in enumerate(leyes_vigentes, 1):
        # Nombre legible de la ley (última parte del path, sin .pdf)
        nombre_raw = info.filename.split("/")[-1].replace(".pdf", "")
        # Limpiar nombre (puede tener encoding raro)
        nombre = nombre_raw.encode("latin-1", errors="replace").decode("utf-8", errors="replace")
        if not nombre or len(nombre) < 3:
            nombre = nombre_raw

        logger.info("[%d/%d] %s (%.1f MB)", i, len(leyes_vigentes), nombre[:60], info.file_size / 1e6)

        # Extraer PDF del zip
        try:
            pdf_bytes = zf.read(info.filename)
        except Exception as e:
            logger.warning("  ✗ Error leyendo del zip: %s", e)
            fallidas += 1
            continue

        # Extraer texto
        texto = extraer_texto_pdf(pdf_bytes)
        if len(texto) < 500:
            logger.warning("  ✗ Texto muy corto (%d chars)", len(texto))
            fallidas += 1
            continue

        logger.info("  ✓ %d chars extraídos", len(texto))

        # Detectar si es Constitución
        es_constitucion = "constituc" in nombre.lower()
        materia = detectar_materia_leyfed(nombre)

        doc = Documento(
            fuente=Fuente.LEYES_BIBLIO,
            titulo=nombre,
            texto=texto,
            materia=materia,
            entidad=None,  # federal
            tipo="constitucion" if es_constitucion else "ley",
            fecha_publicacion=date(2026, 3, 19),  # fecha de compilación del zip
            jerarquia=Jerarquia.CONSTITUCION if es_constitucion else Jerarquia.LEY_FEDERAL,
            vinculante=True,
            raw={"source": "LEYFED_zip_030326", "original_filename": info.filename},
        )
        docs_a_ingestar.append(doc)
        procesadas += 1

        # Flush cada 10 leyes (son documentos grandes)
        if len(docs_a_ingestar) >= 10:
            n = batch_upsert_documentos(docs_a_ingestar)
            logger.info("  → %d leyes ingresadas (DB total: %d docs)", n, count_documentos())
            docs_a_ingestar = []

    # Flush final
    if docs_a_ingestar:
        batch_upsert_documentos(docs_a_ingestar)

    logger.info("=" * 60)
    logger.info("COMPLETADO: %d leyes procesadas, %d fallidas", procesadas, fallidas)
    logger.info("Total en DB: %d documentos, %d chunks", count_documentos(), count_chunks())
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
