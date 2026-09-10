"""Bóveda de documentos del dossier (F3).

Archivos en filesystem bajo settings.boveda_dir/{dossier_id}/; metadatos y
texto extraído en la tabla dossier_documentos. Todo archivo pasa extracción:
PDF digital → pdftotext; imagen o PDF escaneado → OCR (tesseract, spa+eng).

El texto extraído alimenta el retrieval del caso: Izel puede citarlo.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import uuid
from pathlib import Path

import psycopg

from ai_justicia.config import settings
from ai_justicia.ids import nuevo_id

logger = logging.getLogger(__name__)

TAM_MAX = 15 * 1024 * 1024  # 15 MB

EXT_ES_IMAGEN = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"}
EXT_ES_PDF = {".pdf"}


def _boveda_dir() -> Path:
    d = Path(settings.boveda_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _tesseract() -> str | None:
    return shutil.which("tesseract")


def _pdftotext() -> str | None:
    return shutil.which("pdftotext")


def extraer_texto(ruta: Path, nombre: str) -> tuple[str, str]:
    """Extrae texto de un archivo. Devuelve (texto, metodo).

    PDF digital → pdftotext; si el PDF no tiene capa de texto (escaneado)
    → OCR por página; imagen → OCR directo.
    """
    ext = Path(nombre).suffix.lower()

    if ext in EXT_ES_PDF:
        pdftotext = _pdftotext()
        if pdftotext:
            try:
                r = subprocess.run(
                    [pdftotext, "-l", "60", str(ruta), "-"],
                    capture_output=True, text=True, timeout=120)
                texto = (r.stdout or "").strip()
                if len(texto) > 120:  # tiene capa de texto real
                    return texto, "pdf_digital"
            except Exception as e:
                logger.warning("pdftotext falló para %s: %s", nombre, e)
        # PDF escaneado → OCR (pdftoppm + tesseract por página, máx 30 páginas)
        return _ocr_pdf(ruta, nombre)

    if ext in EXT_ES_IMAGEN:
        return _ocr_imagen(ruta, nombre)

    if ext == ".docx":
        return _extraer_docx(ruta, nombre)

    return "", "sin_texto"


def _extraer_docx(ruta: Path, nombre: str) -> tuple[str, str]:
    """Extrae texto y comentarios de un .docx (zip con word/*.xml)."""
    import re as _re
    import zipfile as _zf
    try:
        with _zf.ZipFile(ruta) as zf:
            nombres = zf.namelist()

            # 1. texto del documento (párrafos de word/document.xml)
            xml = ""
            if "word/document.xml" in nombres:
                raw = zf.read("word/document.xml").decode("utf-8", errors="replace")
                parrafos = []
                for pm in _re.finditer(r"<w:p[ >].*?</w:p>|<w:p/>", raw, _re.S):
                    pxml = pm.group()
                    textos = _re.findall(r"<w:t[^>]*>([^<]*)</w:t>", pxml)
                    ptexto = "".join(textos).strip()
                    if ptexto:
                        parrafos.append(ptexto)
                xml = "\n".join(parrafos)

            if not xml or len(xml) < 50:
                return "", "sin_texto"

            # 2. comentarios inline de Word (word/comments.xml)
            comentarios = []
            if "word/comments.xml" in nombres:
                cxml = zf.read("word/comments.xml").decode("utf-8", errors="replace")
                for cm in _re.finditer(
                    r'<w:comment [^>]*w:author="([^"]*)"[^>]*w:date="([^"]*)"[^>]*>(.*?)</w:comment>',
                    cxml, _re.S
                ):
                    autor, fecha, cuerpo = cm.group(1), cm.group(2), cm.group(3)
                    textos = _re.findall(r"<w:t[^>]*>([^<]*)</w:t>", cuerpo)
                    texto_comentario = "".join(textos).strip()
                    if texto_comentario:
                        fecha_corta = fecha[:10] if fecha else "?"
                        comentarios.append(f"[COMENTARIO de {autor} ({fecha_corta}): {texto_comentario}]")

            resultado = xml
            if comentarios:
                resultado += "\n\n--- COMENTARIOS EN EL DOCUMENTO ---\n" + "\n".join(comentarios)

            metodo = "docx_comentarios" if comentarios else "docx_texto"
            return resultado, metodo

    except Exception as e:
        logger.warning("extraccion docx fallo para %s: %s", nombre, e)
        return "", "sin_texto"


def _ocr_imagen(ruta: Path, nombre: str) -> tuple[str, str]:
    tess = _tesseract()
    if not tess:
        return "", "sin_texto"
    try:
        r = subprocess.run(
            [tess, str(ruta), "-", "-l", "spa+eng", "--psm", "3"],
            capture_output=True, text=True, timeout=120)
        return (r.stdout or "").strip(), "ocr" if r.returncode == 0 else "sin_texto"
    except Exception as e:
        logger.warning("OCR falló para %s: %s", nombre, e)
        return "", "sin_texto"


def _ocr_pdf(ruta: Path, nombre: str) -> tuple[str, str]:
    tess, pdftoppm = _tesseract(), shutil.which("pdftoppm")
    if not (tess and pdftoppm):
        return "", "sin_texto"
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        try:
            subprocess.run(
                [pdftoppm, "-r", "200", "-png", "-l", "30", str(ruta), f"{tmp}/pag"],
                capture_output=True, timeout=300, check=True)
        except Exception as e:
            logger.warning("pdftoppm falló para %s: %s", nombre, e)
            return "", "sin_texto"
        paginas = sorted(Path(tmp).glob("pag-*.png"))
        textos = []
        for pag in paginas:
            r = subprocess.run(
                [tess, str(pag), "-", "-l", "spa+eng", "--psm", "3"],
                capture_output=True, text=True, timeout=180)
            if r.returncode == 0:
                textos.append((r.stdout or "").strip())
        texto = "\n\n".join(t for t in textos if t)
        return (texto, "ocr") if len(texto) > 40 else ("", "sin_texto")


def guardar_documento(
    dossier_id: uuid.UUID,
    actor_id: uuid.UUID,
    nombre: str,
    contenido: bytes,
    tipo_mime: str | None,
    version_de: int | None = None,
    mensaje_cambio: str | None = None,
) -> dict:
    """Guarda archivo + metadatos + texto extraído + mensaje de cambio (commit msg).

    mensaje_cambio: descripción corta de qué cambió respecto a la versión
    anterior — como un "commit message" de git.
    """
    if len(contenido) > TAM_MAX:
        raise ValueError(f"Archivo mayor a {TAM_MAX // (1024 * 1024)} MB")

    nombre = Path(nombre).name[:200] or "documento"
    h = hashlib.sha256(contenido).hexdigest()

    dir_dossier = _boveda_dir() / str(dossier_id)
    dir_dossier.mkdir(parents=True, exist_ok=True)

    version = 1
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            if version_de:
                cur.execute(
                    "SELECT version FROM dossier_documentos WHERE id = %s AND dossier_id = %s",
                    (version_de, dossier_id))
                row = cur.fetchone()
                if not row:
                    raise ValueError("Documento base no encontrado en este caso")
                version = row[0] + 1

            doc_id_tmp = nuevo_id().hex[:12]
    ruta = dir_dossier / f"{doc_id_tmp}_{nombre}"
    ruta.write_bytes(contenido)

    texto, metodo = extraer_texto(ruta, nombre)

    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO dossier_documentos
                   (dossier_id, actor_id, nombre, tipo_mime, tamano_bytes, hash_sha256,
                    version, version_de, ruta_archivo, texto_extraido, metodo_texto, estado, mensaje_cambio)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'listo', %s)
                   RETURNING id, creado_en""",
                (dossier_id, actor_id, nombre, tipo_mime, len(contenido), h,
                 version, version_de, str(ruta), texto or None, metodo,
                 (mensaje_cambio or "").strip()[:500] or None))
            did, creado = cur.fetchone()
            conn.commit()
    logger.info("Documento %s (%s, %d bytes, texto=%s/%d chars) en dossier %s",
                nombre, metodo, len(contenido), metodo, len(texto), dossier_id)
    return {"id": did, "nombre": nombre, "version": version, "version_de": version_de,
            "metodo_texto": metodo, "tamano": len(contenido), "creado_en": creado.isoformat()}


def listar_documentos(dossier_id: uuid.UUID) -> list[dict]:
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT d.id, d.nombre, d.version, d.version_de, d.tipo_mime,
                          d.tamano_bytes, d.metodo_texto, d.creado_en, d.mensaje_cambio,
                          length(coalesce(d.texto_extraido, '')),
                          a.es_abogado
                   FROM dossier_documentos d JOIN actores a ON a.id = d.actor_id
                   WHERE d.dossier_id = %s
                   ORDER BY d.creado_en DESC LIMIT 200""",
                (dossier_id,))
            cols = [c[0] for c in cur.description]
            filas = [dict(zip(cols, r)) for r in cur.fetchall()]
    # fecha como iso
    for f in filas:
        f["creado_en"] = f["creado_en"].isoformat()
    return filas


def obtener_documento(doc_id: int) -> dict | None:
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, dossier_id, nombre, tipo_mime, ruta_archivo, version
                   FROM dossier_documentos WHERE id = %s""", (doc_id,))
            row = cur.fetchone()
    if not row:
        return None
    return {"id": row[0], "dossier_id": row[1], "nombre": row[2],
            "tipo_mime": row[3], "ruta_archivo": row[4], "version": row[5]}


def textos_para_contexto(dossier_id: uuid.UUID, max_chars: int = 8000) -> str:
    """Texto plano de los documentos del caso, para inyectar a Izel."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT nombre, texto_extraido FROM dossier_documentos
                   WHERE dossier_id = %s AND texto_extraido IS NOT NULL
                   ORDER BY creado_en DESC LIMIT 10""",
                (dossier_id,))
            filas = cur.fetchall()
    if not filas:
        return ""
    partes, total = [], 0
    for nombre, texto in filas:
        frag = (texto or "")[:2000]
        parte = f"[Documento: {nombre}]\n{frag}"
        if total + len(parte) > max_chars:
            break
        partes.append(parte)
        total += len(parte)
    return "\n\n".join(partes)
