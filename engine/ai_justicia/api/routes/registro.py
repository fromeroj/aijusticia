"""Registrar ciudadano con email + contraseña (Nextcloud OCS + JWT).

Reemplaza la frase de 12 palabras como método principal de persistencia.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import sys
import urllib.request
import uuid as _uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field

sys.path.insert(0, "/opt/aijusticia/engine")
from ai_justicia.auth.jwt import par_tokens
from ai_justicia.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


class RegistroRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=200)
    password: str = Field(..., min_length=8, max_length=128)


class LoginEmailRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=200)
    password: str = Field(..., min_length=1, max_length=128)


def _hash_password(password: str) -> str:
    import hashlib
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000)
    return f"pbkdf2${salt}${h.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, h_hex = stored.split("$")
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000)
        return h.hex() == h_hex
    except Exception:
        return False


def _nc_crear_usuario(email: str, password: str) -> bool:
    """Crea usuario en Nextcloud via OCS API. Devuelve True si OK o ya existe."""
    import base64
    settings = sys.modules.get("ai_justicia.config").settings
    url = f"{settings.bufete_nc_url.rstrip('/')}/ocs/v1.php/cloud/users"
    auth = base64.b64encode(
        f"{settings.bufete_nc_user}:{settings.bufete_nc_app_pass}".encode()
    ).decode()
    body = urllib.parse.urlencode({"userid": email, "password": password}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "OCS-APIRequest": "true",
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/x-www-form-urlencoded",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception:
        return False  # ya existe u otro error — el login por email valida


def _crear_actor_email(email: str, password_hash: str) -> str:
    """Crea actor ciudadano con email en la DB."""
    import psycopg
    aid = str(_uuid.uuid4())
    conn = psycopg.connect(settings.psycopg_dsn)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO actores (id, es_abogado, email, password_hash)
           VALUES (%s, FALSE, %s, %s)""",
        (aid, email, password_hash),
    )
    conn.commit()
    conn.close()
    return aid


def _entrar_con_email(email: str, password: str) -> str | None:
    """Busca el actor por email y verifica password. Devuelve actor_id o None."""
    import psycopg
    conn = psycopg.connect(settings.psycopg_dsn)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, password_hash FROM actores WHERE email = %s AND password_hash IS NOT NULL",
        (email,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    actor_id, stored = row
    if not _verify_password(password, stored):
        return None
    return str(actor_id)


@router.post("/registro")
def auth_registro(req: RegistroRequest):
    """Registra un ciudadano con email + contraseña. Crea usuario Nextcloud."""
    email = req.email.strip().lower()
    ph = _hash_password(req.password)
    aid = str(_uuid.uuid4())

    import psycopg
    conn = psycopg.connect(settings.psycopg_dsn)
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO actores (id, es_abogado, email, password_hash)
               VALUES (%s, FALSE, %s, %s)""",
            (aid, email, ph),
        )
        conn.commit()
    except psycopg.errors.UniqueViolation:
        conn.close()
        raise HTTPException(409, "Este correo ya está registrado")
    except Exception as e:
        conn.close()
        raise HTTPException(500, str(e)[:100])
    conn.close()

    # crear usuario Nextcloud (no bloquea si falla)
    _nc_crear_usuario(email, req.password)

    tokens = par_tokens(aid, "ciudadano")
    return {**tokens, "actor_id": aid, "tipo": "ciudadano", "email": email}


@router.post("/login-email")
def login_email(req: LoginEmailRequest):
    """Login con email + contraseña."""
    import psycopg
    conn = psycopg.connect(settings.psycopg_dsn)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, password_hash FROM actores WHERE email = %s AND password_hash IS NOT NULL",
        (req.email.strip().lower(),))
    row = cur.fetchone()
    conn.close()
    if not row or not _verify_password(req.password, row[1]):
        raise HTTPException(401, "Credenciales incorrectas")
    tokens = par_tokens(str(row[0]), "ciudadano")
    return {**tokens, "actor_id": str(row[0]), "tipo": "ciudadano", "email": req.email}
