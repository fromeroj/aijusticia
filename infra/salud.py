#!/usr/bin/env python3
"""Salud integral del sistema AI Justicia — un comando, todo el sistema.

Uso:
  python3 infra/salud.py               # chequeo estándar (~30s)
  python3 infra/salud.py --full        # + smoke del chat (1 pregunta real)
  python3 infra/salud.py --json        # salida JSON (para CI)
  SALUD_SIN_SSH=1 python3 infra/salud.py   # sólo lo que se ve por HTTP
Exit codes: 0 = todo OK · 1 = avisos · 2 = al menos un fallo

Qué aprendió este script (cada chequeo nació de una falla real que nadie vio):
  - frescura DOF        → el DOF deja de publicar en puentes oficiales: hasta 6
                          días es aviso, no fallo.
  - backup off-site     → la réplica estuvo 5 días parada (19-23 nov 2026) y el
                          monitor no la miraba. Atraso sin réplica en vuelo = fallo.
  - OOM recientes       → el mantenimiento nocturno asfixió la máquina tres veces
                          (10, 22, 23 nov 2026) sin que ningún chequeo lo viera.
  - mantenimiento       → un paso nocturno que falla debe verse al día siguiente.
  - sin pgrep remotos sin corchetes: el patrón se matchea a sí mismo por SSH y
    da un "ok" falso (el viejo chequeo del harvest llevaba semanas en falso verde).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

import requests

PROD = "https://aijusticia.mx"
OFFICE = "http://162.35.113.166:8080"
SSH_PROD = "root@162.35.113.166"
SSH_AUX = "root@66.154.100.25"
SSH_STORAGE = "root@148.135.106.227"
SSH_TIMEOUT = 25

RESULTADOS: list[dict] = []


def check(nombre: str, fn, critico: bool = True, recordar: bool = True):
    """Ejecuta un chequeo. Si devuelve None se omite (no aplica en este entorno).

    recordar=False marca un chequeo de EVENTO puntual (ya ocurrió y ya pasó):
    su fallo se alerta una vez y no se repite cada 12h mientras siga visible.
    """
    t0 = time.time()
    try:
        r = fn()
    except Exception as e:
        r = ("fail", f"excepción: {str(e)[:120]}")
    if r is None or r[0] is None:
        return
    estado, detalle = r
    dt = round(time.time() - t0, 1)
    icono = {"ok": "✅", "warn": "⚠️ ", "fail": "❌"}[estado]
    RESULTADOS.append({"check": nombre, "estado": estado, "detalle": detalle,
                       "segundos": dt, "critico": critico, "recordar": recordar})
    print(f"{icono} {nombre:34s} {detalle[:90]}  ({dt}s)", flush=True)


def http(url: str, expect: int = 200, timeout: int = 20) -> tuple[str, str]:
    r = requests.get(url, timeout=timeout)
    return ("ok", f"HTTP {r.status_code}") if r.status_code == expect else \
        ("fail" if r.status_code >= 500 else "warn", f"HTTP {r.status_code}")


def ssh(host: str, cmd: str, timeout: int = SSH_TIMEOUT) -> str:
    try:
        r = subprocess.run(["ssh", "-o", "ConnectTimeout=15", "-o", "BatchMode=yes", "-o",
                            "StrictHostKeyChecking=accept-new", host, cmd],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return ""
    return r.stdout.strip()


# ---- lo que se ve por HTTP --------------------------------------------------

def c_web():
    return http(f"{PROD}/")


def c_engine_health():
    r = requests.get(f"{PROD}/health", timeout=45)
    d = r.json()
    llm = d.get("lmstudio", {}).get("ok", d.get("llm", False))
    return ("ok", f"status ok, llm={llm}") if r.status_code == 200 and llm else \
        ("fail", f"status={r.status_code} llm={llm}")


_CORPUS: dict = {"t": 0.0, "datos": None}


def corpus_status() -> dict:
    """/corpus/status UNA vez por corrida: lo usan dos chequeos."""
    if _CORPUS["datos"] is None or time.time() - _CORPUS["t"] > 120:
        r = requests.get(f"{PROD}/corpus/status", timeout=60)
        r.raise_for_status()
        _CORPUS.update(t=time.time(), datos=r.json())
    return _CORPUS["datos"]


def c_corpus():
    t = corpus_status()["totales"]
    docs, chunks = t["documentos"], t["chunks"]
    if docs < 400_000:
        return "warn", f"{docs:,} docs (¿bajó?)"
    return "ok", f"{docs:,} docs · {chunks/1e6:.1f}M chunks"


def c_frescura_dof():
    f = next((x for x in corpus_status().get("fuentes", []) if x["fuente"] == "DOF"), None)
    if not f:
        return "fail", "fuente DOF ausente"
    dias = f["dias_sin_nuevos"]
    if dias <= 2:
        return "ok", f"último DOF hace {dias}d ({f['ultimo_doc']})"
    if dias <= 6:
        # puentes oficiales largos: el DOF deja de publicar hasta 6 días
        return "warn", f"sin DOF hace {dias}d (¿puente oficial?) — {f['ultimo_doc']}"
    return "fail", f"DOF con {dias}d sin nuevos (¿cron roto?) — {f['ultimo_doc']}"


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
    return "ok", f"streaming ok ({'con leyes' if 'laws' in eventos else 'sin leyes'})"


def c_office():
    return http(f"{OFFICE}/status.php", timeout=15)


# ---- lo que requiere SSH -----------------------------------------------------

def c_servicios_162():
    out = ssh(SSH_PROD, "systemctl is-active aijusticia-engine aijusticia-web docker postgresql cron | tr '\\n' ' '")
    estados = out.split()
    if len(estados) == 5 and all(e == "active" for e in estados):
        return "ok", " ".join(estados)
    return "fail", out or "sin respuesta ssh"


def c_disco_162():
    out = ssh(SSH_PROD, "df -P / | awk 'NR==2{print $5, $4}'")
    try:
        pct, libre_gb = int(out.split()[0].rstrip("%")), int(out.split()[1]) // 1048576
    except (ValueError, IndexError):
        return "fail", f"sin lectura de disco ({out[:40]!r})"
    # 182 murió de un disco al 100%: nunca dejar que 162 se acerque
    return ("ok" if pct < 80 else "warn" if pct < 90 else "fail"), f"disco {pct}% · {libre_gb}GB libres"


def c_carga_162():
    out = ssh(SSH_PROD, "cat /proc/loadavg | cut -d' ' -f1-3")
    try:
        load1 = float(out.split()[0])
    except (ValueError, IndexError):
        return "fail", "sin lectura de carga"
    return ("ok" if load1 <= 8 else "warn" if load1 <= 14 else "fail"), f"load {out}"


# Cuánto tiempo sigue visible un kill por OOM en el reporte. Es un EVENTO
# puntual, no una condición persistente: se alerta una vez (recordar=False) y
# un kill nuevo alerta de inmediato porque cambia el detalle del chequeo.
OOM_HORAS = 30


def c_oom_recientes():
    """Procesos que el kernel mató por falta de memoria en las últimas OOM_HORAS."""
    lineas = ssh(SSH_PROD,
                 f"journalctl -k --since '-{OOM_HORAS} hours' --no-pager -o short-iso 2>/dev/null "
                 "| grep 'Out of memory: Killed process'").splitlines()
    if not lineas:
        return "ok", f"sin kills por OOM en {OOM_HORAS}h"
    det = []
    for linea in lineas:
        m = re.search(r"Killed process \d+ \(([^)]+)\).*?anon-rss:(\d+)kB", linea)
        det.append(f"{linea[11:16]}Z {m.group(1)} {int(m.group(2))/1048576:.1f}GB" if m else linea[11:16])
    return "fail", f"{len(lineas)} kill(s) por OOM: " + ", ".join(det[-3:])


def c_mantenimiento():
    """Resultado de la última corrida del mantenimiento nocturno."""
    out = ssh(SSH_PROD,
              "awk '/===== mantenimiento nocturno =====/{n=0} {l[n++]=$0} "
              "END{for(i=0;i<n;i++) print l[i]}' /var/log/aijusticia_mantenimiento.log 2>/dev/null")
    if not out:
        return None, None   # todavía no corre con el formato nuevo
    lineas = out.splitlines()
    fallos = [re.sub(r".*FALLO rc=\S+: ", "", l) for l in lineas if "FALLO rc=" in l]
    if fallos:
        return "warn", "falló: " + "; ".join(f[:48] for f in fallos[-2:])
    if not any("fin del mantenimiento" in l for l in lineas):
        return "warn", "en curso o interrumpido"
    return "ok", "noche sin fallos"


def c_backup():
    out = ssh(SSH_PROD, "stat -c %Y $(ls -t /opt/aijusticia/backups/aijusticia_*.sql.gz 2>/dev/null | head -1) 2>/dev/null")
    if not out.strip().isdigit():
        return "fail", "sin dumps locales (¿cron de backup roto?)"
    edad_h = (time.time() - int(out.strip())) / 3600
    return ("ok" if edad_h < 30 else "warn"), f"último dump hace {edad_h:.0f}h"


def c_backup_offsite():
    """Debe haber un dump COMPLETO y reciente en el storage.

    Completo = mismo nombre y mismo tamaño (rsync --partial deja un archivo
    incompleto con el nombre final: el nombre solo no prueba nada).
    La criticidad es si existe copia completa reciente, no si ya terminó la
    transferencia del día (que puede tardar horas con el enlace lento).
    Atrasado y SIN réplica en curso = fallo: así estuvo 5 días (19-23 nov 2026).
    """
    local = ssh(SSH_PROD, "f=$(ls -t /opt/aijusticia/backups/aijusticia_*.sql.gz 2>/dev/null | head -1); "
                          "[ -n \"$f\" ] && basename \"$f\" && stat -c %s \"$f\"")
    nombre, _, tam = local.partition("\n")
    if not nombre.startswith("aijusticia_") or not tam.strip().isdigit():
        return "fail", "sin dumps locales que comparar"
    tam = int(tam)

    remoto = ssh(SSH_STORAGE, f"stat -c %s /srv/backups/{nombre} 2>/dev/null", timeout=30)
    if remoto.strip().isdigit() and int(remoto) == tam:
        return "ok", f"al día ({nombre})"

    # el más nuevo no está completo allá: ¿cuál es el último completo y de cuándo?
    anterior = ssh(SSH_STORAGE,
                   f"f=$(ls -t /srv/backups/aijusticia_*.sql.gz 2>/dev/null | grep -v '{nombre}' | head -1); "
                   "[ -n \"$f\" ] && stat -c '%Y' \"$f\"", timeout=30)
    try:
        edad_d = (time.time() - int(anterior.split()[0])) / 86400
    except (ValueError, IndexError):
        edad_d = 99.0
    n_vuelo = ssh(SSH_PROD, "pgrep -fc '[r]sync -a --partial --append-verify'").strip()
    en_vuelo = n_vuelo.isdigit() and int(n_vuelo) > 0
    pct = f"{int(remoto) / tam * 100:.0f}%" if remoto.strip().isdigit() else "0%"
    # "FALLO definitivo" = 6 intentos agotados; "ABANDON (6h limit)" = tope global
    # de la réplica. Ambos dejan ese dump sin copia completa.
    fallo = ssh(SSH_PROD, "grep -E 'off-site (FALLO definitivo|ABANDON)' /var/log/aijusticia_offsite.log 2>/dev/null | tail -1")
    if f" {nombre}" in fallo:
        return ("fail" if edad_d > 2 else "warn"), \
            f"réplica de {nombre} abandonada · último completo hace {edad_d:.0f}d"
    if edad_d <= 2:
        detalle = f"último completo hace {edad_d:.0f}d · {nombre} "
        return "ok", detalle + (f"replicando ({pct})" if en_vuelo else "aún sin replicar")
    if en_vuelo:
        return "warn", f"alcanzando: {pct} de {nombre} · último completo hace {edad_d:.0f}d"
    return "fail", f"off-site con {edad_d:.0f}d de retraso y sin réplica en curso"


def c_disco_storage():
    out = ssh(SSH_STORAGE, "df -Pm /srv | awk 'NR==2{print $5, $4}'", timeout=30)
    try:
        pct, libre_gb = int(out.split()[0].rstrip("%")), int(out.split()[1]) // 1024
    except (ValueError, IndexError):
        return "fail", "sin lectura del storage"
    return ("ok" if pct < 80 else "warn" if pct < 90 else "fail"), f"disco storage {pct}% · {libre_gb}GB libres"


def c_host_aux():
    out = ssh(SSH_AUX, "uptime -p")
    return ("ok", f"66 alcanzable ({out})") if out else ("warn", "66 no responde (auxiliar)")


def c_bateria_reciente():
    import glob as g
    runs = sorted(g.glob(os.path.join(os.path.dirname(__file__), "..", "eval", "runs", "bateria_*.json")))
    if not runs:
        return None, None   # sólo aplica donde se corre la batería (la Mac)
    d = json.load(open(runs[-1]))
    # la fecha sale del NOMBRE del archivo (bateria_YYYYmmdd_HHMMSS.json), no del
    # mtime: en CI el checkout es nuevo y el mtime diría "hace 0h" de una
    # corrida de hace semanas.
    m = re.search(r"bateria_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})", runs[-1])
    if not m:
        return None, None
    from datetime import datetime as _dt
    edad_h = (time.time() - _dt(*map(int, m.groups())).timestamp()) / 3600
    nota = f"{d.get('ok')}/{d.get('total')} hace {edad_h:.0f}h"
    return ("ok" if edad_h <= 72 else "warn"), f"batería {nota}"


# ---- main --------------------------------------------------------------------

def correr(sin_ssh: bool = False, full: bool = False) -> list[dict]:
    """Ejecuta todos los chequeos, imprime el reporte y devuelve los resultados."""
    RESULTADOS.clear()
    print("== SALUD AI JUSTICIA ==", datetime.now().strftime("%Y-%m-%d %H:%M %Z"), flush=True)
    check("web aijusticia.mx", c_web)
    check("engine /health + LLM", c_engine_health)
    check("corpus (docs/chunks)", c_corpus)
    check("frescura DOF (cron diario)", c_frescura_dof)
    check("office Nextcloud :8080", c_office, critico=False)
    if not sin_ssh:
        check("servicios 162 (engine/web/pg)", c_servicios_162)
        check(f"OOM recientes ({OOM_HORAS}h)", c_oom_recientes, recordar=False)
        check("mantenimiento nocturno", c_mantenimiento)
        check("disco 162", c_disco_162)
        check("carga 162", c_carga_162)
        check("dump local", c_backup)
        check("réplica off-site", c_backup_offsite)
        check("disco storage", c_disco_storage)
        check("host auxiliar 66", c_host_aux, critico=False)
        check("batería de evaluación", c_bateria_reciente, critico=False)
    if full:
        check("smoke chat /chat/stream", c_chat_stream)
    fails = [r for r in RESULTADOS if r["estado"] == "fail"]
    warns = [r for r in RESULTADOS if r["estado"] == "warn"]
    print(f"\n== {len(RESULTADOS) - len(fails) - len(warns)} ok · {len(warns)} warn · {len(fails)} FAIL ==")
    return list(RESULTADOS)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--full", action="store_true", help="+ smoke del chat (consume tokens)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    res = correr(sin_ssh=os.environ.get("SALUD_SIN_SSH") == "1", full=args.full)
    fails = [r for r in res if r["estado"] == "fail"]
    warns = [r for r in res if r["estado"] == "warn"]
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    sys.exit(2 if fails else (1 if warns else 0))


if __name__ == "__main__":
    main()
