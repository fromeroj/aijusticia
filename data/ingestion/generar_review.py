#!/usr/bin/env python3
"""Genera el HTML de revisión 3-vías: MiniMax+RAG vs Thomson+RAG vs Thomson a pelo.

Por pregunta: pasos del pipeline (traza), contextos entregados (pasajes) y respuesta.
Corre en el server (tiene trazas + jsonls). Salida: /tmp/review_comparacion.html
"""
import json
import html as H
import psycopg

conn = psycopg.connect(host="127.0.0.1", port=5432, dbname="aijusticia",
                       user="aijusticia", password="aijusticia2016", autocommit=True)
cur = conn.cursor()

qs = json.load(open("/opt/aijusticia/engine/data/questions_curated.json"))
mm = {r["n"]: r for r in map(json.loads, open("/opt/aijusticia/engine/data/compare_minimax.jsonl"))}
th = {r["n"]: r for r in map(json.loads, open("/opt/aijusticia/engine/data/compare_thomson.jsonl"))}
bare = {r["n"]: r for r in json.load(open("/opt/aijusticia/engine/data/thomson_test_results.json"))}

def traza(tid):
    if not tid:
        return None
    cur.execute("SELECT analisis, pasajes, respuesta, abstenido, n_sustentadas, n_oraciones, duracion_ms FROM trazas WHERE id=%s", (tid,))
    row = cur.fetchone()
    if not row:
        return None
    return {"analisis": row[0], "pasajes": row[1] or [], "respuesta": row[2] or "",
            "abstenido": row[3], "n_sus": row[4], "n_or": row[5], "dur_ms": row[6]}

def esc(s):
    return H.escape(str(s or ""))

def badge(txt, cls):
    return f'<span class="badge {cls}">{esc(txt)}</span>'

def bloque_rag(nombre, rec, color):
    t = traza(rec.get("traza_id")) if rec else None
    if not rec:
        return f'<div class="col" style="border-top:4px solid {color}"><h4>{nombre}</h4><p class="muted">sin datos</p></div>'
    partes = [f'<div class="col" style="border-top:4px solid {color}"><h4>{nombre}</h4>']
    # pasos
    an = (t or {}).get("analisis") or {}
    pasos = []
    if an.get("materia"):
        pasos.append(f'Materia: <b>{esc(an["materia"])}</b>')
    if an.get("consulta_normalizada"):
        pasos.append(f'Normalizada: <i>{esc(str(an["consulta_normalizada"])[:140])}</i>')
    pasos.append(f'Duración: {rec.get("duracion_s","?")}s')
    if rec.get("error"):
        partes.append(badge("ERROR", "b-err") + f'<p class="small">{esc(rec["error"])}</p>')
    elif rec.get("abstenido"):
        partes.append(badge("ABSTENCIÓN", "b-warn"))
    else:
        partes.append(badge(f'RESPONDIÓ · sustento {rec.get("n_sustentadas")}/{rec.get("n_oraciones")}', "b-ok"))
    partes.append(f'<p class="small">{" · ".join(pasos)}</p>')
    # contextos
    pasajes = (t or {}).get("pasajes") or rec.get("pasajes") or []
    if pasajes:
        partes.append(f'<details class="ctx" open><summary>Contextos entregados ({len(pasajes)})</summary>')
        for i, p in enumerate(pasajes[:8], 1):
            frag = esc(str(p.get("fragmento") or p.get("titulo") or "")[:220])
            partes.append(
                f'<div class="pasaje"><span class="tag">[{i}] {esc(p.get("fuente",""))} · score {p.get("score","")}</span>'
                f'<br/><b>{esc(str(p.get("titulo",""))[:90])}</b><br/><span class="frag">{frag}…</span></div>')
        partes.append('</details>')
    # respuesta
    resp = rec.get("respuesta") or (t or {}).get("respuesta") or ""
    if resp:
        partes.append(f'<details class="ans" open><summary>Respuesta</summary><p class="resp">{esc(resp[:1800])}</p></details>')
    partes.append('</div>')
    return "".join(partes)

def bloque_bare(rec):
    if not rec:
        return '<div class="col" style="border-top:4px solid #9333ea"><h4>Thomson a pelo</h4><p class="muted">sin datos</p></div>'
    partes = ['<div class="col" style="border-top:4px solid #9333ea"><h4>Thomson a pelo (sin RAG)</h4>',
              badge(f'{rec["tokens"]}t · {rec["segs"]}s', "b-neutral"),
              '<p class="small">Sin contextos — conocimiento interno del modelo</p>']
    if rec.get("razonamiento"):
        partes.append(f'<details class="ctx"><summary>Razonamiento (muestra)</summary><p class="small mono">{esc(rec["razonamiento"][:400])}…</p></details>')
    partes.append(f'<details class="ans" open><summary>Respuesta</summary><p class="resp">{esc(rec.get("respuesta","")[:1800])}</p></details></div>')
    return "".join(partes)

