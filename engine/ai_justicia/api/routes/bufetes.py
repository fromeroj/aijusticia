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
from ai_justicia.ids import nuevo_id
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
        self.user = user
        import base64
        self._b64 = base64.b64encode(f"{user}:{app_password}".encode()).decode()

    def _url(self, path: str) -> str:
        import urllib.parse as _up
        return f"{self.base}/remote.php/dav/files/{_up.quote(self.user)}/{_up.quote(path)}"

    def _req(self, method: str, path: str, data: bytes | None = None,
             headers: dict | None = None) -> urllib.request.Request:
        h = {"Authorization": f"Basic {self._b64}"}
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
    """NC del despacho — en cloud: oficina.konen.guru; on-prem: URL del bufete.
    El actor JWT no carga credenciales: siempre resuelve contra la config del bufete."""
    cfg = bufetes_config()
    return NcClient(
        base_url=cfg["nc_url"],
        user=actor.get("nc_user") or cfg["nc_user"],
        app_password=actor.get("nc_app_password") or cfg["nc_app_password"],
    )


def bufetes_config() -> dict:
    """Config del tier despacho (settings/.env)."""
    return {
        "nc_url": settings.bufete_nc_url,
        "nc_user": settings.bufete_nc_user,
        "nc_app_password": settings.bufete_nc_app_password,
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
    """Casos visibles para ESTE miembro (modelo day-1, E1).

    Regla: en lo de la firma (propios ∪ compartidos a la firma) se ve
    (siendo admin) todo lo NO confidencial, o lo que esté asignado a mí.
    Los compartidos a MI persona directamente, siempre.
    """
    if not actor.get("bufete"):
        raise HTTPException(403, "Requiere sesión de despacho")
    import psycopg
    from ai_justicia.config import settings
    aid = uuid.UUID(actor["sub"])
    bid = uuid.UUID(actor["bufete"])
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT rol FROM bufete_miembros
                   WHERE bufete_id = %s AND actor_id = %s AND estado='activo'""",
                (bid, aid))
            row = cur.fetchone()
            if not row:
                raise HTTPException(403, "No eres miembro activo de esta firma")
            es_admin = row[0] == "admin"

            # visibilidad dentro de la firma: admin ve no-confidenciales;
            # cualquier miembro ve sus asignados (el muro ético tumba asignaciones)
            if es_admin:
                visib = """(d.confidencial = FALSE OR EXISTS (
                            SELECT 1 FROM caso_asignaciones z
                            WHERE z.dossier_id = d.id AND z.actor_id = %(a)s
                              AND z.revocada_en IS NULL))"""
            else:
                visib = """EXISTS (SELECT 1 FROM caso_asignaciones z
                            WHERE z.dossier_id = d.id AND z.actor_id = %(a)s
                              AND z.revocada_en IS NULL)"""
            sel = """SELECT d.id, d.materia, d.jurisdiccion, d.estado, d.confidencial,
                            d.expediente->>'nombre' as nombre,
                            d.expediente->>'hechos' as hechos, d.created_at"""

            casos = []
            # 1. propios de la org
            cur.execute(
                f"""{sel} FROM dossiers d
                    WHERE d.bufete_id = %(b)s AND {visib}
                    ORDER BY d.created_at DESC LIMIT 100""",
                {"a": aid, "b": bid})
            cols = [c[0] for c in cur.description]
            for r in cur.fetchall():
                c = dict(zip(cols, r)); c["origen"] = "propio"; casos.append(c)
            # 2. compartidos a la firma
            cur.execute(
                f"""{sel} FROM dossiers d
                    WHERE d.bufete_id IS NULL AND EXISTS (
                        SELECT 1 FROM dossier_accesos g
                        WHERE g.dossier_id = d.id AND g.revocado_en IS NULL
                          AND g.bufete_id = %(b)s)
                      AND {visib}
                    ORDER BY d.created_at DESC LIMIT 100""",
                {"a": aid, "b": bid})
            for r in cur.fetchall():
                c = dict(zip(cols, r)); c["origen"] = "compartido"; casos.append(c)
            # 3. compartidos a MI persona (grants directos, cualquier relación)
            cur.execute(
                f"""SELECT DISTINCT ON (d.id) d.id, d.materia, d.jurisdiccion, d.estado, d.confidencial,
                    d.expediente->>'nombre' as nombre,
                    d.expediente->>'hechos' as hechos, d.created_at, g.relacion, g.rol as rol_acceso
                    FROM dossiers d
                    JOIN dossier_accesos g ON g.dossier_id = d.id
                         AND g.revocado_en IS NULL AND g.actor_id = %(a)s
                    ORDER BY d.id, CASE g.rol WHEN 'edicion' THEN 0 ELSE 1 END,
                             d.created_at DESC
                    LIMIT 100""",
                {"a": aid})
            cols3 = [c[0] for c in cur.description]
            for r in cur.fetchall():
                c = dict(zip(cols3, r))
                c["origen"] = "compartido"; c["via"] = "persona"; casos.append(c)
    casos.sort(key=lambda c: c["created_at"], reverse=True)
    return {"casos": casos, "total": len(casos), "es_admin": es_admin}


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
        ciudadano_id = nuevo_id()
        # crear actor mínimo para el dossier
        cur.execute(
            "INSERT INTO actores (id, es_abogado, frase_hash) VALUES (%s, true, 'bufete-direct')",
            (ciudadano_id,))
        dossier_id = nuevo_id()
        expediente = {"nombre": req.nombre, "descripcion": req.descripcion or "", "hechos": {}}
        set_tenant(cur, None)  # INSERT sin RLS (aún no existe)
        cur.execute(
            """INSERT INTO dossiers (id, ciudadano_id, materia, expediente, bufete_id)
               VALUES (%s, %s, %s, %s, %s)""",
            (dossier_id, ciudadano_id, req.materia,
             json.dumps(expediente), uuid.UUID(actor["bufete"])))
    # E1: quien crea el caso queda asignado como responsable
    from ai_justicia.dossiers import store as dstore
    dstore.asignar_caso(dossier_id, uuid.UUID(actor["bufete"]),
                        uuid.UUID(actor["sub"]), "responsable",
                        asignado_por=uuid.UUID(actor["sub"]))
    return {"caso_id": str(dossier_id), "nombre": req.nombre}


# ── Gestión interna del caso (E1): equipo, vetos, confidencial, miembros ───

def _admin_firma(actor: dict) -> uuid.UUID:
    if not actor.get("bufete"):
        raise HTTPException(403, "Requiere sesión de despacho")
    from ai_justicia.dossiers import store as dstore
    rol = dstore.rol_en_bufete(uuid.UUID(actor["bufete"]), uuid.UUID(actor["sub"]))
    if rol != "admin":
        raise HTTPException(403, "Solo un socio/admin de la firma puede hacer esto")
    return uuid.UUID(actor["bufete"])


class AsignarRequest(BaseModel):
    actor_id: str
    rol_en_caso: str = "abogado"


@router.post("/casos/{caso_id}/asignaciones")
def asignar_miembro(caso_id: str, req: AsignarRequest, actor: dict = Depends(actor_actual)):
    """Admin de la firma asigna un miembro al caso (muro ético se respeta)."""
    from ai_justicia.dossiers import store as dstore
    bid = _admin_firma(actor)
    cid = uuid.UUID(caso_id)
    if not dstore.es_admin_caso(cid, uuid.UUID(actor["sub"]), actor.get("bufete")):
        # la firma debe tener acceso al caso (propio o compartido a la firma)
        raise HTTPException(403, "Tu firma no gestiona este caso")
    try:
        aid = dstore.asignar_caso(cid, bid, uuid.UUID(req.actor_id), req.rol_en_caso,
                                  asignado_por=uuid.UUID(actor["sub"]))
    except PermissionError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"asignacion_id": aid}


@router.delete("/casos/{caso_id}/asignaciones/{asignacion_id}")
def quitar_asignacion(caso_id: str, asignacion_id: str,
                      actor: dict = Depends(actor_actual)):
    """Admin quita la asignación; el asignado puede irse él mismo."""
    from ai_justicia.dossiers import store as dstore
    if not actor.get("bufete"):
        raise HTTPException(403, "Requiere sesión de despacho")
    ok = dstore.revocar_asignacion(uuid.UUID(caso_id), asignacion_id,
                                   uuid.UUID(actor["sub"]))
    if not ok:
        raise HTTPException(404, "Asignación no encontrada o sin permiso")
    return {"ok": True}


class VetoRequest(BaseModel):
    actor_id: str
    razon: str | None = None


@router.post("/casos/{caso_id}/vetos")
def vetar_miembro(caso_id: str, req: VetoRequest, actor: dict = Depends(actor_actual)):
    """Muro ético: el vetado no puede ver NI ser asignado al caso (bloqueo absoluto)."""
    from ai_justicia.dossiers import store as dstore
    bid = _admin_firma(actor)
    ok = dstore.vetar(uuid.UUID(caso_id), bid, uuid.UUID(req.actor_id),
                      uuid.UUID(actor["sub"]), req.razon)
    return {"ok": ok}


@router.delete("/casos/{caso_id}/vetos/{actor_id}")
def quitar_veto_ep(caso_id: str, actor_id: str, actor: dict = Depends(actor_actual)):
    from ai_justicia.dossiers import store as dstore
    _admin_firma(actor)
    ok = dstore.quitar_veto(uuid.UUID(caso_id), uuid.UUID(actor_id))
    if not ok:
        raise HTTPException(404, "Veto no encontrado")
    return {"ok": True}


class ConfidencialRequest(BaseModel):
    valor: bool


@router.post("/casos/{caso_id}/confidencial")
def toggle_confidencial(caso_id: str, req: ConfidencialRequest,
                        actor: dict = Depends(actor_actual)):
    """Caso confidencial: solo los asignados lo ven (ni los demás admins)."""
    from ai_justicia.dossiers import store as dstore
    _admin_firma(actor)
    cid = uuid.UUID(caso_id)
    if not dstore.es_admin_caso(cid, uuid.UUID(actor["sub"]), actor.get("bufete")):
        raise HTTPException(403, "Tu firma no gestiona este caso")
    dstore.marcar_confidencial(cid, req.valor)
    return {"ok": True, "confidencial": req.valor}


@router.get("/miembros")
def miembros_ep(actor: dict = Depends(actor_actual)):
    """Miembros de la firma con sus roles (cualquier miembro los ve)."""
    if not actor.get("bufete"):
        raise HTTPException(403, "Requiere sesión de despacho")
    from ai_justicia.dossiers import store as dstore
    return {"miembros": dstore.listar_miembros(uuid.UUID(actor["bufete"]))}


class RolRequest(BaseModel):
    actor_id: str
    rol: str


@router.post("/miembros/rol")
def cambiar_rol_ep(req: RolRequest, actor: dict = Depends(actor_actual)):
    from ai_justicia.dossiers import store as dstore
    _admin_firma(actor)
    ok = dstore.cambiar_rol_miembro(uuid.UUID(actor["bufete"]),
                                    uuid.UUID(req.actor_id), req.rol,
                                    uuid.UUID(actor["sub"]))
    if not ok:
        raise HTTPException(404, "Miembro no encontrado")
    return {"ok": True}


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


@router.get("/jobs/{job_id}")
def estado_job(job_id: int, actor: dict = Depends(actor_actual)):
    """Estado de un job de la cola del despacho (aislado por bufete del payload)."""
    if not actor.get("bufete"):
        raise HTTPException(403, "Requiere sesión de despacho")
    with _db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, tipo, estado, intentos, resultado, ultimo_error, payload->>'bufete_id' "
            "FROM cola_jobs WHERE id = %s", (job_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Job no encontrado")
    if row[6] and row[6] != actor["bufete"]:
        raise HTTPException(403, "Job de otro despacho")
    return {
        "job_id": row[0], "tipo": row[1], "estado": row[2], "intentos": row[3],
        "resultado": row[4], "error": row[5],
    }


@router.get("/plantillas/variables")
def plantilla_variables(nombre: str, actor: dict = Depends(actor_actual)):
    """Extrae las variables {{CLAVE}} de una plantilla .docx (server-side)."""
    if not actor.get("bufete"):
        raise HTTPException(403, "Requiere sesión de despacho")
    if ".." in nombre or nombre.startswith("/"):
        raise HTTPException(400, "Ruta inválida")
    nc = _nc_del_actor(actor)
    try:
        blob = nc.download(f"Plantillas/{nombre}")
    except Exception:
        raise HTTPException(404, f"Plantilla no encontrada: {nombre}")
    import io
    import re as _re
    import zipfile
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    except Exception:
        raise HTTPException(422, "El archivo no es un .docx válido")
    # placeholders pueden quedar cortados por runs de Word: unir texto plano también
    texto = _re.sub(r"<[^>]+>", "", xml)
    encontradas = set(_re.findall(r"\{\{\s*([A-Za-zÁÉÍÓÚÑáéíóúñ_][A-Za-z0-9ÁÉÍÓÚÑáéíóúñ_]*)\s*\}\}", xml))
    encontradas |= set(_re.findall(r"\{\{\s*([A-Za-zÁÉÍÓÚÑáéíóúñ_][A-Za-z0-9ÁÉÍÓÚÑáéíóúñ_]*)\s*\}\}", texto))
    return {"variables": sorted(encontradas)}


@router.post("/query")
def consulta_bufete(req: QueryBufete, actor: dict = Depends(actor_actual)):
    """Consulta jurídica anclada con contexto del bufete (Nivel1)."""
    if not actor.get("bufete"):
        raise HTTPException(403, "Requiere sesión de despacho")

    # si hay caso, enriquecer la consulta con su expediente + bóveda
    consulta_final = req.consulta
    if req.caso_id:
        from ai_justicia.dossiers import store as dstore
        try:
            cid = uuid.UUID(req.caso_id)
        except ValueError:
            raise HTTPException(400, "caso_id inválido")
        nivel = dstore.tiene_acceso(cid, uuid.UUID(actor["sub"]), actor.get("bufete"))
        if not nivel:
            raise HTTPException(404, "Caso no encontrado")
        with _db() as conn:
            cur = conn.cursor()
            set_tenant(cur, None)  # casos compartidos: el gate ES el grant, no RLS
            cur.execute(
                "SELECT expediente FROM dossiers WHERE id = %s", (cid,))
            row = cur.fetchone()
            if row and row[0] and isinstance(row[0], dict) and any(row[0].values()):
                contexto = "; ".join(
                    f"{k}: {v}" for k, v in row[0].items()
                    if isinstance(v, str) and v.strip())[:1500]
                if contexto:
                    consulta_final = f"Contexto del caso: {contexto}\n\nConsulta: {req.consulta}"
        # F3: documentos de la bóveda del caso — Izel los cita
        from ai_justicia.dossiers import boveda
        docs = boveda.textos_para_contexto(cid)
        if docs:
            consulta_final = (
                f"{consulta_final}\n\nDocumentos adjuntos del caso "
                f"(subidos al expediente):\n{docs}")

    resultado = ejecutar_consulta(consulta_final, nivel="Nivel1")
    return {
        "respuesta": resultado.respuesta,
        "abstenido": resultado.abstenido,
        "pasajes": resultado.pasajes[:5] if resultado.pasajes else [],
        "traza_id": resultado.traza_id,
    }


# ── Gestión del caso (U2): notas, timeline, documentos, promoción ──────────

def _acceso_caso(caso_id: str, actor: dict, minimo: str = "lectura"):
    from ai_justicia.dossiers import store as dstore
    import uuid as _u
    cid = _u.UUID(caso_id)
    nivel = dstore.tiene_acceso(cid, _u.UUID(actor["sub"]), actor.get("bufete"))
    orden = {"lectura": 0, "edicion": 1, "dueño": 2}
    if not nivel or orden[nivel] < orden[minimo]:
        raise HTTPException(403, "Sin acceso suficiente al caso")
    return cid


class NotaRequest(BaseModel):
    texto: str = Field(..., min_length=1, max_length=2000)


@router.post("/casos/{caso_id}/notas")
def crear_nota_ep(caso_id: str, req: NotaRequest, actor: dict = Depends(actor_actual)):
    """Nota del caso con autor visible (colaboración entre partes/asesores)."""
    from ai_justicia.dossiers import gestion
    import uuid as _u
    cid = _acceso_caso(caso_id, actor)
    nid = gestion.crear_nota(cid, _u.UUID(actor["sub"]), req.texto)
    return {"nota_id": nid}


@router.get("/casos/{caso_id}/notas")
def listar_notas_ep(caso_id: str, actor: dict = Depends(actor_actual)):
    from ai_justicia.dossiers import gestion
    cid = _acceso_caso(caso_id, actor)
    return {"notas": gestion.listar_notas(cid)}


@router.delete("/casos/{caso_id}/notas/{nota_id}")
def borrar_nota_ep(caso_id: str, nota_id: str, actor: dict = Depends(actor_actual)):
    from ai_justicia.dossiers import gestion
    import uuid as _u
    cid = _acceso_caso(caso_id, actor)
    if not gestion.borrar_nota(cid, nota_id, _u.UUID(actor["sub"])):
        raise HTTPException(404, "Nota no encontrada (solo su autor puede borrarla)")
    return {"ok": True}


@router.get("/casos/{caso_id}/timeline")
def timeline_ep(caso_id: str, actor: dict = Depends(actor_actual)):
    """Historia viva del caso: creación, documentos, accesos, asignaciones, notas."""
    from ai_justicia.dossiers import gestion
    cid = _acceso_caso(caso_id, actor)
    return {"eventos": gestion.timeline(cid)}


@router.get("/casos/{caso_id}/documentos")
def documentos_caso_ep(caso_id: str, actor: dict = Depends(actor_actual)):
    """Documentos de la bóveda del caso (acceso por grant/asignación)."""
    from ai_justicia.dossiers import boveda
    cid = _acceso_caso(caso_id, actor)
    return {"documentos": boveda.listar_documentos(cid)}


@router.post("/casos/{caso_id}/documentos/{doc_id}/promover")
def promover_plantilla_ep(caso_id: str, doc_id: int, actor: dict = Depends(actor_actual)):
    """Promueve un documento del caso a PLANTILLA: PII-scan → anonimiza → /Plantillas/."""
    if not actor.get("bufete"):
        raise HTTPException(403, "Requiere sesión de despacho")
    from ai_justicia.dossiers import boveda
    _acceso_caso(caso_id, actor)  # lectura basta: el PII-scan anonimiza
    doc = boveda.obtener_documento(doc_id)
    if not doc or str(doc["dossier_id"]) != caso_id:
        raise HTTPException(404, "Documento no encontrado en este caso")
    job_id = encolar("promover_plantilla", {
        "boveda_doc_id": doc_id,
        "dossier_id": caso_id,
        "bufete_id": actor["bufete"],
        "actor_id": actor["sub"],
        "destino": "Plantillas/Importadas",
    }, prioridad=3)
    return {"job_id": job_id, "estado": "encolado"}


# ── Invitaciones de membresía a la firma ───────────────────────────────────

class InvitarMiembroRequest(BaseModel):
    rol: str = "abogado"


@router.post("/miembros/invitacion")
def invitar_miembro_ep(req: InvitarMiembroRequest, actor: dict = Depends(actor_actual)):
    """Admin genera código de invitación para que un abogado se una a la firma."""
    from ai_justicia.dossiers import gestion
    import uuid as _u
    _admin_firma(actor)
    if req.rol not in ("abogado", "pasante", "admin"):
        raise HTTPException(400, "rol inválido")
    inv = gestion.crear_invitacion_miembro(
        _u.UUID(actor["bufete"]), _u.UUID(actor["sub"]), req.rol)
    inv["url"] = f"https://aijusticia.mx/unirse?c={inv['codigo']}"
    return inv


class UnirseRequest(BaseModel):
    codigo: str = Field(..., min_length=6, max_length=12)


@router.post("/miembros/unirse")
def unirse_ep(req: UnirseRequest, actor: dict = Depends(actor_actual)):
    """Un abogado canjea el código y entra a la firma.

    Devuelve par JWT NUEVO: el claim bufete del token anterior apunta a la
    firma individual vieja y quedaría obsoleto.
    """
    from ai_justicia.dossiers import gestion
    import datetime
    import uuid as _u
    from ai_justicia.auth.jwt import par_tokens, hash_refresh
    r = gestion.unirse_con_codigo(req.codigo.strip(), _u.UUID(actor["sub"]))
    if not r.get("ok"):
        raise HTTPException(400, r.get("error", "Código no válido"))
    tokens = par_tokens(actor["sub"], "abogado", r["bufete_id"], r.get("rol"))
    import psycopg
    conn = psycopg.connect(host=settings.pg_host, port=settings.pg_port,
                           dbname=settings.pg_db, user=settings.pg_user, password=settings.pg_password)
    cur = conn.cursor()
    cur.execute("INSERT INTO refresh_tokens (actor_id, token_hash, expires_at) VALUES (%s, %s, %s)",
                (_u.UUID(tokens["actor_id"]), hash_refresh(tokens["refresh_token"]),
                 datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)))
    conn.commit(); conn.close()
    r.update(tokens)
    return r


@router.post("/casos/{caso_id}/documentos/{doc_id}/abrir")
def abrir_documento_ep(caso_id: str, doc_id: int, actor: dict = Depends(actor_actual)):
    """Abre un documento en Collabora (via Nextcloud) — URL DIRECTA del editor.

    1. Sube el archivo de la bóveda a /Casos/{id}/ del NC (si hace falta)
    2. Obtiene el fileId de NC via PROPFIND
    3. Crea un share link interno via OCS
    4. Devuelve la URL que abre el EDITOR directo (no el file manager)
    """
    if not actor.get("bufete"):
        raise HTTPException(403, "Requiere sesión de despacho")
    from pathlib import Path
    from ai_justicia.dossiers import boveda
    _acceso_caso(caso_id, actor)

    doc = boveda.obtener_documento(doc_id)
    if not doc or str(doc["dossier_id"]) != caso_id:
        raise HTTPException(404, "Documento no encontrado en este caso")

    ruta = Path(doc["ruta_archivo"])
    if not ruta.exists():
        raise HTTPException(410, "El archivo ya no existe en la bóveda")

    nc = _nc_del_actor(actor)
    nombre = doc["nombre"]
    nc.mkdir(f"Casos/{caso_id}")  # best-effort (405 si ya existe)
    nc.upload(f"Casos/{caso_id}/{nombre}", ruta.read_bytes(),
              doc["tipo_mime"] or "application/octet-stream")

    # crear share link público con edición → abre Collabora sin login NC
    share_url = None
    try:
        import urllib.request as _ureq
        import json as _json
        import base64 as _b64
        share_body = _json.dumps({
            "path": f"/Casos/{caso_id}/{nombre}",
            "shareType": 3,       # public link
            "permissions": 3,     # read + update (editar)
        }).encode()
        share_req = _ureq.Request(
            f"{nc.base}/ocs/v2.php/apps/files_sharing/api/v1/shares?format=json",
            data=share_body, method="POST", headers={
                "Authorization": f"Basic {nc._b64}",
                "OCS-APIRequest": "true",
                "Content-Type": "application/json",
            })
        with _ureq.urlopen(share_req, timeout=15) as sr:
            sdata = _json.loads(sr.read())
            share_url = sdata.get("ocs", {}).get("data", {}).get("url")
    except Exception:
        pass

    # la URL del share abre directamente en Collabora para .docx
    return {
        "editor_url": share_url or f"{nc.base}/apps/files/?dir=/Casos/{caso_id}&openfile=true",
        "nc_url": f"{nc.base}/apps/files/?dir=/Casos/{caso_id}",
        "archivo": nombre,
    }


class RevisionRequest(BaseModel):
    caso_id: str
    documento_id: int
    consulta: str = Field(..., min_length=5, max_length=2000,
                          description="Qué corregir / qué dijo el revisor")


@router.post("/casos/{caso_id}/documentos/{doc_id}/revisar")
def revisar_documento(caso_id: str, doc_id: int, req: RevisionRequest,
                      actor: dict = Depends(actor_actual)):
    """Izel revisa un documento y genera una versión corregida.

    Recibe el texto completo del documento + comentarios del Word + notas
    del caso, y el LLM genera el documento corregido + lista de cambios.
    El resultado se guarda como versión nueva en la bóveda.
    """
    if not actor.get("bufete"):
        raise HTTPException(403, "Requiere sesión de despacho")
    import uuid as _u
    from ai_justicia.dossiers import revision
    _acceso_caso(caso_id, actor, minimo="edicion")

    try:
        resultado = revision.revisar_y_editar(
            _u.UUID(caso_id), doc_id,
            req.consulta, _u.UUID(actor["sub"]))
        return resultado
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"Error en la revisión: {str(e)[:200]}")


# ── Chat de Izel por caso (persistente, visible a participantes) ──────────

@router.get("/casos/{caso_id}/chat")
def chat_caso(caso_id: str, actor: dict = Depends(actor_actual)):
    """Historial completo del chat de Izel para este caso."""
    from ai_justicia.dossiers import chat, store as dstore
    import uuid as _u
    cid = _u.UUID(caso_id)
    if not dstore.tiene_acceso(cid, _u.UUID(actor["sub"]), actor.get("bufete")):
        raise HTTPException(404, "Dossier no encontrado")
    return {"mensajes": chat.listar(cid)}


class ChatMsgRequest(BaseModel):
    rol: str = Field(..., description="user | izel")
    texto: str = Field(..., max_length=8000)
    citas: list | None = None


@router.post("/casos/{caso_id}/chat")
def guardar_chat(caso_id: str, req: ChatMsgRequest, actor: dict = Depends(actor_actual)):
    """Guarda un mensaje del chat (user o izel)."""
    from ai_justicia.dossiers import chat, store as dstore
    import uuid as _u
    cid = _u.UUID(caso_id)
    if not dstore.tiene_acceso(cid, _u.UUID(actor["sub"]), actor.get("bufete")):
        raise HTTPException(404, "Dossier no encontrado")
    mid = chat.guardar(cid, req.rol, req.texto,
                       _u.UUID(actor["sub"]) if req.rol == "user" else None,
                       req.citas)
    return {"msg_id": mid}


class StudioQueryRequest(BaseModel):
    consulta: str = Field(..., min_length=1, max_length=4000)
    caso_id: str | None = None


@router.post("/studio/query")
def studio_query(req: StudioQueryRequest, actor: dict = Depends(actor_actual)):
    """Query agéntico: Izel puede llamar tools para ejecutar acciones."""
    from ai_justicia.tools.agent import agentic_query
    from ai_justicia.tools.registry import ToolContext
    from ai_justicia.dossiers import boveda, store as dstore, gestion, chat
    import uuid as _u
    import asyncio as _aio

    aid = _u.UUID(actor["sub"])
    bid = _u.UUID(actor["bufete"]) if actor.get("bufete") else None

    ctx = ToolContext(
        actor_id=actor["sub"],
        bufete_id=actor.get("bufete"),
        rol=actor.get("rol"),
        nombre=actor.get("nc_user") or actor.get("email") or "usuario",
    )

    contexto = ""
    if req.caso_id:
        try:
            cid = _u.UUID(req.caso_id)
            nivel = dstore.tiene_acceso(cid, aid, actor.get("bufete"))
            if nivel:
                docs = boveda.textos_para_contexto(cid)
                if docs:
                    contexto = f"Caso: {req.caso_id}\nDocumentos:\n{docs[:2000]}"
                notas = gestion.listar_notas(cid)
                if notas:
                    contexto += "\nNotas:\n" + "\n".join(n["texto"][:100] for n in notas[-5:])
        except Exception:
            pass

    loop = _aio.new_event_loop()
    try:
        resultado = loop.run_until_complete(
            agentic_query(req.consulta, ctx, contexto))
    finally:
        loop.close()

    if req.caso_id:
        try:
            chat.guardar(_u.UUID(req.caso_id), "user", req.consulta, aid)
            chat.guardar(_u.UUID(req.caso_id), "izel", resultado["respuesta"])
        except Exception:
            pass

    return resultado
