"""Izel revisa y edita documentos del caso (I4).

Flujo:
  1. Izel recibe: acta completa (texto + comentarios) + notas del caso + consulta
  2. El LLM analiza y propone correcciones con texto nuevo
  3. Se genera un .docx nuevo (versión +1) con los cambios aplicados
  4. Se sube a la bóveda como versión nueva del documento original
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from ai_justicia.config import settings
from ai_justicia.dossiers import boveda, gestion

logger = logging.getLogger(__name__)


PROMPT_REVISION = """Eres Izel, asistente jurídica especializada en derecho mexicano.
Tu tarea es revisar y corregir un documento legal basándote en los comentarios
y notas del caso.

DOCUMENTO ACTUAL (texto completo):
{documento}

COMENTARIOS EN EL DOCUMENTO (si los hay):
{comentarios}

NOTAS DEL CASO (conversación entre las partes):
{notas}

CONSULTA DEL USUARIO:
{consulta}

INSTRUCCIONES:
1. Analiza el documento completo
2. Identifica cada corrección necesaria basándote en los comentarios y notas
3. Genera el TEXTO COMPLETO CORREGIDO del documento
4. Al final, lista los cambios que hiciste en formato:
   CAMBIO 1: [qué cambió y por qué]
   CAMBIO 2: [qué cambió y por qué]

FORMATO DE RESPUESTA:
Primero el documento corregido completo, luego una línea que diga "---CAMBIOS---"
y después la lista de cambios.

Respuesta:"""


def revisar_y_editar(dossier_id: uuid.UUID, doc_id: int,
                     consulta: str, actor_id: uuid.UUID) -> dict:
    """Izel revisa un documento del caso y genera una versión corregida.

    1. Lee el documento (texto extraído + comentarios del Word)
    2. Lee las notas del caso
    3. Envía todo al LLM con instrucciones de revisión
    4. Parsea la respuesta: documento corregido + lista de cambios
    5. Genera un .docx nuevo y lo sube como versión +1
    """
    from ai_justicia.llm.client import get_llm_client

    # 1. leer documento
    doc = boveda.obtener_documento(doc_id)
    if not doc or str(doc["dossier_id"]) != str(dossier_id):
        raise ValueError("Documento no encontrado en este caso")

    # obtener texto extraído de la DB
    import psycopg
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT texto_extraido FROM dossier_documentos WHERE id = %s",
                (doc_id,))
            row = cur.fetchone()
    doc_texto = (row[0] if row and row[0] else "").strip()

    if not doc_texto or len(doc_texto) < 100:
        # re-extraer en caso de que no tenga texto
        ruta = Path(doc["ruta_archivo"])
        if ruta.exists():
            doc_texto, _ = boveda.extraer_texto(ruta, doc["nombre"])
            # actualizar en DB
            with psycopg.connect(settings.psycopg_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE dossier_documentos SET texto_extraido=%s, metodo_texto=%s WHERE id=%s",
                        (doc_texto, "docx_reextract", doc_id))
                conn.commit()

    if not doc_texto or len(doc_texto) < 100:
        raise ValueError("El documento no tiene texto extraíble")

    # separar comentarios del texto si están embebidos
    comentarios = ""
    if "--- COMENTARIOS EN EL DOCUMENTO ---" in doc_texto:
        partes = doc_texto.split("--- COMENTARIOS EN EL DOCUMENTO ---")
        doc_texto = partes[0].strip()
        comentarios = partes[1].strip() if len(partes) > 1 else ""

    # 2. leer notas del caso
    notas_raw = gestion.listar_notas(dossier_id)
    notas_fmt = "\n".join(
        f"[{n['autor']}]: {n['texto'][:300]}" for n in notas_raw[-10:]
    ) or "(sin notas)"

    # 3. enviar al LLM
    prompt = PROMPT_REVISION.format(
        documento=doc_texto[:60000],  # 60K chars max ~ 15K tokens
        comentarios=comentarios[:5000] or "(sin comentarios en el documento)",
        notas=notas_fmt[:8000],
        consulta=consulta[:2000],
    )

    client = get_llm_client()
    respuesta = client.chat(
        [{"role": "user", "content": prompt}],
        max_tokens=32000,
        temperature=0.1,
    )

    # 4. parsear respuesta
    doc_corregido = respuesta
    cambios = ""
    if "---CAMBIOS---" in respuesta:
        partes = respuesta.split("---CAMBIOS---", 1)
        doc_corregido = partes[0].strip()
        cambios = partes[1].strip()

    # 5. generar .docx nuevo (versión +1)
    import io
    import zipfile as zf

    # crear un .docx simple con el texto corregido
    buffer = io.BytesIO()
    with zf.ZipFile(buffer, "w", zf.ZIP_DEFLATED) as z:
        # contenido mínimo de un .docx
        z.writestr("[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>')
        z.writestr("_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
        # convertir texto plano a XML de Word (párrafos)
        parrafos_xml = ""
        for linea in doc_corregido.split("\n"):
            if linea.strip():
                texto_escaped = (linea.strip()
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;"))
                parrafos_xml += f'<w:p><w:r><w:t xml:space="preserve">{texto_escaped}</w:t></w:r></w:p>'
        z.writestr("word/document.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body>{parrafos_xml}</w:body></w:document>')

    contenido = buffer.getvalue()

    # subir como versión nueva
    nombre_original = doc["nombre"]
    nombre_nuevo = nombre_original.replace(".docx", "") + "_izel.docx"
    nuevo_doc = boveda.guardar_documento(
        dossier_id, actor_id, nombre_nuevo, contenido,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        version_de=doc_id,
        mensaje_cambio=cambios[:500] if cambios else f"Revisión de Izel: {consulta[:200]}",
    )

    # guardar nota del caso con los cambios
    gestion.crear_nota(
        dossier_id, actor_id,
        f"[Izel] Revisé el documento y generé {nombre_nuevo} (v{nuevo_doc['version']}).\n"
        f"Cambios aplicados:\n{cambios[:2000]}"
    )

    return {
        "documento_id": nuevo_doc["id"],
        "archivo": nombre_nuevo,
        "version": nuevo_doc["version"],
        "version_de": doc_id,
        "cambios": cambios[:3000],
        "respuesta_completa": respuesta[:10000],
    }
