"""Worker de la cola SKIP LOCKED para jobs del despacho.

Tipos soportados:
  - generar_documento: descarga plantilla NC → docxtpl → PII-scan → sube al caso
  - pii_scan: escanea documento → detecta PII → reporte
  - promover_plantilla: PII-scan → anonimiza → crea en /Plantillas/

Corre como servicio o en tmux. Uso:
  python -m ai_justicia.jobs.worker_despacho
"""
from __future__ import annotations

import base64
import io
import logging
import re
import time
import urllib.error
import urllib.request
import zipfile

from ai_justicia.config import settings
from ai_justicia.jobs.cola import completar, fallar, stats, tomar

logging.basicConfig(level=settings.log_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("worker_despacho")


# ── Detector PII (reglas mexicanas; Presidio en F2) ─────────────────

PATRONES_PII = [
    ("CURP", re.compile(r"\b[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d\b")),
    ("RFC", re.compile(r"\b[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}\b")),
    ("EMAIL", re.compile(r"\b[\w.-]+@[\w.-]+\.\w+\b")),
    ("TELEFONO", re.compile(r"\b\d{2,3}[- ]?\d{4}[- ]?\d{4}\b")),
    ("FECHA_NAC", re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b")),
    ("CP", re.compile(r"\b\d{5}\b")),
]


def escanear_pii(texto: str) -> list[dict]:
    hallazgos = []
    for tipo, pat in PATRONES_PII:
        for m in pat.finditer(texto):
            hallazgos.append({
                "tipo": tipo,
                "valor": m.group()[:60],
                "inicio": m.start(),
                "replacement": f"[{tipo}]",
            })
    return hallazgos


def anonimizar(texto: str, hallazgos: list[dict]) -> str:
    for h in sorted(hallazgos, key=lambda x: x["inicio"], reverse=True):
        texto = texto[:h["inicio"]] + h["replacement"] + texto[h["inicio"] + len(h["valor"]):]
    return texto


# ── WebDAV helper ─────────────────────────────────────────────────────

def _dav(base: str, user: str, pw: str, method: str, path: str,
         data: bytes | None = None, headers: dict | None = None):
    url = f"{base.rstrip('/')}/remote.php/dav/files/{user}/{path}"
    h = {"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    return urllib.request.urlopen(req, timeout=60)


def _mkdirs(base: str, user: str, pw: str, path: str):
    """Crea la ruta WebDAV segmento a segmento (MKCOL crea un nivel por llamada)."""
    acumulado = ""
    for segmento in [s for s in path.strip("/").split("/") if s]:
        acumulado += segmento
        try:
            with _dav(base, user, pw, "MKCOL", acumulado):
                pass
        except urllib.error.HTTPError as e:
            if e.code != 405:  # 405 = ya existe
                raise
        acumulado += "/"


def _nc_config(payload: dict) -> tuple[str, str, str]:
    """NC del despacho: settings (.env) con override por payload del job."""
    return (
        payload.get("nc_url") or settings.bufete_nc_url,
        payload.get("nc_user") or settings.bufete_nc_user,
        payload.get("nc_app_password") or settings.bufete_nc_app_password,
    )


# ── Procesadores ──────────────────────────────────────────────────────

def procesar_generar_documento(job: dict) -> dict:
    payload = job["payload"]
    plantilla = payload["plantilla"]
    caso_id = payload["caso_id"]
    variables = payload.get("variables", {})
    base, user, pw = _nc_config(payload)

    # 1. descargar plantilla
    with _dav(base, user, pw, "GET", f"Plantillas/{plantilla}") as r:
        tpl_bytes = r.read()

    # 2. reemplazar variables en document.xml
    zf_in, zf_out = io.BytesIO(tpl_bytes), io.BytesIO()
    reemplazos = 0
    with zipfile.ZipFile(zf_in, "r") as zin, zipfile.ZipFile(zf_out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.namelist():
            data = zin.read(item)
            if item == "word/document.xml":
                xml = data.decode("utf-8", errors="replace")
                for k, v in variables.items():
                    # aceptar mayúsculas/minúsculas: la plantilla define {{CLAVE}}
                    for clave in {k, k.upper(), k.lower()}:
                        for ph in (f"{{{{{clave}}}}}", f"{{{{ {clave} }}}}"):
                            if ph in xml:
                                reemplazos += 1
                                xml = xml.replace(ph, v or f"[{clave}]")
                data = xml.encode("utf-8")
            zout.writestr(item, data)

    # 3. PII-scan de lo insertado
    pii = escanear_pii(" ".join(str(v) for v in variables.values()))

    # 4. subir al caso
    fecha = time.strftime("%Y-%m-%d")
    nombre = plantilla.rsplit("/", 1)[-1].replace(".docx", "") + f"_{fecha}.docx"
    _mkdirs(base, user, pw, f"Casos/{caso_id}")
    with _dav(base, user, pw, "PUT", f"Casos/{caso_id}/{nombre}", zf_out.getvalue(),
              {"Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}):
        pass

    return {"archivo": nombre, "ruta": f"/Casos/{caso_id}/{nombre}",
            "variables_reemplazadas": reemplazos, "pii_detectada": len(pii),
            "pii_tipos": list({p["tipo"] for p in pii})}


def procesar_pii_scan(job: dict) -> dict:
    payload = job["payload"]
    base, user, pw = _nc_config(payload)
    with _dav(base, user, pw, "GET", payload["ruta"]) as r:
        doc = r.read()
    with zipfile.ZipFile(io.BytesIO(doc)) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
        texto = re.sub(r"<[^>]+>", " ", xml)
    hallazgos = escanear_pii(texto)
    return {"hallazgos": [{k: v for k, v in h.items() if k != "replacement"} for h in hallazgos[:50]],
            "total": len(hallazgos)}


def procesar_promover_plantilla(job: dict) -> dict:
    """Anonimiza un documento del caso → lo crea como plantilla.

    Dos orígenes: bóveda del engine (boveda_doc_id) o NC (ruta).
    """
    payload = job["payload"]
    base, user, pw = _nc_config(payload)
    if payload.get("boveda_doc_id"):
        from pathlib import Path as _P
        from ai_justicia.dossiers import boveda as _boveda
        doc_row = _boveda.obtener_documento(int(payload["boveda_doc_id"]))
        if not doc_row:
            raise ValueError("Documento de bóveda no encontrado")
        doc = _P(doc_row["ruta_archivo"]).read_bytes()
        nombre_base = doc_row["nombre"]
    else:
        with _dav(base, user, pw, "GET", payload["ruta"]) as r:
            doc = r.read()
        nombre_base = payload["ruta"].rsplit("/", 1)[-1]
    with zipfile.ZipFile(io.BytesIO(doc)) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
        texto = re.sub(r"<[^>]+>", " ", xml)
    hallazgos = escanear_pii(texto)
    xml_anon = anonimizar(xml, hallazgos)  # nota: anonimiza el XML directamente

    # reescribir docx
    zf_out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(doc), "r") as zin, \
         zipfile.ZipFile(zf_out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.namelist():
            data = zin.read(item)
            if item == "word/document.xml":
                data = xml_anon.encode("utf-8")
            zout.writestr(item, data)

    destino = payload.get("destino", "Plantillas/Importadas")
    nombre = nombre_base.replace(".docx", "") + "_anon.docx"
    _mkdirs(base, user, pw, destino)
    with _dav(base, user, pw, "PUT", f"{destino}/{nombre}", zf_out.getvalue(),
              {"Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}):
        pass
    return {"plantilla": f"{destino}/{nombre}", "pii_anonimizada": len(hallazgos)}


PROCESADORES = {
    "generar_documento": procesar_generar_documento,
    "pii_scan": procesar_pii_scan,
    "promover_plantilla": procesar_promover_plantilla,
}


def main():
    worker_id = f"despacho-{int(time.time())}"
    logger.info("Worker despacho iniciado: %s", worker_id)
    vacios = 0
    tipos = list(PROCESADORES)
    while True:
        job = tomar(worker_id, tipos)
        if not job:
            vacios += 1
            if vacios >= 60:
                s = {k: v["n"] for k, v in stats().items()}
                logger.info("Sin jobs. Stats: %s", s)
                vacios = 0
            time.sleep(5)
            continue
        vacios = 0
        logger.info("Job %d: %s (intento %d)", job["id"], job["tipo"], job["intentos"])
        try:
            resultado = PROCESADORES[job["tipo"]](job)
            completar(job["id"], resultado)
            logger.info("Job %d ✓: %s", job["id"], str(resultado)[:120])
        except Exception as e:
            fallar(job["id"], str(e), reintentar=job["intentos"] < 3)
            logger.error("Job %d ✗: %s", job["id"], str(e)[:200])


if __name__ == "__main__":
    main()
