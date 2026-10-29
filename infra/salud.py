#!/usr/bin/env python3
"""Salud integral del sistema AI Justicia — un comando, todo el sistema.

Uso:
  python3 infra/salud.py               # chequeo estándar (~15s)
  python3 infra/salud.py --full        # + smoke del chat (1 pregunta real)
  python3 infra/salud.py --json        # salida JSON (para CI)
Exit codes: 0 = todo OK · 1 = advertencias · 2 = fallo crítico
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone

import requests

PROD = "https://aijusticia.mx"
OFFICE = "http://162.35.113.166:8080"
SSH_PROD = "root@162.35.113.166"
SSH_AUX = "root@66.154.100.25"
SSH_TIMEOUT = 25

RESULTADOS: list[dict] = []


def check(nombre: str, fn, critico: bool = True):
    t0 = time.time()
    try:
        estado, detalle = fn()
    except Exception as e:
        estado, detalle = "fail", f"excepción: {str(e)[:120]}"
    dt = round(time.time() - t0, 1)
    icono = {"ok": "✅", "warn": "⚠️ ", "fail": "❌"}[estado]
    RESULTADOS.append({"check": nombre, "estado": estado, "detalle": detalle,
                       "segundos": dt, "critico": critico})
    print(f"{icono} {nombre:38s} {detalle[:80]}  ({dt}s)", flush=True)


def http(url: str, expect: int = 200, timeout: int = 20) -> tuple[str, str]:
    r = requests.get(url, timeout=timeout)
    return ("ok", f"HTTP {r.status_code}") if r.status_code == expect else \
        ("fail" if r.status_code >= 500 else "warn", f"HTTP {r.status_code}")


def ssh(host: str, cmd: str, timeout: int = SSH_TIMEOUT) -> str:
    r = subprocess.run(["ssh", "-o", "ConnectTimeout=15", "-o",
                        "StrictHostKeyChecking=accept-new", host, cmd],
                       capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()


def dias_desde(iso: str) -> float:
    then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - then).total_seconds() / 86400


# ---- checks ---------------------------------------------------------------

def c_web():
    return http(f"{PROD}/")


def c_engine_health():
    r = requests.get(f"{PROD}/health", timeout=20)
    d = r.json()
    llm = d.get("lmstudio", {}).get("ok", d.get("llm", False))
    return ("ok", f"status ok, llm={llm}") if r.status_code == 200 and llm else \
        ("fail", f"status={r.status_code} llm={llm}")


def c_corpus():
    r = requests.get(f"{PROD}/corpus/status", timeout=30)
    t = r.json()["totales"]
    docs, chunks = t["documentos"], t["chunks"]
    if docs < 400_000:
        return "warn", f"{docs:,} docs (bajó?)"
    return "ok", f"{docs:,} docs · {chunks/1e6:.1f}M chunks"


def c_frescura_dof():
    r = requests.get(f"{PROD}/corpus/status", timeout=30)
    for f in r.json()["fuentes"]:
        if f["fuente"] == "DOF":
            dias = f["dias_sin_nuevos"]
            if dias <= 2:
                return "ok", f"último DOF hace {dias}d ({f['ultimo_doc']})"
            return "fail", f"DOF con {dias}d sin nuevos (cron roto?) — {f['ultimo_doc']}"
    return "fail", "fuente DOF ausente"


def c_chat_stream():
    r = requests.post(f"{PROD}/chat/stream",
                      json={"consulta": "plazo queja", "historial": []},
                      stream=True, timeout=(10, 60))
    eventos = set()
    for line in r.iter_lines(decode_unicode=True):
        if line and line.startswith("event: "):
            eventos.add(line[7:])
        if "done" in eventos:
            break
    faltan = {"token", "done"} - eventos
    if faltan:
        return "fail", f"sin eventos {faltan}"
    return "ok", f"streaming ok ({'laws' in eventos and 'con leyes' or 'sin leyes'})"


def c_office():
    return http(f"{OFFICE}/status.php", timeout=15)


def c_servicios_162():
    out = ssh(SSH_PROD, "systemctl is-active aijusticia-engine aijusticia-web docker | tr '\\n' ' '")
    if "active" in out and "inactive" not in out and "failed" not in out:
        return "ok", out
    return "fail", out or "sin respuesta ssh"


def c_disco_162():
    out = ssh(SSH_PROD, "df -h / | awk 'NR==2{print $5}'")
    pct = int(out.rstrip("%") or 0)
    if pct < 85:
        return "ok", f"disco {pct}%"
    return ("warn" if pct < 92 else "fail"), f"disco {pct}%"


def c_carga_162():
    out = ssh(SSH_PROD, "uptime | awk -F'average:' '{print $2}'")
    load1 = float(out.split(",")[0].strip() or 0)
    if load1 <= 8:
        return "ok", f"load {load1}"
    return ("warn" if load1 <= 14 else "fail"), f"load {load1} (¿mantenimiento de día?)"


def c_backup_offsite():
    out = ssh(SSH_PROD, "stat -c %Y $(ls -t /mnt/backups_offsite/aijusticia_*.sql.gz 2>/dev/null | head -1) 2>/dev/null")
    if not out.strip().isdigit():
        return "warn", "off-site vacío (NFS caído o copia rota)"
    edad_d = (time.time() - int(out.strip())) / 86400
    if edad_d <= 2:
        return "ok", f"off-site hace {edad_d:.0f}d"
    return "fail", f"off-site con {edad_d:.0f}d de retraso"


def c_backup():
    out = ssh(SSH_PROD, "stat -c %Y $(ls -t /opt/aijusticia/backups/aijusticia_*.sql.gz 2>/dev/null | head -1) 2>/dev/null")
    if not out.strip().isdigit():
        return "fail", "sin backups (cron de backup roto)"
    edad_h = (time.time() - int(out.strip())) / 3600
    if edad_h < 30:
        return "ok", f"último backup hace {edad_h:.0f}h"
    return "warn", f"backup viejo: {edad_h:.0f}h"


def c_harvest_aux():
    out = ssh(SSH_AUX, "pgrep -f harvest_ordenjuridico >/dev/null && echo vivo || echo muerto; "
                       "tail -1 /opt/aijusticia/ordenjuridico_full.log 2>/dev/null")
    lineas = out.splitlines()
    vivo = "vivo" in (lineas[0] if lineas else "")
    progreso = lineas[1][:60] if len(lineas) > 1 else "?"
    if vivo:
        return "ok", f"harvest vivo — {progreso}"
    return "warn", f"harvest detenido — {progreso}"


def c_bateria_reciente():
    import glob as g
    runs = sorted(g.glob("eval/runs/bateria_*.json"))
    if not runs:
        return "warn", "sin corridas de batería"
    import os
    edad_h = (time.time() - os.path.getmtime(runs[-1])) / 3600
    d = json.load(open(runs[-1]))
    if edad_h > 72:
        return "warn", f"última batería hace {edad_h:.0f}h ({d.get('ok')}/{d.get('total')})"
    return "ok", f"hace {edad_h:.0f}h: {d.get('ok')}/{d.get('total')}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="+ smoke del chat (consume tokens)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    import os
    sin_ssh = os.environ.get("SALUD_SIN_SSH") == "1"

    print("== SALUD AI JUSTICIA ==", datetime.now().strftime("%Y-%m-%d %H:%M %Z"), flush=True)
    check("web aijusticia.mx", c_web)
    check("engine /health + LLM", c_engine_health)
    check("corpus (docs/chunks)", c_corpus)
    check("frescura DOF (cron diario)", c_frescura_dof)
    check("office Nextcloud :8080", c_office, critico=False)
    if not sin_ssh:
        check("servicios systemd 162", c_servicios_162)
        check("disco 162", c_disco_162, critico=False)
        check("carga 162", c_carga_162, critico=False)
        check("backup DB local", c_backup, critico=False)
        check("backup off-site (storage)", c_backup_offsite, critico=True)
        check("harvest auxiliar 66", c_harvest_aux, critico=False)
        check("batería reciente", c_bateria_reciente, critico=False)
    if args.full:
        check("smoke chat /chat/stream", c_chat_stream)

    fails = [r for r in RESULTADOS if r["estado"] == "fail"]
    warns = [r for r in RESULTADOS if r["estado"] == "warn"]
    print(f"\n== {len(RESULTADOS) - len(fails) - len(warns)} ok · {len(warns)} warn · {len(fails)} FAIL ==")
    if args.json:
        print(json.dumps(RESULTADOS, ensure_ascii=False, indent=1))
    sys.exit(2 if fails else (1 if warns else 0))


if __name__ == "__main__":
    main()
