"""Rutas de autenticación: frase, dispositivo, Google OAuth."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/auth", tags=["auth"])

def _sesion_resp(s: dict) -> dict:
    return {
        "actor_id": s["actor_id"],
        "tipo": "abogado" if s["es_abogado"] else "ciudadano",
        "dossier_id": s.get("dossier_id"),
        "bufete_id": s.get("bufete_id"),
        "email": s.get("email"),
    }




class FraseLoginRequest(BaseModel):
    frase: str = Field(..., min_length=10, description="Frase de recuperación de 12 palabras")


class DispositivoLoginRequest(BaseModel):
    token: str = Field(..., min_length=20, description="Token de dispositivo guardado en el navegador")


class DispositivoRegistroRequest(BaseModel):
    actor_id: str
    token: str = Field(..., min_length=20)


class GoogleLoginRequest(BaseModel):
    google_sub: str = Field(..., description="Subject ID único de Google")
    email: str | None = None


def _sesion_resp(s: dict) -> dict:
    return {
        "actor_id": s["actor_id"],
        "tipo": "abogado" if s["es_abogado"] else "ciudadano",
        "dossier_id": s.get("dossier_id"),
        "bufete_id": s.get("bufete_id"),
        "email": s.get("email"),
    }




@router.post("/frase")
def auth_frase(req: FraseLoginRequest):
    """Re-entrada con la frase de recuperación (ciudadano o abogado)."""
    from ai_justicia.dossiers import store as dstore
    s = dstore.entrar_con_frase(req.frase.strip())
    if not s:
        raise HTTPException(401, "Frase incorrecta. Revisa que sean tus 12 palabras.")
    return _sesion_resp(s)


@router.post("/dispositivo")
def auth_dispositivo(req: DispositivoLoginRequest):
    """Re-entrada de un toque con el token guardado en este navegador."""
    from ai_justicia.dossiers import store as dstore
    s = dstore.entrar_con_dispositivo(req.token.strip())
    if not s:
        raise HTTPException(401, "Este dispositivo ya no está vinculado. Usa tu frase.")
    return _sesion_resp(s)


@router.post("/dispositivo/registrar")
def auth_dispositivo_registrar(req: DispositivoRegistroRequest):
    """Vincula el navegador actual tras un login exitoso (one-tap la próxima vez)."""
    from ai_justicia.dossiers import store as dstore
    import uuid as _uuid
    try:
        aid = _uuid.UUID(req.actor_id)
    except ValueError:
        raise HTTPException(400, "actor_id inválido")
    dstore.registrar_dispositivo(aid, req.token.strip())
    return {"ok": True}


@router.post("/google")
def auth_google(req: GoogleLoginRequest):
    """Find-or-create por Google (llamado por el callback OAuth del frontend)."""
    from ai_justicia.dossiers import store as dstore
    s = dstore.entrar_o_crear_con_google(req.google_sub.strip(), req.email)
    return _sesion_resp(s)


