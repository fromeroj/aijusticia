"""Harvest completo de LeyesBiblio (diputados.gob.mx) — corpus federal.

Corre en el SERVER. Descarga el catálogo completo (index.htm), el texto
vigente de cada ley (doc/{CODE}.doc → antiword/unrtf) y la fecha de última
reforma (ref/{code}.htm), e ingresa todo vía upsert_documento_rapido
(chunk FTS, sin embeddings). Idempotente: re-ejecutar refresca.

Uso:  .venv/bin/python scripts/harvest_leyes_federales.py [--solo-faltantes]
"""
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import date

sys.path.insert(0, "/opt/aijusticia/engine")
from ai_justicia.config import settings  # noqa: E402
from ai_justicia.corpus.clean import limpiar_texto  # noqa: E402
from ai_justicia.corpus.models import Documento, Fuente, Jerarquia, Materia  # noqa: E402
from ai_justicia.corpus.store import upsert_documento_rapido  # noqa: E402
import psycopg  # noqa: E402

BASE = "https://www.diputados.gob.mx/LeyesBiblio"
INDEX = f"{BASE}/index.htm"
SOLO_FALTANTES = "--solo-faltantes" in sys.argv

MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
         "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10,
         "noviembre": 11, "diciembre": 12}

MATERIAS = [
    (Materia.CONSTITUCIONAL, ["constituci"]),
    (Materia.AMPARO, ["amparo"]),
    (Materia.LABORAL, ["trabajo", "laboral", "trabajador"]),
    (Materia.PENAL, ["penal", "delito", "tortura", "trata", "secuestro", "extorsi",
                     "armas", "narcomenudeo", "extinción de dominio", "ejecución de penas"]),
    (Materia.FISCAL, ["fiscal", "impuesto", "contribucion", "aduan", "ingresos"]),
    (Materia.MERCANTIL, ["mercantil", "comercio", "comercio", "sociedades", "concurso",
                         "quiebra", "inversión", "inversion", "turismo", "propiedad industrial"]),
    (Materia.FAMILIAR, ["familia", "familiares", "niñas", "niños", "adolescen",
                        "victimas", "víctimas", "derechos de las niñ"]),
    (Materia.AGRARIO, ["agraria", "agrario", "ejidal", "aguas nacionales", "rural"]),
    (Materia.ELECTORAL, ["electoral", "elecciones", "voto", "partidos", "consulta popular"]),
    (Materia.ADMINISTRATIVO, ["administraci", "orgánica", "organica", "procedimiento administrativo",
                              "transparencia", "datos personales", "responsabilidades",
                              "adquisiciones", "obras públicas", "obra pública"]),
    (Materia.CIVIL, ["civil", "obligaciones", "contratos", "arrendam", "propiedad"]),
]


def _materia(nombre: str) -> Materia | None:
    n = nombre.lower()
    for materia, claves in MATERIAS:
        if any(c in n for c in claves):
            return materia
    return None


