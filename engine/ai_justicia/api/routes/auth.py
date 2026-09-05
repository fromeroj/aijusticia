"""Rutas de autenticación: frase, dispositivo, Google OAuth."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ai_justicia.config import settings

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




class TokenRequest(BaseModel):
    """Intercambio de credenciales por par JWT access+refresh."""
    via: str = Field(..., description="google | frase | dispositivo | refresh")
    credential: str = Field(..., description="Token/frase/refresh_token según vía")
    email: str | None = Field(None, description="solo via=google")


@router.post("/token")
def auth_token(req: TokenRequest):
    """Emite par JWT access(15m) + refresh(30d) según la vía."""
    import datetime
    import uuid as _uuid
    from ai_justicia.auth.jwt import par_tokens, verificar_token, hash_refresh
    from ai_justicia.dossiers import store as dstore

    actor_info = None

    if req.via == "refresh":
        claims = verificar_token(req.credential)
        if not claims or claims.get("typ") != "refresh":
            raise HTTPException(401, "Refresh token inválido")
        # verificar no revocado
        import psycopg
        conn = psycopg.connect(host=settings.pg_host, port=settings.pg_port,
                               dbname=settings.pg_db, user=settings.pg_user, password=settings.pg_password)
        cur = conn.cursor()
        cur.execute("SELECT actor_id FROM refresh_tokens WHERE token_hash=%s AND revoked_at IS NULL AND expires_at > now()",
                    (hash_refresh(req.credential),))
        row = cur.fetchone()
        if not row:
            raise HTTPException(401, "Refresh token revocado o expirado")
        # rotar: revocar viejo, emitir nuevo
        cur.execute("UPDATE refresh_tokens SET revoked_at=now() WHERE token_hash=%s", (hash_refresh(req.credential),))
        actor_id, tier = str(claims["sub"]), claims.get("tier", "ciudadano")
        conn.commit(); conn.close()
        actor_info = {"actor_id": actor_id, "tipo": tier, "dossier_id": None}

    elif req.via == "frase":
        s = dstore.entrar_con_frase(req.credential.strip())
        if not s:
            raise HTTPException(401, "Frase incorrecta")
        actor_info = s

    elif req.via == "dispositivo":
        s = dstore.entrar_con_dispositivo(req.credential.strip())
        if not s:
            raise HTTPException(401, "Dispositivo no vinculado")
        actor_info = s

    elif req.via == "google":
        s = dstore.entrar_o_crear_con_google(req.credential.strip(), req.email)
        actor_info = s

    else:
        raise HTTPException(400, f"vía desconocida: {req.via}")

    # emitir par
    resultado = par_tokens(actor_info["actor_id"], actor_info.get("tipo", "ciudadano"),
                           actor_info.get("bufete_id"), actor_info.get("rol"))

    # persistir refresh hash
    import psycopg
    conn = psycopg.connect(host=settings.pg_host, port=settings.pg_port,
                           dbname=settings.pg_db, user=settings.pg_user, password=settings.pg_password)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO refresh_tokens (actor_id, token_hash, expires_at) VALUES (%s, %s, %s)",
        (_uuid.UUID(resultado["actor_id"]), hash_refresh(resultado["refresh_token"]),
         datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)))
    conn.commit(); conn.close()

    return resultado
