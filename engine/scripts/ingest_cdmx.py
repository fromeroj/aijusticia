"""Descarga e ingesta las leyes de la CDMX desde aldf.gob.mx.

Lee la lista de leyes desde data/leyes_cdmx.json (extraída del sitio),
descarga cada PDF, extrae el texto con pypdf, e ingesta en el corpus.

Uso:
    python scripts/ingest_cdmx.py                  # todas
    python scripts/ingest_cdmx.py --limite 10      # solo 10 (prueba)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_justicia.corpus.adapters.base import metadata_a_documento
from ai_justicia.corpus.models import Documento, Fuente, Jerarquia, Materia
from ai_justicia.corpus.store import batch_upsert_documentos, count_documentos
from ai_justicia.corpus.watermark import guardar_watermark

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("cdmx")

BASE_URL = "http://www.aldf.gob.mx/"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PDF_DIR = DATA_DIR / "leyes_cdmx"


def descargar_pdf(url: str, filepath: Path) -> bool:
    """Descarga un PDF."""
    import requests
    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200 and len(resp.content) > 1000:
            filepath.write_bytes(resp.content)
            return True
    except Exception:
        pass
    return False


def extraer_texto_pdf(filepath: Path) -> str:
    """Extrae texto de un PDF con pypdf."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(filepath))
        textos = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                textos.append(t)
        return "\n\n".join(textos)
    except Exception:
        # Fallback: pdftotext si está instalado
        import subprocess
        try:
            result = subprocess.run(["pdftotext", str(filepath), "-"], capture_output=True, text=True, timeout=30)
            return result.stdout
        except Exception:
            return ""


def detectar_materia(nombre: str) -> Materia | None:
    """Detecta la materia por el nombre de la ley."""
    n = nombre.lower()
    if any(w in n for w in ["violencia", "mujeres", "familia", "convivencia"]):
        return Materia.FAMILIAR
    if any(w in n for w in ["penal", "delito", "reclusión", "ejecución"]):
        return Materia.PENAL
    if any(w in n for w in ["trabajo", "empleo", "laboral"]):
        return Materia.LABORAL
    if any(w in n for w in ["salud", "fumadores", "mental"]):
        return Materia.OTRA  # salud no es una materia jurídica clásica
    if any(w in n for w in ["civil", "propiedad", "condominio", "arrendamiento"]):
        return Materia.CIVIL
    if any(w in n for w in ["mercantil", "establecimiento"]):
        return Materia.MERCANTIL
    if any(w in n for w in ["transparencia", "datos"]):
        return Materia.ADMINISTRATIVO
    if any(w in n for w in ["ambiental", "cambió climático", "residuos", "animales"]):
        return Materia.AMBIENTAL
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingesta leyes de la CDMX")
    parser.add_argument("--limite", type=int, help="Máximo número de leyes")
    parser.add_argument("--solo-descargar", action="store_true", help="Solo descargar PDFs, no ingesta")
    args = parser.parse_args()

    # Cargar lista de leyes
    leyes = json.loads((DATA_DIR / "leyes_cdmx.json").read_text())
    if args.limite:
        leyes = leyes[:args.limite]

    logger.info("=" * 60)
    logger.info("INGESTA LEYES CDMX — %d leyes", len(leyes))
    logger.info("=" * 60)

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    docs_a_ingestar: list[Documento] = []
    descargadas = 0
    fallidas = 0

    for i, ley in enumerate(leyes, 1):
        pdf_file = ley["pdf"]
        pdf_path = PDF_DIR / pdf_file
        ley_name = ley["name"]
        url = ley["url"]

        # Descargar si no existe
        if not pdf_path.exists() or pdf_path.stat().st_size < 1000:
            logger.info("[%d/%d] Descargando: %s", i, len(leyes), ley_name[:50])
            ok = descargar_pdf(url, pdf_path)
            if not ok:
                logger.warning("  ✗ Falló descarga de %s", pdf_file)
                fallidas += 1
                continue
            time.sleep(0.5)  # educativo
        else:
            logger.info("[%d/%d] Ya descargado: %s", i, len(leyes), ley_name[:50])

        descargadas += 1

        if args.solo_descargar:
            continue

        # Extraer texto
        texto = extraer_texto_pdf(pdf_path)
        if len(texto) < 100:
            logger.warning("  ✗ Texto muy corto (%d chars) para %s", len(texto), pdf_file)
            continue

        # Crear Documento
        materia = detectar_materia(ley_name)
        doc = Documento(
            fuente=Fuente.GACETA_ESTATAL,
            titulo=ley_name,
            texto=texto,
            materia=materia,
            entidad="Ciudad de México",
            tipo="ley",
            fecha_publicacion=date(2024, 1, 1),  # fecha aproximada
            jerarquia=Jerarquia.LEY_ESTATAL,
            vinculante=True,
            url_origen=url,
            raw={"pdf_file": pdf_file, "source": "aldf.gob.mx"},
        )
        docs_a_ingestar.append(doc)

        # Flush cada 20 documentos
        if len(docs_a_ingestar) >= 20:
            n = batch_upsert_documentos(docs_a_ingestar)
            logger.info("  → %d leyes ingresadas (total DB: %d)", n, count_documentos())
            docs_a_ingestar = []

    # Flush final
    if docs_a_ingestar:
        batch_upsert_documentos(docs_a_ingestar)

    logger.info("=" * 60)
    logger.info("COMPLETADO: %d descargadas, %d fallidas, %d en DB total",
                descargadas, fallidas, count_documentos())
    logger.info("=" * 60)

    if not args.solo_descargar:
        guardar_watermark("GacetaEstatal_CDMX", date.today())


if __name__ == "__main__":
    main()