def _get(url: str, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (educational research)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read() if binary else r.read().decode("iso-8859-1", errors="replace")


def extraer_doc(contenido: bytes) -> str:
    """Extrae texto de un .doc de diputados (probamos antiword → unrtf → decode)."""
    with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as f:
        f.write(contenido)
        ruta = f.name
    try:
        for cmd in (["antiword", "-w", "0", ruta],
                    ["unrtf", "--text", ruta]):
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if r.returncode == 0 and len(r.stdout.strip()) > 200:
                    return r.stdout
            except Exception:
                continue
        return contenido.decode("iso-8859-1", errors="ignore")
    finally:
        import os
        os.unlink(ruta)


def resolver_doc_url(code: str) -> str:
    """Resuelve el .doc real desde la página ref (algunos códigos difieren)."""
    # intento directo primero
    directa = f"{BASE}/doc/{code.upper()}.doc"
    try:
        req = urllib.request.Request(directa, method="HEAD",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            if r.status == 200:
                return directa
    except Exception:
        pass
    # desde la página ref: buscar el enlace al texto vigente
    try:
        html = _get(f"{BASE}/ref/{code}.htm")
        m = re.search(r'href="[^"]*/doc/([^"/]+\.doc)"', html, re.I)
        if not m:
            m = re.search(r'href="(?:\./)?doc/([^"/]+\.doc)"', html, re.I)
        if m:
            return f"{BASE}/doc/{m.group(1)}"
    except Exception:
        pass
    return directa  # que falle con su 404 y quede registrado


def fecha_reforma(code: str) -> date | None:
    try:
        html = _get(f"{BASE}/ref/{code}.htm")
        m = re.search(r"DOF\s+el\s+(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", html, re.I)
        if m and m.group(2).lower() in MESES:
            return date(int(m.group(3)), MESES[m.group(2).lower()], int(m.group(1)))
    except Exception:
        pass
    return None


def main():
    html = _get(INDEX)
    patron = re.compile(
        r'<a\s+href="(?:\./)?(?:ref|doc)/([A-Za-z0-9_ñÑ]+)\.(?:htm|doc)"[^>]*>(.*?)</a>',
        re.I | re.DOTALL)
    limpiar = re.compile(r"<[^>]+>|\s+")
    catalogo: dict[str, str] = {}
    for code, nombre in patron.findall(html):
        nombre = limpiar.sub(" ", nombre).strip()
        if nombre and len(nombre) > 4 and "reformas" not in nombre.lower():
            catalogo.setdefault(code.lower(), nombre)

    # qué hay ya en DB (por código en url_origen)
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT url_origen FROM documentos WHERE fuente='LeyesBiblio'")
            existentes = set()
            for (url,) in cur.fetchall():
                m = re.search(r"/(?:ref|doc)/([A-Za-z0-9_ñÑ]+)\.", url or "", re.I)
                if m:
                    existentes.add(m.group(1).lower())

    cola = [c for c in catalogo if c not in existentes] if SOLO_FALTANTES else list(catalogo)
    print(f"catálogo {len(catalogo)} · a procesar {len(cola)} "
          f"({'solo faltantes' if SOLO_FALTANTES else 'refresco completo'})", flush=True)

    ok = vacio = err = 0
    t0 = time.time()
    for i, code in enumerate(cola, 1):
        nombre = catalogo[code]
        try:
            contenido = _get(resolver_doc_url(code), binary=True)
            texto = limpiar_texto(extraer_doc(contenido)) if len(contenido) > 500 else ""
            if len(texto) < 500:
                vacio += 1
                print(f"[{i}] ✗ sin texto útil: {code} — {nombre[:50]}", flush=True)
            else:
                doc = Documento(
                    fuente=Fuente.LEYES_BIBLIO,
                    titulo=nombre,
                    texto=texto,
                    materia=_materia(nombre),
                    tipo="ley",
                    jerarquia=Jerarquia.LEY_FEDERAL,
                    vinculante=True,
                    url_origen=f"{BASE}/ref/{code}.htm",
                    raw={"code": code},
                )
                doc.fecha_reforma = fecha_reforma(code)
                if not doc.fecha_reforma:
                    m = re.search(r"DOF\s+(\d{2})-(\d{2})-(\d{4})", texto)
                    if m:
                        from datetime import date as _d
                        doc.fecha_reforma = _d(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                upsert_documento_rapido(doc)
                ok += 1
                print(f"[{i}] ✓ {code} — {nombre[:55]} ({len(texto)//1000}k chars)", flush=True)
        except Exception as e:
            err += 1
            print(f"[{i}] ✗ ERROR {code}: {str(e)[:80]}", flush=True)
        time.sleep(0.8)
    print(f"\nFIN: {ok} ingresados, {vacio} sin texto, {err} errores "
          f"({time.time()-t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
