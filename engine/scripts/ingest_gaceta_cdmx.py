#!/usr/bin/env python3
"""Extrae texto de los PDFs de la Gaceta CDMX e ingiere en el corpus."""
import hashlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/opt/aijusticia/engine")
from ai_justicia.corpus.models import Documento, Fuente
from ai_justicia.corpus.store import batch_upsert_documentos

PDFS = Path("/opt/aijusticia/corpus_downloads/gaceta_cdmx_pdfs")
files = sorted(PDFS.glob("*.pdf"))
print(f"Gaceta CDMX PDFs: {len(files)}", flush=True)

total = 0
lote = []
vistos = set()
for pdf_path in files:
    try:
        r = subprocess.run(["pdftotext", "-q", str(pdf_path), "-"],
                           capture_output=True, timeout=180)
        texto = r.stdout.decode("utf-8", errors="replace")
        if len(texto.strip()) < 500:
            continue
        h = hashlib.md5(texto.encode()).hexdigest()[:16]
        if h in vistos:
            continue
        vistos.add(h)
        # extraer fecha del texto si se puede
        import re
        m = re.search(r"(?:Año|A\~no)\s+([IVXLC]+|A.D)\s*[·.·]\s*[Nn].*[·.·]\s*(\d{1,2}\s+de\s+\w+\s+de\s+\d{4})", texto[:2000])
        fecha_str = m.group(2) if m else ""
        lote.append(Documento(
            fuente=Fuente("GacetaCDMX"),
            titulo=f"Gaceta Oficial CDMX ({fecha_str} | {pdf_path.stem[:12]})"[:300],
            texto=texto,
            registro_sjf=f"GCDMX:{h}",
            url_origen=str(pdf_path),
            entidad="Ciudad de México",
        ))
        total += 1
        if total % 200 == 0:
            n = batch_upsert_documentos(lote)
            lote = []
            print(f"  {total} extraídos, {n} ingeridos", flush=True)
    except Exception as e:
        print(f"  {pdf_path.name}: {str(e)[:70]}", flush=True)

if lote:
    batch_upsert_documentos(lote)
print(f"GACETA CDMX: {total} documentos extraídos", flush=True)
