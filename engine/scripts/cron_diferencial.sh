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

# 3) Estadística del día (contra snapshot de ayer)
.venv/bin/python - << 'PYEOF' >> $LOG 2>&1
import psycopg
from datetime import date
conn = psycopg.connect(host="127.0.0.1", port=5432, dbname="aijusticia",
                       user="aijusticia", password="aijusticia2016", autocommit=True)
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

echo "=== $(date '+%F %T') fin ===" >> $LOG
