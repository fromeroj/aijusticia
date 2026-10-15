#!/usr/bin/env python3
"""Refresca LeyesBiblio: descarga el texto CONSOLIDADO vigente de las leyes
federales clave (diputados.gob.mx) y lo canonicaliza.

Problema que arregla: los refreshes anteriores insertaron copias por fecha
('Ley Federal del Trabajo_2026-07-26') — varias con texto VACÍO porque la
extracción usaba textutil (solo macOS). Retrieval citaba ley vieja/vacía.

Este script:
  1. baja el .doc vigente de cada ley clave y extrae con antiword,
  2. upsertea UNA fila canónica con registro_sjf='LB:<code>' (dedup estable),
  3. borra las copias viejas/vacías (y sus chunks).

Uso (server): nohup .venv/bin/python scripts/refrescar_leyesbiblio.py > /tmp/lb.log 2>&1 &
"""
import sys
import time

sys.path.insert(0, "/opt/aijusticia/engine")

from datetime import date

from ai_justicia.corpus.adapters.leyes_biblio import LEYES_CLAVE, LeyesBiblioAdapter
from ai_justicia.config import settings
from ai_justicia.corpus.models import Documento, Fuente
from ai_justicia.corpus.store import batch_upsert_documentos
import psycopg

MIN_CHARS = 2_000


def descargar_y_extraer(adapter: LeyesBiblioAdapter, code: str) -> str:
    """Baja el .doc vigente y extrae con antiword (el adapter usa textutil,
    que solo existe en macOS, y revienta antes de llegar a antiword)."""
    from ai_justicia.corpus.clean import limpiar_texto

    url = f"https://www.diputados.gob.mx/LeyesBiblio/doc/{code.upper()}.doc"
    resp = adapter.client.get(url)
    if resp.status_code != 200:
        # fallback: muchas leyes solo están como PDF
        url_pdf = f"https://www.diputados.gob.mx/LeyesBiblio/pdf/{code.upper()}.pdf"
        resp = adapter.client.get(url_pdf)
        if resp.status_code != 200:
            return ""
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(resp.content)
            tmp = f.name
        try:
            r = subprocess.run(["pdftotext", "-q", tmp, "-"], capture_output=True, timeout=180)
            return r.stdout.decode("utf-8", errors="replace")
        finally:
            os.unlink(tmp)
    import subprocess
    import tempfile
    import os
    with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as f:
        f.write(resp.content)
        tmp = f.name
    try:
        r = subprocess.run(["antiword", tmp], capture_output=True, timeout=60)
        texto = r.stdout.decode("utf-8", errors="replace")
        if len(texto.strip()) < 500:
            r2 = subprocess.run(["strings", "-e", "l", tmp], capture_output=True, timeout=60)
            texto = r2.stdout.decode("utf-8", errors="replace")
        return limpiar_texto(texto) if texto else ""
    finally:
        os.unlink(tmp)


def main():
    adapter = LeyesBiblioAdapter()
    ok = vacios = errores = 0
    with psycopg.connect(settings.psycopg_dsn) as conn:
        cur = conn.cursor()
        for i, (code, nombre) in enumerate(LEYES_CLAVE.items(), 1):
            t0 = time.time()
            try:
                texto = descargar_y_extraer(adapter, code)
            except Exception as e:
                print(f"[{i:02d}] {code}: error extracción {str(e)[:80]}", flush=True)
                errores += 1
                continue
            if len(texto) < MIN_CHARS:
                print(f"[{i:02d}] {code}: texto insuficiente ({len(texto)} chars) — skip", flush=True)
                vacios += 1
                continue
            try:
                fecha_reforma = adapter.obtener_fecha_reforma(code)
            except Exception:
                fecha_reforma = None
            doc = Documento(
                fuente=Fuente.LEYES_BIBLIO,
                titulo=nombre,
                texto=texto,
                registro_sjf=f"LB:{code}",
                fecha_reforma=fecha_reforma,
                fecha_publicacion=date.today(),
                url_origen=f"https://www.diputados.gob.mx/LeyesBiblio/doc/{code.upper()}.doc",
                tipo="ley",
            )
            batch_upsert_documentos([doc])

            # id canónico + limpieza de duplicadas/vacíñas del mismo título
            cur.execute("""
                SELECT id FROM documentos
                WHERE fuente='LeyesBiblio' AND registro_sjf=%s
            """, (f"LB:{code}",))
            row = cur.fetchone()
            canon_id = row[0] if row else None
            cur.execute("""
                DELETE FROM documentos_chunks WHERE documento_id IN (
                    SELECT id FROM documentos
                    WHERE fuente='LeyesBiblio' AND titulo=%s AND id <> %s
                )
            """, (nombre, canon_id or -1))
            cur.execute("""
                DELETE FROM documentos
                WHERE fuente='LeyesBiblio' AND titulo=%s AND id <> %s
            """, (nombre, canon_id or -1))
            borradas = cur.rowcount
            conn.commit()
            ok += 1
            print(f"[{i:02d}] {code}: {len(texto):,} chars, reforma={fecha_reforma}, "
                  f"dup borradas={borradas} ({time.time()-t0:.0f}s)", flush=True)
        # resumen
        cur.execute("""
            SELECT count(*) FROM documentos WHERE fuente='LeyesBiblio'
        """)
        print(f"LISTO: ok={ok} vacíos={vacios} errores={errores} "
              f"total LeyesBiblio={cur.fetchone()[0]}", flush=True)


if __name__ == "__main__":
    main()