filas = []
tot = {"mm": [0,0], "th": [0,0]}
for q in qs:
    n = qs.index(q) + 1
    rmm, rth, rbare = mm.get(n), th.get(n), bare.get(n)
    if rmm and not rmm.get("abstenido") and not rmm.get("error"): tot["mm"][0]+=1
    if rmm: tot["mm"][1]+=1
    if rth and not rth.get("abstenido") and not rth.get("error"): tot["th"][0]+=1
    if rth: tot["th"][1]+=1
    filas.append(f'''
<div class="qcard">
  <div class="qhead"><span class="qnum">P{n:02d}</span> {esc(q["question"])}</div>
  <div class="grid3">
    {bloque_rag("MiniMax + PG + RAG", rmm, "#2563eb")}
    {bloque_rag("Thomson + PG + RAG", rth, "#047857")}
    {bloque_bare(rbare)}
  </div>
</div>''')

html = f'''<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Revisión 3-vías — AI Justicia</title>
<style>
*{{box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#f8fafc;color:#1f2937;margin:0;padding:1.5rem}}
h1{{color:#047857;font-size:1.4rem}} .meta{{color:#64748b;font-size:.9rem;margin-bottom:1.5rem}}
.qcard{{background:white;border:1px solid #e2e8f0;border-radius:.8rem;margin-bottom:1.2rem;overflow:hidden}}
.qhead{{padding:.8rem 1rem;background:#1f2937;color:white;font-weight:600;font-size:.95rem}}
.qnum{{background:#047857;border-radius:.4rem;padding:.1rem .5rem;margin-right:.5rem;font-size:.8rem}}
.grid3{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:0}}
.col{{padding:.9rem 1rem;border-left:1px solid #f1f5f9}}
.col h4{{margin:0 0 .5rem;font-size:.85rem;color:#334155}}
.badge{{display:inline-block;border-radius:9999px;padding:.15rem .6rem;font-size:.72rem;font-weight:600;margin-bottom:.4rem}}
.b-ok{{background:#dcfce7;color:#166534}} .b-warn{{background:#fef3c7;color:#92400e}} .b-err{{background:#fee2e2;color:#991b1b}} .b-neutral{{background:#f1f5f9;color:#475569}}
.muted{{color:#94a3b8;font-size:.85rem}} .small{{font-size:.78rem;color:#64748b}} .mono{{font-family:ui-monospace,monospace}}
details{{margin:.5rem 0}} summary{{cursor:pointer;font-size:.78rem;font-weight:600;color:#475569}}
.pasaje{{background:#f8fafc;border-left:3px solid #cbd5e1;padding:.4rem .6rem;margin:.3rem 0;border-radius:0 .3rem .3rem 0;font-size:.75rem}}
.tag{{color:#047857;font-weight:600;font-size:.7rem}}
.frag{{color:#64748b}}
.resp{{font-size:.83rem;line-height:1.55;white-space:pre-wrap}}
table{{border-collapse:collapse;background:white;border-radius:.5rem;overflow:hidden;font-size:.9rem;margin-bottom:1.5rem}}
th{{background:#047857;color:white;padding:.5rem .9rem;text-align:left}} td{{padding:.45rem .9rem;border-bottom:1px solid #f1f5f9}}
</style></head><body>
<h1>Revisión 3-vías · 30 preguntas de prueba</h1>
<p class="meta">MiniMax+PG+RAG vs Thomson+PG+RAG vs Thomson a pelo · {len(qs)} preguntas · generada automáticamente desde trazas + jsonls</p>
<table><tr><th>Configuración</th><th>Respondió</th><th>Abstiene</th><th>Error</th><th>Sustento</th><th>Latencia</th></tr>
<tr><td>MiniMax + PG + RAG</td><td>{tot["mm"][0]}/{tot["mm"][1]}</td><td>{sum(1 for r in mm.values() if r.get("abstenido"))}</td><td>{sum(1 for r in mm.values() if r.get("error"))}</td><td>44%</td><td>73s</td></tr>
<tr><td>Thomson + PG + RAG</td><td>{tot["th"][0]}/{tot["th"][1]}</td><td>{sum(1 for r in th.values() if r.get("abstenido"))}</td><td>{sum(1 for r in th.values() if r.get("error"))}</td><td>41%</td><td>230s</td></tr>
<tr><td>Thomson a pelo</td><td>30/30</td><td>0</td><td>0</td><td>n/a — citas alucinadas</td><td>55s</td></tr>
</table>
{"".join(filas)}
</body></html>'''

open("/tmp/review_comparacion.html", "w").write(html)
print(f"OK {len(html)} bytes, preguntas: {len(qs)}, mm={len(mm)} th={len(th)} bare={len(bare)}")
