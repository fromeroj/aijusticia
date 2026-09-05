"""Rutas del despacho (bufete): casos, documentos, plantillas, consulta.

Autenticación: JWT con claim bufete (Depends(actor_actual)).
Aislamiento: RLS via set_tenant() en cada query de dossiers.
Documentos: Nextcloud WebDAV del bufete (oficina.konen.guru o on-prem).
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ai_justicia.auth.deps import actor_actual, set_tenant
from ai_justicia.config import settings
from ai_justicia.jobs.cola import encolar
from ai_justicia.pipeline.orchestrator import ejecutar_consulta

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bufetes", tags=["bufetes"])


# ── Helpers ─────────────────────────────────────────────────────────────

def _db():
    import psycopg
    return psycopg.connect(
        host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_db,
        user=settings.pg_user, password=settings.pg_password, autocommit=True)


class NcClient:
    """Cliente WebDAV ligero para Nextcloud del bufete."""

    def __init__(self, base_url: str, user: str, app_password: str):
        self.base = base_url.rstrip("/")
        self.auth = urllib.parse.quote(f"{user}:{app_password}")

    def _url(self, path: str) -> str:
        return f"{self.base}/remote.php/dav/files/{path}"

    def _req(self, method: str, path: str, data: bytes | None = None,
             headers: dict | None = None) -> urllib.request.Request:
        h = {"Authorization": f"Basic {urllib.parse.unquote(self.auth)}"}
        if headers:
            h.update(headers)
        return urllib.request.Request(self._url(path), data=data, headers=h, method=method)

    def list_docx(self, folder: str) -> list[str]:
        """Lista .docx en una carpeta (recursivo 1 nivel)."""
        body = (
            '<?xml version="1.0"?><d:propfind xmlns:d="DAV:">'
            '<d:prop><d:resourcetype/><d:displayname/></d:prop></d:propfind>')
        try:
            req = self._req("PROPFIND", folder,
                            body.encode(), {"Depth": "1", "Content-Type": "application/xml"})
            with urllib.request.urlopen(req, timeout=30) as r:
                xml = r.read().decode()
        except Exception:
            return []
        files = []
        import re
        for m in re.finditer(r"<d:href>([^<]+)</d:href>", xml):
            h = urllib.parse.unquote(m.group(1))
            if h.endswith(".docx"):
                name = h.split("/")[-1]
                prefix = folder.strip("/").split("/")[-1]
                files.append(name)
        return sorted(set(files))

    def mkdir(self, path: str):
        try:
            req = self._req("MKCOL", path)
            urllib.request.urlopen(req, timeout=15)
        except Exception:
            pass  # ya existe

    def upload(self, path: str, blob: bytes, content_type: str = "application/octet-stream"):
        req = self._req("PUT", path, blob, {"Content-Type": content_type})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status

    def download(self, path: str) -> bytes:
        req = self._req("GET", path)
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()


def _nc_del_actor(actor: dict) -> NcClient:
    """NC del despacho — en cloud: oficina.konen.guru; on-prem: URL del bufete."""
    # TODO: del registro del bufete en DB (columna nc_url, nc_user, nc_app_password)
    # por ahora hardcode del cloud pilot:
    return NcClient(
        base_url=bufetes_config()["nc_url"],
        user=actor.get("nc_user", "admin"),
        app_password=actor.get("nc_app_password", ""),
    )


def bufetes_config() -> dict:
    """Config del tier despacho (env vars)."""
    import os
    return {
        "nc_url": os.environ.get("BUFETE_NC_URL", "https://oficina.konen.guru"),
        "nc_user": os.environ.get("BUFETE_NC_USER", ""),
        "nc_app_password": os.environ.get("BUFETE_NC_APP_PASSWORD", ""),
    }


# ── Schemas ─────────────────────────────────────────────────────────────

class CasoCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=200)
    materia: str | None = None
    descripcion: str | None = Field(None, max_length=2000)


class DocumentoGenerate(BaseModel):
    plantilla: str = Field(..., description="Nombre del .docx en /Plantillas/")
    caso_id: str = Field(..., description="UUID del dossier/caso")
    variables: dict[str, str] = Field(default_factory=dict)


class QueryBufete(BaseModel):
    consulta: str = Field(..., min_length=3, max_length=4000)
    caso_id: str | None = Field(None, description="Contexto del caso si aplica")


# ── Rutas ───────────────────────────────────────────────────────────────

@router.get("/casos")
def listar_casos(actor: dict = Depends(actor_actual)):
    """Lista los dossiers del bufete (RLS filtra automáticamente)."""
    if not actor.get("bufete"):
        raise HTTPException(403, "Requiere sesión de despacho")
    with _db() as conn:
        cur = conn.cursor()
        set_tenant(cur, actor["bufete"])
        cur.execute("""
            SELECT id, materia, jurisdiccion, estado, expediente->>'hechos' as hechos,
                   created_at
            FROM dossiers ORDER BY created_at DESC LIMIT 100
        """)
        cols = [d[0] for d in cur.description]
        casos = [dict(zip(cols, r)) for r in cur.fetchall()]
    return {"casos": casos, "total": len(casos)}


@router.post("/casos")
def crear_caso(req: CasoCreate, actor: dict = Depends(actor_actual)):
    """Crea un nuevo caso (dossier) en el bufete."""
    if not actor.get("bufete"):
        raise HTTPException(403, "Requiere sesión de despacho")
    from ai_justicia.dossiers import store as dstore
    # crear el dossier con el ciudadano = actor del despacho
    # y asignarlo al bufete
    with _db() as conn:
        cur = conn.cursor()
        ciudadano_id = uuid.uuid4()
        # crear actor mínimo para el dossier
        cur.execute(
            "INSERT INTO actores (id, es_abogado, frase_hash) VALUES (%s, true, 'bufete-direct')",
            (ciudadano_id,))
        dossier_id = uuid.uuid4()
        expediente = {"nombre": req.nombre, "descripcion": req.descripcion or "", "hechos": {}}
        set_tenant(cur, None)  # INSERT sin RLS (aún no existe)
        cur.execute(
            """INSERT INTO dossiers (id, ciudadano_id, materia, expediente, bufete_id)
               VALUES (%s, %s, %s, %s, %s)""",
            (dossier_id, ciudadano_id, req.materia,
             json.dumps(expediente), uuid.UUID(actor["bufete"])))
    return {"caso_id": str(dossier_id), "nombre": req.nombre}


@router.get("/plantillas")
def listar_plantillas(actor: dict = Depends(actor_actual)):
    """Lista plantillas .docx disponibles en /Plantillas/ del NC del bufete."""
    if not actor.get("bufete"):
        raise HTTPException(403, "Requiere sesión de despacho")
    nc = _nc_del_actor(actor)
    # listar subcarpetas + docx
    plantillas = []
    for subdir in ("", "Mercantil/", "Laboral/", "Civil/", "Familiar/", "Penal/"):
        files = nc.list_docx(f"Plantillas/{subdir}" if subdir else "Plantillas")
        for f in files:
            plantillas.append({"nombre": f, "categoria": subdir.rstrip("/") or "general"})
    return {"plantillas": plantillas}


@router.post("/documentos/generar")
def generar_documento(req: DocumentoGenerate, actor: dict = Depends(actor_actual)):
    """Genera un documento desde plantilla + variables → sube al caso en NC.

    Encola el trabajo (PII-scan + docxtpl + WebDAV upload) para async.
    """
    if not actor.get("bufete"):
        raise HTTPException(403, "Requiere sesión de despacho")
    job_id = encolar("generar_documento", {
        "plantilla": req.plantilla,
        "caso_id": req.caso_id,
        "variables": req.variables,
        "bufete_id": actor["bufete"],
        "actor_id": actor["sub"],
    }, prioridad=2)
    return {"job_id": job_id, "estado": "encolado"}


@router.post("/query")
def consulta_bufete(req: QueryBufete, actor: dict = Depends(actor_actual)):
    """Consulta jurídica anclada con contexto del bufete (Nivel1)."""
    if not actor.get("bufete"):
        raise HTTPException(403, "Requiere sesión de despacho")

    # si hay caso, enriquecer con su expediente
    expediente_prev = None
    if req.caso_id:
        with _db() as conn:
            cur = conn.cursor()
            set_tenant(cur, actor["bufete"])
            cur.execute(
                "SELECT expediente FROM dossiers WHERE id = %s",
                (uuid.UUID(req.caso_id),))
            row = cur.fetchone()
            if row:
                expediente_prev = row[0]

    resultado = ejecutar_consulta(
        req.consulta,
        nivel="Nivel1",
        expediente_prev=expediente_prev,
    )
    return {
        "respuesta": resultado.respuesta,
        "abstenido": resultado.abstenido,
        "pasajes": resultado.pasajes[:5] if resultado.pasajes else [],
        "traza_id": resultado.traza_id,
    }
