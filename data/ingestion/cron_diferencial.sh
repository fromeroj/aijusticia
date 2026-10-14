#!/bin/bash
# Cron diferencial diario: re-cosecha fuentes registradas + estadística del día.
# Corre en el MAIN server. Los harvesters mac-only (Jalisco, geo-bloqueos) quedan
# fuera — se registran como pendientes_manuales.
set -u
LOG=/var/log/aijusticia_cron.log
echo "=== $(date '+%F %T') inicio cron diferencial ===" >> $LOG

cd /opt/aijusticia/engine

# 1) LexMX (diaria, la más importante — leyes federales)
bash scripts/harvest_lexmx.sh >> $LOG 2>&1

# 2) DOF incremental (notas de ayer/hoy)
timeout 3600 nice -n 19 .venv/bin/python - << 'PYEOF' >> $LOG 2>&1
import sys
sys.path.insert(0, "/opt/aijusticia/engine")
from datetime import date, timedelta
from ai_justicia.corpus.adapters.dof import DOFAdapter
from ai_justicia.corpus.models import Documento, Fuente
from ai_justicia.corpus.store import batch_upsert_documentos
a = DOFAdapter()
metas = list(a.listar_desde(fecha_inicio=date.today(), max_days=3))
docs = []
for m in metas:
    try:
        t = a.obtener_texto(m)
        if t and len(t) > 200:
            docs.append(Documento(fuente=Fuente.DOF, titulo=m.titulo[:300], texto=t,
                                  fecha_publicacion=m.fecha_publicacion,
                                  url_origen=m.url_origen, tipo=m.tipo))
    except Exception:
        pass
if docs:
    n = batch_upsert_documentos(docs)
    print(f"DOF diario: +{n}")
PYEOF

# 3) SJF diferencial (SOLO domingos — la SCJN bloquea consultas diarias)
if [ "$(date +%u)" = "7" ]; then
timeout 1800 nice -n 19 .venv/bin/python - << 'PYEOF' >> $LOG 2>&1
import sys
sys.path.insert(0, "/opt/aijusticia/engine")
from datetime import date, timedelta
from ai_justicia.corpus.adapters.sjf import SJFAdapter
from ai_justicia.corpus.models import Documento, Fuente
from ai_justicia.corpus.store import batch_upsert_documentos
a = SJFAdapter()
metas = list(a.listar_desde(fecha_inicio=date.today() - timedelta(days=2), max_pages=5))
docs = []
for m in metas:
    try:
        t = a.obtener_texto(m)
        if t and len(t) > 200:
            docs.append(Documento(
                fuente=Fuente.SJF, titulo=m.titulo[:300], texto=t,
                registro_sjf=m.id_externo, tipo=m.tipo,
                url_origen=m.url_origen))
    except Exception:
        pass
if docs:
    n = batch_upsert_documentos(docs)
    print(f"SJF diferencial: +{n}")
else:
    print("SJF diferencial: sin novedades")
PYEOF
else
    echo "SJF: skip (no domingo)" >> $LOG
fi

# 4) Leyes federales frescas (LeyesBiblio — detecta reformas del día)
timeout 1800 nice -n 19 .venv/bin/python - << 'PYEOF' >> $LOG 2>&1
import sys, json, re, subprocess, tempfile, os, urllib.request
sys.path.insert(0, "/opt/aijusticia/engine")
from ai_justicia.corpus.models import Documento, Fuente
from ai_justicia.corpus.store import batch_upsert_documentos
from ai_justicia.corpus.clean import limpiar_texto

BASE = "https://www.diputados.gob.mx/LeyesBiblio"
INDEX = f"{BASE}/index.htm"
req = urllib.request.Request(INDEX, headers={"User-Agent": "Mozilla/5.0 (educational)"})
html = urllib.request.urlopen(req, timeout=30).read().decode("iso-8859-1", errors="replace")
patron = re.compile(r'<a\s+href="(?:\./)?(?:ref|doc)/([A-Za-z0-9_ñÑ]+)\.(?:htm|doc)"[^>]*>(.*?)</a>', re.I | re.DOTALL)
limpiar = re.compile(r"<[^>]+>|\s+")
catalogo = {}
for code, nombre in patron.findall(html):
    nombre = limpiar.sub(" ", nombre).strip()
    if nombre and len(nombre) > 4 and "reformas" not in nombre.lower():
        catalogo.setdefault(code.lower(), nombre)

# solo verificar las ~30 leyes clave que cambian con más frecuencia
CLAVE = ["cpeum", "ccf", "cpf", "cft", "cpcf", "cnpp", "cnpcef", "cff", "cca",
         "lft", "lfpdppp", "lamp", "lfpc", "lgs", "lgsc", "lritf", "loapf", "ljudfed"]
