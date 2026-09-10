"""Autenticación JWT unificada para AI Justicia.

3 emisores (frase/dispositivo/Google → ciudadanos; NC OAuth → despachos),
1 verificador (deps.py en cada ruta del engine).

Tokens:
  - access_token: 15 min, HS256, claims {sub, tier, bufete, rol}
  - refresh_token: 30 días rotativo, revocable via tabla refresh_tokens
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Any

from ai_justicia.config import settings
from ai_justicia.ids import nuevo_id

# HS256 manual (sin dependencia de PyJWT — implementación transparente y auditable)


def _b64(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    pad = 4 - len(data) % 4
    return urlsafe_b64decode(data + "=" * pad)


def _sign(payload: bytes, secret: str) -> str:
    return _b64(hmac.new(secret.encode(), payload, hashlib.sha256).digest())


def emitir_token(claims: dict, ttl_seg: int, secret: str | None = None) -> str:
    """Emite un JWT HS256. Los claims ya deben traer sub/tier."""
    sec = secret or settings.jwt_secret
    now = int(time.time())
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = dict(claims)
    body.setdefault("iat", now)
    body["exp"] = now + ttl_seg
    body["jti"] = str(nuevo_id())
    payload = _b64(json.dumps(body).encode())
    signing_input = f"{header}.{payload}".encode()
    return f"{header}.{payload}.{_sign(signing_input, sec)}"


def verificar_token(token: str, secret: str | None = None) -> dict | None:
    """Verifica firma y expiración. Devuelve claims o None."""
    sec = secret or settings.jwt_secret
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        signing_input = f"{parts[0]}.{parts[1]}".encode()
        expected = _sign(signing_input, sec)
        if not hmac.compare_digest(expected, parts[2]):
            return None
        claims = json.loads(_unb64(parts[1]))
        if claims.get("exp", 0) < time.time():
            return None
        return claims
    except Exception:
        return None


def hash_refresh(token: str) -> str:
    """Hash del refresh token para almacenar (nunca en claro)."""
    return hashlib.sha256(token.encode()).hexdigest()


def par_tokens(actor_id: str, tier: str, bufete_id: str | None = None,
               rol: str | None = None, dossier_id: str | None = None) -> dict:
    """Emite el par access + refresh para un actor."""
    claims = {"sub": str(actor_id), "tier": tier}
    if bufete_id:
        claims["bufete"] = str(bufete_id)
    if rol:
        claims["rol"] = rol
    if dossier_id:
        claims["dossier"] = str(dossier_id)

    access = emitir_token(claims, ttl_seg=900)  # 15 min
    refresh = emitir_token({**claims, "typ": "refresh"}, ttl_seg=86400 * 30)  # 30 días
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": 900,
        "refresh_token": refresh,
        "actor_id": str(actor_id),
        "tipo": tier,
        "dossier_id": str(dossier_id) if dossier_id else None,
        "bufete_id": str(bufete_id) if bufete_id else None,
    }
