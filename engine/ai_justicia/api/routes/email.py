"""Endpoint de email — envía invitaciones y notificaciones vía Resend."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ai_justicia.auth.deps import actor_actual
from ai_justicia.config import settings

router = APIRouter(prefix="/email", tags=["email"])


class InvitacionEmailRequest(BaseModel):
    to: str = Field(..., description="Email del destinatario")
    tipo: str = Field(..., description="invitacion_caso | invitacion_firma | notificacion")
    datos: dict = Field(default_factory=dict, description="Datos según el tipo")


@router.post("/enviar")
def enviar_email(req: InvitacionEmailRequest, actor: dict = Depends(actor_actual)):
    """Envía un email del sistema. Requiere sesión (no es público).

    Tipos:
      invitacion_caso:  {nombre_dueño, codigo, url}
      invitacion_firma: {nombre_firma, rol, codigo, url}
      notificacion:     {nombre_caso, evento}
    """
    from ai_justicia.email import cliente

    if not settings.resend_api_key:
        # modo log: registrar pero no fallar
        return {"ok": False, "modo": "log", "mensaje": "RESEND_API_KEY no configurada"}

    if req.tipo == "invitacion_caso":
        ok = cliente.enviar_invitacion_caso(
            req.to, req.datos.get("nombre_dueño", "Alguien"),
            req.datos.get("codigo", ""), req.datos.get("url", ""))
    elif req.tipo == "invitacion_firma":
        ok = cliente.enviar_invitacion_firma(
            req.to, req.datos.get("nombre_firma", ""), req.datos.get("rol", "abogado"),
            req.datos.get("codigo", ""), req.datos.get("url", ""))
    elif req.tipo == "notificacion":
        ok = cliente.enviar_notificacion_caso(
            req.to, req.datos.get("nombre_caso", ""), req.datos.get("evento", ""))
    else:
        raise HTTPException(400, f"tipo desconocido: {req.tipo}")

    return {"ok": ok}
