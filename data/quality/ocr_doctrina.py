#!/usr/bin/env python3
"""OCR de doctrina escaneada (SCJN cuadernillos + CDMX libros) via Apple Vision.

Para cada PDF: si ya tiene texto embebido suficiente (>2K chars), lo usa;
si no, OCR pagina por pagina (150 dpi, es-ES). Salida: JSONL por lote.
"""
import json
import sys
import time
from pathlib import Path

import fitz
from ocrmac.ocrmac import OCR

BATCHES = {
    "scjn": (Path("/tmp/ocr_batch/scjn"), "SCJN-Libros", 30),
    "cdmx": (Path("/tmp/ocr_batch/cdmx"), "CDMX-Doctrina", 1200),
}
OUT = Path.home() / "workspace/aijusticia/engine/data"


def ocr_pdf(path, max_pages=900):
    doc = fitz.open(str(path))
    # texto embebido?
    embebido = ""
    for i in range(min(5, len(doc))):
        embebido += doc[i].get_text()
        if len(embebido) > 4000:
            break
    if len(embebido) > 3000:
        return "\n".join(doc[i].get_text() for i in range(min(len(doc), max_pages))), len(doc), False
    textos = []
    for i in range(min(len(doc), max_pages)):
        pix = doc[i].get_pixmap(dpi=150)
        img = f"/tmp/_ocr_pg.png"
        pix.save(img)
        try:
            res = OCR(img, language_preference=["es-ES"]).recognize()
            textos.append("\n".join(r[0] for r in res))
        except Exception:
            pass
    return "\n".join(textos), len(doc), True


def main():
    batch = sys.argv[1]
    carpeta, fuente, _ = BATCHES[batch]
    files = sorted(carpeta.glob("*.pdf"))
    out_path = OUT / f"ocr_{batch}.jsonl"
    hechos = set()
    if out_path.exists():
        hechos = {json.loads(l)["archivo"] for l in open(out_path)}
    print(f"[{batch}] {len(files)} PDFs, {len(hechos)} ya hechos", flush=True)
    n = ok = ocrs = 0
    with open(out_path, "a") as out:
        for f in files:
            n += 1
            if f.name in hechos:
                continue
            try:
                t0 = time.time()
                texto, npag, uso_ocr = ocr_pdf(f)
                texto = texto.encode("utf-8", errors="ignore").decode("utf-8")
                if len(texto) > 800:
                    titulo = f.stem.replace("_", " ")
                    # quitar prefijo numerico
                    titulo = titulo.split(" ", 1)[1] if " " in titulo else titulo
                    out.write(json.dumps({
                        "titulo": titulo[:300], "fuente": fuente, "texto": texto,
                        "paginas": npag, "archivo": f.name, "ocr": uso_ocr,
                    }, ensure_ascii=False) + "\n")
                    ok += 1
                    if uso_ocr:
                        ocrs += 1
                    print(f"  [{n}/{len(files)}] {f.name[:45]} {npag}p {'OCR' if uso_ocr else 'txt'} {time.time()-t0:.0f}s", flush=True)
                else:
                    print(f"  [{n}/{len(files)}] {f.name[:45]} VACIO ({len(texto)})", flush=True)
            except Exception as e:
                print(f"  [{n}/{len(files)}] ERR {f.name[:40]}: {str(e)[:50]}", flush=True)
            if n % 50 == 0:
                out.flush()
    print(f"\nFINAL {batch}: ok={ok} (ocr={ocrs}) -> {out_path}", flush=True)


if __name__ == "__main__":
    main()
