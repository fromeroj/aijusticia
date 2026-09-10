"""Rutas de la bóveda de documentos del dossier (F3).

Acceso: JWT + tiene_acceso (dueño o grant de edición para subir;
lectura basta para listar/descargar).
"""
from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ai_justicia.auth.deps import actor_actual

router = APIRouter(tags=["archivos"])


def _uuid_o_400(valor: str) -> _uuid.UUID:
    try:
        return _uuid.UUID(valor)
    except ValueError:
        raise HTTPException(400, "id inválido")


def _nivel(dossier_id, actor) -> str:
    from ai_justicia.dossiers import store as dstore
    nivel = dstore.tiene_acceso(dossier_id, _uuid.UUID(actor["sub"]), actor.get("bufete"))
    if not nivel:
        raise HTTPException(404, "Dossier no encontrado")
    return nivel


@router.post("/dossiers/{dossier_id}/documentos")
async def subir_documento(
    dossier_id: str,
    archivo: UploadFile = File(...),
    version_de: int | None = Form(None),
    actor: dict = Depends(actor_actual),
):
    """Sube un documento a la bóveda del caso. Extrae texto (PDF/OCR).

    version_de: id del documento del que es nueva versión (opcional).
    """
    from ai_justicia.dossiers import boveda
    did = _uuid_o_400(dossier_id)
    if _nivel(did, actor) not in ("dueño", "edicion"):
        raise HTTPException(403, "Se necesita permiso de edición para subir documentos")

    contenido = await archivo.read()
    try:
        doc = boveda.guardar_documento(
            did, _uuid.UUID(actor["sub"]),
            archivo.filename or "documento", contenido,
            archivo.content_type, version_de=version_de)
    except ValueError as e:
        raise HTTPException(413, str(e))
    return doc


@router.get("/dossiers/{dossier_id}/documentos")
def listar_documentos(dossier_id: str, actor: dict = Depends(actor_actual)):
    """Documentos del caso (metadatos; el texto lo consume Izel server-side)."""
    from ai_justicia.dossiers import boveda
    did = _uuid_o_400(dossier_id)
    _nivel(did, actor)
    return {"documentos": boveda.listar_documentos(did)}


@router.get("/documentos/{doc_id}/descargar")
def descargar_documento(doc_id: int, actor: dict = Depends(actor_actual)):
    """Descarga el archivo original. Respeta la preferencia del cliente
    (attachment siempre; el navegador/SO decide si abrir con la app)."""
    from ai_justicia.dossiers import boveda
    doc = boveda.obtener_documento(doc_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")
    _nivel(doc["dossier_id"], actor)
    from pathlib import Path
    ruta = Path(doc["ruta_archivo"])
    if not ruta.exists():
        raise HTTPException(410, "El archivo ya no existe en la bóveda")
    return FileResponse(
        ruta, filename=doc["nombre"],
        media_type=doc["tipo_mime"] or "application/octet-stream")
