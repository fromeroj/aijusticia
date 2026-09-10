"""Rutas de dossiers (casos), consentimiento y registro de abogados.

Seguridad (S3):
  - POST /dossiers y /abogados/registro: anónimos por diseño (registro).
  - GET /dossiers/{id} y consentimiento: exigen JWT; el consentimiento
    SOLO el dueño (un abogado con grant no decide el entrenamiento).
  - /auth/dispositivo/registrar exige prueba de posesión (JWT propio o frase).
"""
from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ai_justicia.auth.deps import actor_actual

router = APIRouter(tags=["dossiers"])

class DossierCreateRequest(BaseModel):
    """Crear ciudadano anónimo + su primer dossier. La frase se muestra UNA vez."""
    pass


class ConsentimientoRequest(BaseModel):
    otorgar: bool = Field(..., description="True = consentir entrenamiento general, False = revocar")




@router.post("/dossiers")
def crear_dossier_ep(_: DossierCreateRequest | None = None):
    """Crea ciudadano anónimo + dossier. Devuelve la frase de recuperación UNA vez.

    El cliente debe mostrarla inmediatamente y nunca reenviarla al servidor.
    """
    from ai_justicia.dossiers import store as dstore
    actor_id, frase = dstore.crear_ciudadano()
    dossier_id = dstore.crear_dossier(actor_id)
    return {
        "dossier_id": str(dossier_id),
        "actor_id": str(actor_id),
        "frase_recuperacion": frase,
        "aviso": (
            "Guarda esta frase en un lugar seguro: es la ÚNICA forma de volver a entrar "
            "a tu caso. Si la pierdes, el dossier no puede recuperarse."
        ),
    }


def _uuid_o_400(dossier_id: str) -> _uuid.UUID:
    try:
        return _uuid.UUID(dossier_id)
    except ValueError:
        raise HTTPException(400, "dossier_id inválido")


@router.post("/dossiers/{dossier_id}/consentimiento")
def consentimiento_ep(dossier_id: str, req: ConsentimientoRequest,
                      actor: dict = Depends(actor_actual)):
    """Registra/revoca el consentimiento EXPRESO para entrenamiento. Solo el dueño.

    LFPDPPP 2025: opt-in separado del servicio, revocable, con timestamp
    y versión del aviso como prueba. Solo alimenta el adapter GENERAL;
    los datos de bufetes jamás entran ahí.
    """
    from ai_justicia.dossiers import store as dstore
    did = _uuid_o_400(dossier_id)
    if dstore.tiene_acceso(did, _uuid.UUID(actor["sub"]), actor.get("bufete")) != "dueño":
        raise HTTPException(403, "Solo el dueño del caso puede cambiar el consentimiento")

    if req.otorgar:
        ok = dstore.otorgar_consentimiento(did)
        accion = "otorgado"
    else:
        ok = dstore.revocar_consentimiento(did)
        accion = "revocado"
    if not ok:
        raise HTTPException(409, f"Consentimiento ya estaba en ese estado")
    return {"dossier_id": dossier_id, "consentimiento": accion}


