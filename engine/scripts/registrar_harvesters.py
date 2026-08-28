#!/usr/bin/env python3
"""Registra/actualiza todos los harvesters en harvest_scripts (DB) con su estado actual.

Lee el código de engine/scripts/, captura watermarks reales de los archivos de
estado en el server (o del corpus_downloads) y hace UPSERT por (fuente, nombre).
Correr desde el server: cd /opt/aijusticia/engine && .venv/bin/python scripts/registrar_harvesters.py
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

ROOT = Path("/opt/aijusticia")
SCRIPTS = ROOT / "engine/scripts"
DL = ROOT / "corpus_downloads"

# (fuente, script, descripcion, metodo, origen, ejecucion, diferencial, frecuencia, completa, estado_fn)
REGISTRO = [
    ("DOF", "dof_backfill99b.py",
     "Diario Oficial de la Federación 1999-2021 (notas individuales por día)",
     "scraping-http", "https://www.dof.gob.mx/index_111.php", "server-tmux",
     "Watermark por fecha: adapter.listar_desde(fecha_inicio=hoy). Diario hacia atrás; histórico 1999-2021 una sola vez",
     "diaria", False, None),
    ("SIVEPJ", "harvest_sivepj2.py",
     "Sentencias TSJCDMX — universo completo: 19 materias × juzgados × 8 años × 4 trimestres",
     "scraping-playwright", "http://sivepj.poderjudicialcdmx.gob.mx:819/consulta/", "mac-local",
     "Universo agotado. Incremental: re-query (materia × juzgado × año actual × trimestres recientes); PDFs vía URLs firmadas de gestordocumental",
     "trimestral", True, lambda: {"combos": 4512, "sentencias": 28146, "vacios_juzgados": 212}),
    ("SentenciasEdomex", "harvest_edomex.py",
     "Sentencias PJEdomex vía API elástica (backgestiondocumental) + PDFs directos de electronico.pjedomex.gob.mx",
     "api-rest", "https://backgestiondocumental.pjedomex.gob.mx/files/search/elastic", "server-tmux",
     "fase1 re-query year=años recientes; fase2 usa estado.json (PDFs ya bajados). Slices materia×año, sub-rebanado trimestral si >10K",
     "mensual", False, lambda: {"manifest": sum(1 for _ in open(DL / "edomex/manifest.jsonl"))}),
    ("BJV", "harvest_bjv.py",
     "Biblioteca Jurídica Virtual IIJ-UNAM: 5,680 libros/tesis vía OAI-PMH + bitstreams",
     "oai-pmh", "http://ru.juridicas.unam.mx/oai/request", "server-tmux",
     "OAI soporta from=YYYY-MM-DD en ListRecords: re-cosechar solo records con datestamp > última corrida",
     "mensual", False, lambda: {"manifest": sum(1 for _ in open(DL / "bjv/manifest.jsonl")), "descargados": len(json.loads((DL / "bjv/estado.json").read_text()))}),
    ("GacetaCDMX", "download_gaceta_cdmx.py",
     "Gaceta Oficial CDMX/DF histórica (2014-2026) vía Wayback Machine CDX",
     "wayback", "https://web.archive.org/cdx/ (portal_old/uploads/gacetas)", "mac-local",
     "Universo agotado. Incremental: re-query CDX con from=<última fecha>; los PDFs nuevos también aparecen en CDX",
     "mensual", True, lambda: {"gacetas": 2374, "tokens_est": 143_000_000}),
    ("LeyesBiblio", "download_reglamentos.py",
     "Reglamentos/manuales/estatutos federales (diputados.gob.mx, WAF → Playwright)",
     "scraping-playwright", "https://www.diputados.gob.mx/LeyesBiblio/", "mac-local",
     "Comparar listing hash por sección; re-descargar solo PDFs con URL nueva",
     "trimestral", False, None),
    ("GacetaEstatal-CDMX", "download_cdmx_leyes.py",
     "Leyes consolidadas CDMX (Consejería Jurídica) — geo-bloqueado, corre en Mac",
     "scraping-http", "https://data.consejeria.cdmx.gob.mx/index.php/leyes", "mac-geo-bloqueo",
     "Re-descargar listado de secciones; el nombre de archivo codifica versión (ej _5.9.pdf): descargar solo versiones nuevas",
     "mensual", False, None),
    ("GacetaEstatal-Puebla", "download_estados_criticos.py",
     "Leyes Puebla (docman) + Guerrero (PHP) vía Playwright (Cloudflare en Puebla)",
     "scraping-playwright", "https://www.congresopuebla.gob.mx + congresogro.gob.mx", "mac-local",
     "Los gids de docman cambian al reformar: re-listar categoría y comparar gids conocidos",
     "trimestral", False, None),
    ("GacetaEstatal-Veracruz", "download_veracruz.py",
     "Leyes consolidadas Veracruz (SEGOB marco jurídico, pdf_ult/N.pdf con fecha de reforma)",
     "scraping-http", "https://www.segobver.gob.mx/juridico/marco1.php", "mac-geo-bloqueo",
     "La tabla trae 'Última Reforma DD/MM/YYYY': re-scrapear y descargar solo N con fecha > watermark",
     "mensual", False, None),
    ("JustiaEstatal", "download_justia.py",
     "Leyes consolidadas de estados débiles vía Justia México (PDFs de docs.mexico.justia.com)",
     "scraping-playwright", "https://mexico.justia.com/estatales/", "mac-local",
     "Listado Cloudflare-protegido (irregular); PDFs directos sin bloqueo. Re-listar por estado y descargar slugs nuevos",
     "trimestral", False, None),
    ("CDMX-Doctrina", "ocr_doctrina.py",
     "OCR con Apple Vision de doctrina escaneada (CDMX libros + SCJN cuadernillos)",
     "ocr", "local:/tmp/ocr_batch (fuente: juristeca CDMX + scjn.gob.mx/publicaciones)", "mac-local",
     "Solo para nuevo material escaneado; los ya procesados quedan en ocr_*.jsonl",
     "on-demand", False, None),
    ("LawInstruct-SFT", "limpiar_instructivos.py",
     "Datasets instructivos EN (razonamiento jurídico, NO leyes) para SFT — limpiados",
     "api-rest", "huggingface.co/datasets/lawinstruct/lawinstruct", "server-tmux",
     "Estático (SFT). Solo actualizar si sale nueva versión del dataset",
     "anual", True, lambda: {"registros": 269577, "datasets": 10}),

    # ── Sentencias estatales ────────────────────────────────────────────
    ("SentenciasJalisco", "harvest_jalisco.py",
     "84,371 sentencias STJ Jalisco. Cadena: cookie _vt (recaptcha bypass, IP-bound) → GET /tocas?page=N (10/pág, 8,438 págs) → GET /toca/{id}/file → URL S3 firmada → PDF sin sesión. La cookie se auto-renueva via CDP al navegador persistente (click NUEVA BÚSQUEDA→BUSCAR revalida grecaptcha). Solo corre en la Mac con el navegador CDP :9223 VIVO. NOTA: tambien hay url_resumen_ia (resúmenes ciudadanos .txt) cosechables.",
     "api-rest+recaptcha-cdp", "https://publica-sentencias-backend.stjjalisco.gob.mx/tocas", "mac-cdp-navegador",
     "Re-query /tocas pages con periodo reciente (campo periodo=año) y comparar ids conocidos en estado_ids.json; PDFs S3 solo para ids nuevos",
     "mensual", False, None),  # estado vive en la Mac: se registra desde ahí manualmente
    ("SentenciasQro", "harvest_queretaro.py",
     "Sentencias Poder Judicial Querétaro. Cadena: POST leeSent.php (fecINI/fecFIN) → filas con clave estructural ORGANO|MATERIA|TIPO|AÑO|NUM|seq → POST crear_token.php → JWT (TTL 60s) → GET leeDoc.php?cual=JWT → PDF. Puro HTTP. BUG CONOCIDO: la paginación (pag=N) devuelve duplicados — revisar el parámetro real de offset antes de re-cosecha masiva; primer barrido 2008-2026 dio 246 únicas.",
     "scraping-http+jwt", "https://www.poderjudicialqro.gob.mx/APP_UT69ii/leeSent.php", "server-tmux",
     "Re-query por trimestres recientes; las claves son deterministas por expediente — diff contra estado.json",
     "mensual", False, lambda: _estado_server("/opt/aijusticia/corpus_downloads/queretaro/estado.json", "claves")),
    ("TesisUNAM", "harvest_unam_server.py",
     "43,423 tesis Repositorio UNAM (colección Tesis, search c=b0dZK5). Fase A: GET /contenidos/ficha/<slug> SIN sesión → HTML con URL PDF (132.248.9.195 → redirect tesiunamdocumentos.dgb.unam.mx). Fase B: PDF directo + extracción. ~24-31% con PDF (las recientes digitalizadas), 173K tokens/tesis. Índice de slugs: paginar /contenidos?c=b0dZK5&q=derecho&i=<pág> (50/pág, 878 págs) CON sesión caliente (GET /contenidos primero)",
     "scraping-http", "https://repositorio.unam.mx/contenidos", "server-tmux",
     "Re-correr índice páginas recientes (i=1..N hasta detectar slugs conocidos); fichas solo de slugs nuevos",
     "trimestral", False, lambda: _estado_server("/opt/aijusticia/corpus_downloads/unam_tesis/estado_fichas.json", "fichas")),
    ("SentenciasEdomex", "harvest_edomex.py",
     "~197K sentencias PJEdomex vía API elástica (backgestiondocumental) + PDFs de electronico.pjedomex.gob.mx. Slices materia×año, sub-rebanado trimestral si >10K (límite elástico). Fase1 manifiesto COMPLETO (85,572 PDFs únicos tras dedup de 124K filas). Fase2 descarga+extracción en curso.",
     "api-rest", "https://backgestiondocumental.pjedomex.gob.mx/files/search/elastic", "server-tmux",
     "fase1 re-query year=años recientes; fase2 usa estado.json (PDFs ya bajados)",
     "mensual", False, lambda: _estado_server("/opt/aijusticia/corpus_downloads/edomex/estado_fase2.json", "pdfs")),
    ("DOF-Huecos", "dof_huecos.py",
     "Backfill DOF 2009-2010 y 2013-2020 (huecos del backfill original que murió por errores de referer). listar_desde camina hacia atrás: para mes [start, start+30) se consulta desde start+30.",
     "scraping-http", "https://www.dof.gob.mx/index_111.php", "server-tmux",
     "Una sola vez (histórico). Incremental diario ya cubierto por el harvester DOF principal",
     "única", False, None),
]


def leer_script(nombre):
    for base in (SCRIPTS, Path("/tmp")):
        p = base / nombre
        if p.exists():
            return p.read_text(errors="replace")[:200_000]
    return None


def _estado_mac(rel, clave):
    """Lee un estado json desde la Mac (para fuentes que corren aquí)."""
    try:
        p = Path.home() / "workspace/aijusticia" / rel
        return {clave: len(json.loads(p.read_text()))}
    except Exception as e:
        return {"error": str(e)[:60]}


def _estado_server(abs_path, clave):
    """Lee un estado json desde el server (corre en el server)."""
    try:
        return {clave: len(json.loads(open(abs_path).read()))}
    except Exception as e:
        return {"error": str(e)[:60]}


def main():
    conn = psycopg.connect(host="127.0.0.1", port=5432, dbname="aijusticia",
                           user="aijusticia", password="aijusticia2016", autocommit=True)
    cur = conn.cursor()
    ahora = datetime.now(timezone.utc)
    n = 0
    for fuente, script, desc, metodo, origen, ejec, dif, freq, completa, estado_fn in REGISTRO:
        codigo = leer_script(script)
        if not codigo:
            print(f"[skip] {script} no encontrado")
            continue
        estado = {}
        if estado_fn:
            try:
                estado = estado_fn() or {}
            except Exception as e:
                estado = {"error_leyendo_estado": str(e)[:100]}
        cur.execute("""
            INSERT INTO harvest_scripts
                (fuente, nombre, descripcion, metodo, origen_url, ejecucion, codigo,
                 estado, diferencial, frecuencia, completa, ultima_ejecucion, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
            ON CONFLICT (fuente, nombre) DO UPDATE SET
                descripcion=EXCLUDED.descripcion, metodo=EXCLUDED.metodo,
                origen_url=EXCLUDED.origen_url, ejecucion=EXCLUDED.ejecucion,
                codigo=EXCLUDED.codigo, estado=EXCLUDED.estado,
                diferencial=EXCLUDED.diferencial, frecuencia=EXCLUDED.frecuencia,
                completa=EXCLUDED.completa, ultima_ejecucion=EXCLUDED.ultima_ejecucion,
                updated_at=now()
        """, (fuente, script, desc, metodo, origen, ejec, codigo,
              json.dumps(estado, ensure_ascii=False), dif, freq, completa, ahora))
        n += 1
        print(f"[ok] {fuente} :: {script} (estado: {json.dumps(estado, ensure_ascii=False)[:80]})")
    print(f"\n{n} harvesters registrados")
    conn.close()


if __name__ == "__main__":
    main()
