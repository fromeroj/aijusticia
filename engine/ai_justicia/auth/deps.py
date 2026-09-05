"""Dependencias FastAPI para autenticación JWT.

Uso en routers:
    from ai_justicia.auth.deps import actor_actual
    @router.get("/...")
    def endpoint(actor: dict = Depends(actor_actual)):
        # actor = {sub, tier, bufete, rol}
"""
from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request

from ai_justicia.auth.jwt import verificar_token


def _extraer_token(request: Request) -> str | None:
    """Del header Authorization: Bearer <token>."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


async def actor_actual(request: Request) -> dict:
    """Dependencia: valida el JWT y devuelve los claims del actor."""
    token = _extraer_token(request)
    if not token:
        raise HTTPException(401, "Token requerido")
    claims = verificar_token(token)
    if not claims:
        raise HTTPException(401, "Token inválido o expirado")
    return claims


async def actor_opcional(request: Request) -> dict | None:
    """Dependencia blanda: devuelve claims si hay token válido, None si no."""
    token = _extraer_token(request)
    if not token:
        return None
    return verificar_token(token)


async def bufete_actual(actor: dict = Depends(actor_actual)) -> uuid.UUID:
    """Dependencia: exige tier despacho y devuelve el bufete_id (para RLS)."""
    if actor.get("tier") != "despacho" or not actor.get("bufete"):
        raise HTTPException(403, "Requiere sesión de despacho")
    return uuid.UUID(actor["bufete"])


def set_tenant(cur, bufete_id: str | None):
    """Configura la variable de sesión para RLS antes de queries de dossiers.

    Uso:
        conn = psycopg.connect(...)
        cur = conn.cursor()
        set_tenant(cur, actor.get("bufete"))
        cur.execute("SELECT * FROM dossiers ...")
    """
    cur.execute("SELECT set_config('app.bufete_id', %s, false)",
                (str(bufete_id) if bufete_id else "",))
