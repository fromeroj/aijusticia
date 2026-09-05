"""Rutas de dossiers (casos), consentimiento y registro de abogados."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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


@router.post("/dossiers/{dossier_id}/consentimiento")
def consentimiento_ep(dossier_id: str, req: ConsentimientoRequest):
    """Registra/revoca el consentimiento EXPRESO para entrenamiento.

    LFPDPPP 2025: opt-in separado del servicio, revocable, con timestamp
    y versión del aviso como prueba. Solo alimenta el adapter GENERAL;
    los datos de bufetes jamás entran ahí.
    """
    from ai_justicia.dossiers import store as dstore
    import uuid as _uuid
    try:
        did = _uuid.UUID(dossier_id)
    except ValueError:
        raise HTTPException(400, "dossier_id inválido")

    if req.otorgar:
        ok = dstore.otorgar_consentimiento(did)
        accion = "otorgado"
    else:
        ok = dstore.revocar_consentimiento(did)
        accion = "revocado"
    if not ok:
        raise HTTPException(409, f"Consentimiento ya estaba en ese estado")
    return {"dossier_id": dossier_id, "consentimiento": accion}


@router.get("/dossiers/{dossier_id}")
def obtener_dossier_ep(dossier_id: str):
    """Estado del dossier (incluye estado de consentimiento)."""
    from ai_justicia.dossiers import store as dstore
    import uuid as _uuid
    try:
        did = _uuid.UUID(dossier_id)
    except ValueError:
        raise HTTPException(400, "dossier_id inválido")
    d = dstore.obtener_dossier(did)
    if not d:
        raise HTTPException(404, "Dossier no encontrado")
    return d




class AbogadoRegistroRequest(BaseModel):
    cedula: str = Field(..., min_length=5, max_length=20, description="Cédula profesional")
    especialidades: list[str] | None = Field(None, description="Áreas de práctica")
    bufete_nombre: str | None = Field(None, max_length=200, description="Nombre del despacho (opcional)")




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

