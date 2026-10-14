#!/bin/bash
# LexMX: sync diferencial del repo de leyes federales en Markdown.
# Estrategia: git pull, diff de state.json (fecha reforma por sigla),
# re-ingestar solo las leyes cambiadas. Idempotente por (fuente,dedup_key).
set -e
DIR=/opt/aijusticia/corpus_downloads/lexmx_repo
if [ ! -d "$DIR" ]; then
  git clone --quiet https://github.com/ingteranalvarez/lex-mx.git "$DIR"
else
  git -C "$DIR" pull --quiet
fi
cd /opt/aijusticia/engine
.venv/bin/python - << 'PYEOF'
import hashlib, json, re, subprocess
from pathlib import Path
import psycopg

DIR = Path("/opt/aijusticia/corpus_downloads/lexmx_repo")
import os; _env = dict(l.strip().split("=",1) for l in open("/opt/aijusticia/engine/.env") if "=" in l and not l.startswith("#"))
conn = psycopg.connect(host="127.0.0.1", port=5432, dbname=_env.get("PG_DB","aijusticia"),
                       user=_env.get("PG_USER","aijusticia"), password=_env["PG_PASSWORD"], autocommit=True)
cur = conn.cursor()
n = 0
for md in sorted((DIR / "leyes").glob("*.md")):
    raw = md.read_text(errors="replace")
    m = re.match(r"^---\n(.*?)\n---\n(.*)", raw, re.S)
    if not m:
        continue
    fm = dict(re.findall(r'^(\w+):\s*"?([^"\n]+)"?', m.group(1), re.M))
    sigla = fm.get("sigla", md.stem)
    reforma = fm.get("ultima_reforma", "")
    # diferencial: solo si la reforma es mas nueva que lo ingerido
    cur.execute("SELECT fecha_reforma FROM documentos WHERE fuente='LexMX' AND dedup_key=%s",
                (hashlib.md5(f"lexmx|{sigla}".encode()).hexdigest(),))
    row = cur.fetchone()
    if row and row[0] and reforma and str(row[0]) >= reforma:
        continue
    texto = m.group(2).strip().replace(chr(0), "")[:900000]
    if len(texto) < 500:
        continue
    dedup = hashlib.md5(f"lexmx|{sigla}".encode()).hexdigest()
    cur.execute("""INSERT INTO documentos (fuente, entidad, tipo, titulo, texto, url_origen, dedup_key, fecha_reforma)
        VALUES (%s,%s,%s,%s,%s,%s,%s,NULLIF(%s,'')::date)
        ON CONFLICT (fuente, dedup_key) DO UPDATE SET texto=EXCLUDED.texto,
            fecha_reforma=EXCLUDED.fecha_reforma, updated_at=now() RETURNING id""",
        ("LexMX", "Federal", "ley", fm.get("titulo", sigla)[:300], texto,
         f"https://github.com/ingteranalvarez/lex-mx/blob/main/leyes/{md.name}", dedup, reforma or None))
    doc_id = cur.fetchone()[0]
    cur.execute("DELETE FROM documentos_chunks WHERE documento_id=%s", (doc_id,))
    vals = [(doc_id, j//1200, texto[j:j+1200].strip()) for j in range(0, len(texto), 1200)
            if len(texto[j:j+1200].strip()) > 100]
    cur.executemany("INSERT INTO documentos_chunks (documento_id, ordinal, texto) VALUES (%s,%s,%s)", vals)
    n += 1
print(f"LexMX diferencial: {n} leyes actualizadas")
conn.close()
PYEOF
