"""Rutas de práctica legal: plazos, tareas, clientes, dashboard (V1)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ai_justicia.auth.deps import actor_actual

router = APIRouter(prefix="/practica", tags=["practica"])


def _bufete(actor: dict) -> str:
    if not actor.get("bufete"):
        raise HTTPException(403, "Requiere sesión de despacho")
    return actor["bufete"]


# ── Plazos ─────────────────────────────────────────────────────────────────

class PlazoRequest(BaseModel):
    dossier_id: str
    titulo: str = Field(..., max_length=200)
    fecha: str = Field(..., description="ISO datetime")
    fatal: bool = False
    tipo: str = "termino"


@router.post("/plazos")
def crear_plazo(req: PlazoRequest, actor: dict = Depends(actor_actual)):
    from ai_justicia.dossiers import practica
    import uuid
    return {"plazo_id": practica.crear_plazo(
        uuid.UUID(req.dossier_id), uuid.UUID(_bufete(actor)),
        req.titulo, req.fecha, req.fatal, req.tipo,
        uuid.UUID(actor["sub"]))}


@router.get("/plazos")
def plazos(dossier_id: str | None = None, proximos: int | None = None,
           actor: dict = Depends(actor_actual)):
    from ai_justicia.dossiers import practica
    import uuid
    bid = uuid.UUID(_bufete(actor))
    if proximos:
        return {"plazos": practica.plazos_proximos(bid, proximos)}
    if dossier_id:
        return {"plazos": practica.listar_plazos(uuid.UUID(dossier_id))}
    return {"plazos": practica.plazos_proximos(bid, 30)}


@router.post("/plazos/{plazo_id}/completar")
def completar(plazo_id: str, actor: dict = Depends(actor_actual)):
    from ai_justicia.dossiers import practica
    import uuid
    if not practica.completar_plazo(plazo_id, uuid.UUID(_bufete(actor))):
        raise HTTPException(404, "Plazo no encontrado")
    return {"ok": True}


# ── Tareas ─────────────────────────────────────────────────────────────────

class TareaRequest(BaseModel):
    dossier_id: str
    titulo: str = Field(..., max_length=200)
    asignado_a: str | None = None
    vence: str | None = None


@router.post("/tareas")
def crear_tarea(req: TareaRequest, actor: dict = Depends(actor_actual)):
    from ai_justicia.dossiers import practica
    import uuid
    return {"tarea_id": practica.crear_tarea(
        uuid.UUID(req.dossier_id), uuid.UUID(_bufete(actor)),
        req.titulo,
        uuid.UUID(req.asignado_a) if req.asignado_a else None,
        req.vence, uuid.UUID(actor["sub"]))}


@router.get("/tareas")
def tareas(dossier_id: str, actor: dict = Depends(actor_actual)):
    from ai_justicia.dossiers import practica
    import uuid
    return {"tareas": practica.listar_tareas(uuid.UUID(dossier_id))}


@router.post("/tareas/{tarea_id}/toggle")
def toggle(tarea_id: str, actor: dict = Depends(actor_actual)):
    from ai_justicia.dossiers import practica
    import uuid
    if not practica.toggle_tarea(tarea_id, uuid.UUID(_bufete(actor))):
        raise HTTPException(404, "Tarea no encontrada")
    return {"ok": True}


# ── Clientes ───────────────────────────────────────────────────────────────

class ClienteRequest(BaseModel):
    nombre: str = Field(..., max_length=200)
    tipo: str = "persona_fisica"
    email: str | None = None
    telefono: str | None = None
    notas: str | None = None


@router.post("/clientes")
def crear_cliente(req: ClienteRequest, actor: dict = Depends(actor_actual)):
    from ai_justicia.dossiers import practica
    import uuid
    return {"cliente_id": practica.crear_cliente(
        uuid.UUID(_bufete(actor)), req.nombre, req.tipo,
        req.email, req.telefono, req.notas)}


@router.get("/clientes")
def listar_clientes(actor: dict = Depends(actor_actual)):
    from ai_justicia.dossiers import practica
    import uuid
    return {"clientes": practica.listar_clientes(uuid.UUID(_bufete(actor)))}


# ── Dashboard ──────────────────────────────────────────────────────────────

@router.get("/dashboard")
def dashboard(actor: dict = Depends(actor_actual)):
    from ai_justicia.dossiers import practica
    import uuid
    return practica.dashboard(
        uuid.UUID(_bufete(actor)), uuid.UUID(actor["sub"]))