docs = []
for code in CLAVE:
    if code not in catalogo:
        continue
    try:
        r2 = urllib.request.Request(f"{BASE}/doc/{code.upper()}.doc",
                                    headers={"User-Agent": "Mozilla/5.0"})
        contenido = urllib.request.urlopen(r2, timeout=30).read()
        with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as f:
            f.write(contenido)
            ruta = f.name
        texto = ""
        for cmd in (["antiword", "-w", "0", ruta], ["unrtf", "--text", ruta]):
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if proc.returncode == 0 and len(proc.stdout.strip()) > 200:
                    texto = proc.stdout
                    break
            except Exception:
                continue
        os.unlink(ruta)
        texto = limpiar_texto(texto) if texto else ""
        if len(texto) > 500:
            docs.append(Documento(
                fuente=Fuente.LEYES_BIBLIO, titulo=catalogo[code], texto=texto,
                tipo="ley", url_origen=f"{BASE}/ref/{code}.htm"))
    except Exception:
        continue
if docs:
    n = batch_upsert_documentos(docs)
    print(f"LeyesBiblio diario: +{n} leyes verificadas")
else:
    print("LeyesBiblio diario: sin cambios")
PYEOF

# 5) Estadística del día (contra snapshot de ayer)
.venv/bin/python - << 'PYEOF' >> $LOG 2>&1
import psycopg
from datetime import date
import os
_env = dict(l.strip().split("=",1) for l in open("/opt/aijusticia/engine/.env") if "=" in l and not l.startswith("#"))
conn = psycopg.connect(host="127.0.0.1", port=int(_env.get("PG_PORT","5432")),
                       dbname=_env.get("PG_DB","aijusticia"),
                       user=_env.get("PG_USER","aijusticia"), password=_env["PG_PASSWORD"], autocommit=True)
cur = conn.cursor()
cur.execute("SELECT COALESCE(SUM(LENGTH(texto)),0)/4, COUNT(*) FROM documentos_chunks")
tok, docs = cur.fetchone()
hoy = date.today()
cur.execute("""INSERT INTO corpus_diario (fecha, docs_nuevos, tokens_nuevos, total_docs, total_tokens)
    VALUES (%s, 0, 0, %s, %s)
    ON CONFLICT (fecha) DO UPDATE SET total_docs=%s, total_tokens=%s""",
    (hoy, docs, tok, docs, tok))
# delta contra ayer
cur.execute("""SELECT total_docs, total_tokens FROM corpus_diario
    WHERE fecha < %s ORDER BY fecha DESC LIMIT 1""", (hoy,))
row = cur.fetchone()
if row:
    d_docs, d_tok = max(0, docs - row[0]), max(0, tok - row[1])
    cur.execute("UPDATE corpus_diario SET docs_nuevos=%s, tokens_nuevos=%s WHERE fecha=%s",
                (d_docs, d_tok, hoy))
    print(f"estadistica {hoy}: +{d_docs} docs, +{d_tok:,} tokens (total {tok:,})")
conn.close()
PYEOF

# 6) Health check: registrar el estado de cada fuente en source_health
.venv/bin/python - << 'PYEOF' >> $LOG 2>&1
import os, psycopg
from datetime import datetime
_env = dict(l.strip().split("=",1) for l in open("/opt/aijusticia/engine/.env") if "=" in l and not l.startswith("#"))
conn = psycopg.connect(host="127.0.0.1", port=int(_env.get("PG_PORT","5432")),
                       dbname=_env.get("PG_DB","aijusticia"),
                       user=_env.get("PG_USER","aijusticia"), password=_env["PG_PASSWORD"], autocommit=True)
cur = conn.cursor()
cur.execute("""
    SELECT fuente, count(*), max(updated_at)::date
    FROM documentos
    WHERE updated_at > now() - interval '1 day'
    GROUP BY fuente
""")
for fuente, n, ultima in cur.fetchall():
    cur.execute("""
        INSERT INTO source_health (fuente, entidad, tipo, adapter_class, enabled, cron_expr,
                                   last_run_at, last_success_at, health_status, total_documentos)
        VALUES (%s, 'Federal', 'diario', 'cron_diferencial', true, 'daily',
                now(), now(), 'ok', %s)
        ON CONFLICT (fuente, entidad) DO UPDATE SET
            last_run_at = now(), last_success_at = now(),
            health_status = 'ok', total_documentos = %s
    """, (fuente, n, n))
    print(f"  health: {fuente} +{n} docs hoy")
conn.close()
PYEOF

echo "=== $(date '+%F %T') fin ===" >> $LOG