@router.get("/dossiers/mios")
def mis_casos(actor: dict = Depends(actor_actual)):
    """Casos de este actor: propios + compartidos conmigo (parte o asesor).

    La vía para que un ciudadano-parte llegue a un caso compartido con él.
    """
    import psycopg
    from ai_justicia.config import settings
    aid = _uuid.UUID(actor["sub"])
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, materia, estado, expediente->>'nombre' as nombre,
                          created_at
                   FROM dossiers WHERE ciudadano_id = %s AND estado != 'eliminado'
                   ORDER BY updated_at DESC LIMIT 50""",
                (aid,))
            cols = [c[0] for c in cur.description]
            casos = [dict(zip(cols, r)) for r in cur.fetchall()]
            for c in casos:
                c["propio"] = True
            cur.execute(
                """SELECT d.id, d.materia, d.estado,
                          d.expediente->>'nombre' as nombre, d.created_at,
                          g.relacion, g.rol, g.etiqueta, g.id as acceso_id
                   FROM dossiers d
                   JOIN dossier_accesos g ON g.dossier_id = d.id
                        AND g.revocado_en IS NULL AND g.actor_id = %s
                   ORDER BY d.created_at DESC LIMIT 50""",
                (aid,))
            cols2 = [c[0] for c in cur.description]
            for r in cur.fetchall():
                c = dict(zip(cols2, r))
                c["propio"] = False
                casos.append(c)
    casos.sort(key=lambda c: c["created_at"], reverse=True)
    return {"casos": casos}


@router.get("/dossiers/{dossier_id}")
def obtener_dossier_ep(dossier_id: str, actor: dict = Depends(actor_actual)):
    """Estado del dossier (dueño o con grant activo). Incluye consentimiento."""
    from ai_justicia.dossiers import store as dstore
    did = _uuid_o_400(dossier_id)
    nivel = dstore.tiene_acceso(did, _uuid.UUID(actor["sub"]), actor.get("bufete"))
    if not nivel:
        raise HTTPException(404, "Dossier no encontrado")
    d = dstore.obtener_dossier(did)
    if not d:
        raise HTTPException(404, "Dossier no encontrado")
    # el consentimiento de entrenamiento solo es visible para el dueño
    if nivel != "dueño":
        d["consentimiento_entrenamiento"] = None
    d["nivel_acceso"] = nivel
    return d


# ── Compartir / reasignar (F4: el modelo de grants M1 llega a la UI) ────────

class AccesoRequest(BaseModel):
    abogado_id: str = Field(..., description="Actor del abogado que recibirá acceso")
    rol: str = Field("lectura", description="lectura | edicion")
    reasignar: bool = Field(False, description="True: revoca los accesos activos antes (cambio de abogado)")


@router.post("/dossiers/{dossier_id}/accesos")
def compartir_dossier(dossier_id: str, req: AccesoRequest,
                      actor: dict = Depends(actor_actual)):
    """Comparte el caso con un abogado (grant revocable). Solo el dueño.

    reasignar=True = cambio de abogado: revoca los grants activos y otorga
    el nuevo en una sola operación (el historial lo registra todo).
    """
    from ai_justicia.dossiers import store as dstore
    did = _uuid_o_400(dossier_id)
    dueño = _uuid.UUID(actor["sub"])
    if not dstore.es_admin_caso(did, dueño, actor.get("bufete")):
        raise HTTPException(403, "Solo quien gestiona el caso puede compartirlo")
    try:
        aid = _uuid.UUID(req.abogado_id)
    except ValueError:
        raise HTTPException(400, "abogado_id inválido")
    if req.rol not in ("lectura", "edicion"):
        raise HTTPException(400, "rol debe ser lectura o edicion")

    revocados = 0
    if req.reasignar:
        revocados = dstore.revocar_activos(did, excepto_actor=aid)
    gid = dstore.otorgar_acceso(did, dueño, actor_id=aid, rol=req.rol)
    dstore.marcar_estado(did, "compartido")
    return {"acceso_id": gid, "revocados": revocados, "estado": "compartido"}


@router.get("/dossiers/{dossier_id}/accesos")
def listar_accesos_ep(dossier_id: str, actor: dict = Depends(actor_actual)):
    """Historial de accesos del caso (activos y revocados). Solo el dueño."""
    from ai_justicia.dossiers import store as dstore
    did = _uuid_o_400(dossier_id)
    if not dstore.es_admin_caso(did, _uuid.UUID(actor["sub"]), actor.get("bufete")):
        raise HTTPException(403, "Solo quien gestiona el caso puede ver el historial")
    return {"accesos": dstore.listar_accesos(did)}


@router.delete("/dossiers/{dossier_id}/accesos/{acceso_id}")
def revocar_acceso_ep(dossier_id: str, acceso_id: int,
                      actor: dict = Depends(actor_actual)):
    """Revoca un acceso. Solo el dueño. Si no quedan activos, el caso vuelve a 'activo'."""
    from ai_justicia.dossiers import store as dstore
    did = _uuid_o_400(dossier_id)
    if not dstore.es_admin_caso(did, _uuid.UUID(actor["sub"]), actor.get("bufete")):
        raise HTTPException(403, "Solo quien gestiona el caso puede revocar accesos")
    if not dstore.revocar_acceso(did, acceso_id):
        raise HTTPException(404, "Acceso no encontrado o ya revocado")
    if not dstore.tiene_accesos_activos(did):
        dstore.marcar_estado(did, "activo")
    return {"ok": True, "estado": dstore.obtener_dossier(did)["estado"]}


# ── Invitaciones por código/QR (E1: tipadas — parte/asesor, persona/firma) ──

def _puede_gestionar(dossier_id: str, actor: dict):
    """Dueño del caso, o admin de la firma dueña. La llave de 'solo el dueño invita'."""
    from ai_justicia.dossiers import store as dstore
    did = _uuid_o_400(dossier_id)
    if not dstore.es_admin_caso(did, _uuid.UUID(actor["sub"]), actor.get("bufete")):
        raise HTTPException(403, "Solo quien gestiona el caso puede hacer esto")
    return did


class InvitacionRequest(BaseModel):
    relacion: str = Field("asesor", description="parte | asesor")
    rol: str = Field("lectura", description="lectura | edicion (las partes suelen requerir edicion)")
    para_bufete: bool = Field(False, description="True: la invitación es para un despacho completo")


@router.post("/dossiers/{dossier_id}/invitaciones")
def crear_invitacion_ep(dossier_id: str, req: InvitacionRequest,
                        actor: dict = Depends(actor_actual)):
    """Genera un código de invitación tipado. Se devuelve UNA vez; en DB el hash."""
    from ai_justicia.dossiers import invitaciones
    did = _puede_gestionar(dossier_id, actor)
    try:
        inv = invitaciones.crear_invitacion(
            did, _uuid.UUID(actor["sub"]),
            relacion=req.relacion, rol=req.rol, para_bufete=req.para_bufete)
    except ValueError as e:
        raise HTTPException(400, str(e))
    inv["url"] = f"https://aijusticia.mx/reclamar?c={inv['codigo']}"
    return inv


@router.get("/dossiers/{dossier_id}/invitaciones")
def listar_invitaciones_ep(dossier_id: str, actor: dict = Depends(actor_actual)):
    """Invitaciones vivas + solicitudes pendientes (sin códigos)."""
    from ai_justicia.dossiers import invitaciones
    did = _puede_gestionar(dossier_id, actor)
    return {"invitaciones": invitaciones.listar_invitaciones(did),
            "solicitudes": invitaciones.listar_pendientes(did)}


@router.delete("/dossiers/{dossier_id}/invitaciones/{invitacion_id}")
def revocar_invitacion_ep(dossier_id: str, invitacion_id: str,
                          actor: dict = Depends(actor_actual)):
    from ai_justicia.dossiers import invitaciones
    did = _puede_gestionar(dossier_id, actor)
    if not invitaciones.revocar(_uuid_o_400(invitacion_id), did):
        raise HTTPException(404, "Invitación no encontrada o ya resuelta")
    return {"ok": True}


class CanjearRequest(BaseModel):
    codigo: str = Field(..., min_length=8, max_length=20)
    etiqueta: str | None = Field(None, max_length=60,
                                 description="Cómo te conocen en este caso (p.ej. 'Berto — comprador')")


@router.post("/invitaciones/canjear")
def canjear_ep(req: CanjearRequest, actor: dict = Depends(actor_actual)):
    """Canjea el código → solicitud pendiente. Persona (ciudadano/abogado) o firma (admin)."""
    from ai_justicia.dossiers import invitaciones
    r = invitaciones.canjear(req.codigo, _uuid.UUID(actor["sub"]),
                             _uuid.UUID(actor["bufete"]) if actor.get("bufete") else None,
                             etiqueta=req.etiqueta)
    if not r.get("ok"):
        raise HTTPException(400, r.get("error", "Código no válido"))
    return r


@router.post("/invitaciones/{invitacion_id}/aceptar")
def aceptar_invitacion_ep(invitacion_id: str, body: dict,
                          actor: dict = Depends(actor_actual)):
    """El dueño/admin acepta la solicitud (un click → grant tipado)."""
    from ai_justicia.dossiers import invitaciones
    did = _uuid_o_400(str(body.get("dossier_id", "")))
    iid = _uuid_o_400(invitacion_id)
    _puede_gestionar(str(did), actor)
    if not invitaciones.aceptar(iid, did, _uuid.UUID(actor["sub"])):
        raise HTTPException(404, "Solicitud no encontrada o ya resuelta")
    return {"ok": True, "estado": "compartido"}


@router.post("/invitaciones/{invitacion_id}/rechazar")
def rechazar_invitacion_ep(invitacion_id: str, body: dict,
                           actor: dict = Depends(actor_actual)):
    from ai_justicia.dossiers import invitaciones
    did = _uuid_o_400(str(body.get("dossier_id", "")))
    iid = _uuid_o_400(invitacion_id)
    _puede_gestionar(str(did), actor)
    if not invitaciones.rechazar(iid, did):
        raise HTTPException(404, "Solicitud no encontrada o ya resuelta")
    return {"ok": True}


@router.post("/dossiers/{dossier_id}/salir")
def salir_del_caso_ep(dossier_id: str, actor: dict = Depends(actor_actual)):
    """Salida voluntaria: el beneficiario renuncia a SU acceso y asignaciones.

    Sus aportes permanecen visibles a los participantes; derechos ARCO vigentes.
    """
    from ai_justicia.dossiers import store as dstore
    did = _uuid_o_400(dossier_id)
    if not dstore.salir_de_caso(did, _uuid.UUID(actor["sub"])):
        raise HTTPException(404, "No tienes acceso que renunciar en este caso")
    return {"ok": True,
            "nota": "Tus aportes permanecen visibles a los participantes; puedes ejercer tus derechos ARCO cuando quieras."}


@router.get("/dossiers/{dossier_id}/equipo")
def equipo_ep(dossier_id: str, actor: dict = Depends(actor_actual)):
    """Vista de gestión: partes, asesores, asignaciones y vetos del caso."""
    from ai_justicia.dossiers import store as dstore
    did = _uuid_o_400(dossier_id)
    if not dstore.tiene_acceso(did, _uuid.UUID(actor["sub"]), actor.get("bufete")):
        raise HTTPException(404, "Dossier no encontrado")
    return {
        "accesos": dstore.listar_accesos(did),
        "asignaciones": dstore.listar_asignaciones(did),
        "vetos": dstore.listar_vetos(did) if dstore.es_admin_caso(
            did, _uuid.UUID(actor["sub"]), actor.get("bufete")) else [],
    }




class AbogadoRegistroRequest(BaseModel):
    cedula: str = Field(..., min_length=5, max_length=20, description="Cédula profesional")
    especialidades: list[str] | None = Field(None, description="Áreas de práctica")
    bufete_nombre: str | None = Field(None, max_length=200, description="Nombre del despacho (opcional)")

    model_config = {"protected_namespaces": ()}




@router.post("/abogados/registro")
def registro_abogado_ep(req: AbogadoRegistroRequest):
    """Alta de abogado: cédula + especialidades + bufete opcional.

    La verificación de cédula (RENAJU) es Fase E; por ahora queda
    pendiente de verificación. La frase permite re-entrar a su cuenta.
    Sus datos alimentan SOLO el adapter de su bufete, jamás el general.
    """
    from ai_justicia.dossiers import store as dstore
    actor_id, frase, bufete_id = dstore.crear_abogado(
        cedula=req.cedula.strip(),
        especialidades=[e[:60] for e in (req.especialidades or [])][:8],
        bufete_nombre=req.bufete_nombre.strip() if req.bufete_nombre else None,
    )
    return {
        "actor_id": str(actor_id),
        "bufete_id": str(bufete_id) if bufete_id else None,
        "frase_recuperacion": frase,
        "verificacion": "pendiente",
        "nota_adapter": (
            "Los datos de tu bufete entrenan únicamente el modelo privado de tu "
            "despacho. Jamás entran al modelo general ni al de otros bufetes."
        ),
    }


# ── Autenticación: frase / dispositivo / Google ────────────────────────────
