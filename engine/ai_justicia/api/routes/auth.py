"""Rutas de autenticación: frase, dispositivo, Google OAuth."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
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
    frase: str | None = Field(None, min_length=10,
                              description="Prueba de posesión cuando no hay JWT (momento de creación)")


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(..., min_length=50, description="id_token JWT emitido por Google — el engine valida firma y audiencia")
    google_sub: str | None = Field(None, description="(obsoleto) ya no se acepta: el sub sale del id_token verificado")


def _google_validar_id_token(id_token: str) -> tuple[str, str | None]:
    """Valida el id_token contra Google (tokeninfo) y devuelve (sub, email).

    La validación de firma/audiencia la hace Google en su endpoint; el engine
    verifica que aud == nuestro client_id y que el correo esté verificado.
    Antes de este fix el backend confiaba en el google_sub que enviaba el
    frontend sin verificar NADA.
    """
    import json as _json
    import urllib.parse
    import urllib.request
    if not settings.google_client_id:
        raise HTTPException(503, "Login con Google no está configurado")
    url = "https://oauth2.googleapis.com/tokeninfo?id_token=" + urllib.parse.quote(id_token)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            claims = _json.loads(r.read())
    except Exception:
        raise HTTPException(401, "id_token inválido")
    if claims.get("aud") != settings.google_client_id:
        raise HTTPException(401, "id_token emitido para otra aplicación")
    if claims.get("exp", 0) < __import__("time").time():
        raise HTTPException(401, "id_token expirado")
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(401, "id_token sin sub")
    email = claims.get("email") if claims.get("email_verified") else None
    return sub, email


def _nc_validar(user: str, password: str) -> bool:
    """Valida credenciales contra el Nextcloud del despacho (PROPFIND Depth 0)."""
    import base64
    import urllib.error
    import urllib.request
    url = f"{settings.bufete_nc_url.rstrip('/')}/remote.php/dav/files/{user}/"
    req = urllib.request.Request(url, method="PROPFIND", headers={
        "Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode(),
        "Depth": "0",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status in (200, 207)
    except urllib.error.HTTPError:
        return False
    except Exception:
        return False


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
def auth_dispositivo_registrar(req: DispositivoRegistroRequest,
                               request: Request):
    """Vincula el navegador actual tras un login exitoso (one-tap la próxima vez).

    Prueba de posesión obligatoria (A3): un JWT válido del MISMO actor, o la
    frase de recuperación (disponible en el momento de crear el caso).
    Sin ella, cualquiera podría vincular su token a cualquier actor_id.
    """
    from ai_justicia.dossiers import store as dstore
    import uuid as _uuid
    from ai_justicia.auth.jwt import verificar_token
    try:
        aid = _uuid.UUID(req.actor_id)
    except ValueError:
        raise HTTPException(400, "actor_id inválido")

    probado = False
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        claims = verificar_token(auth_header[7:])
        probado = bool(claims) and claims.get("sub") == str(aid)
    if not probado and req.frase:
        probado = dstore.verificar_frase(aid, req.frase.strip())
    if not probado:
        raise HTTPException(401, "Se requiere sesión activa o tu frase para vincular el dispositivo")

    dstore.registrar_dispositivo(aid, req.token.strip())
    return {"ok": True}


@router.post("/google")
def auth_google(req: GoogleLoginRequest):
    """Find-or-create por Google. Valida el id_token del lado del engine (A4)."""
    from ai_justicia.dossiers import store as dstore
    sub, email = _google_validar_id_token(req.id_token.strip())
    s = dstore.entrar_o_crear_con_google(sub, email)
    return _sesion_resp(s)




class TokenRequest(BaseModel):
    """Intercambio de credenciales por par JWT access+refresh."""
    via: str = Field(..., description="google | frase | dispositivo | nc | refresh")
    credential: str = Field(..., description="Token/frase/refresh_token según vía")
    email: str | None = Field(None, description="solo via=google")
    user: str | None = Field(None, description="solo via=nc: usuario Nextcloud")


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
        actor_id = str(claims["sub"])
        actor_info = {
            "actor_id": actor_id,
            "tipo": claims.get("tier", "ciudadano"),
            "rol": claims.get("rol"),
            "dossier_id": claims.get("dossier"),
        }
        conn.commit(); conn.close()

    elif req.via == "nc":
        # Despacho: valida credenciales contra el Nextcloud del bufete (WebDAV)
        # y mapea el usuario NC al actor con nc_login. La contraseña NO se guarda.
        if not req.user:
            raise HTTPException(400, "via=nc requiere user")
        if not _nc_validar(req.user, req.credential):
            raise HTTPException(401, "Credenciales de Nextcloud incorrectas")
        import psycopg
        conn = psycopg.connect(host=settings.pg_host, port=settings.pg_port,
                               dbname=settings.pg_db, user=settings.pg_user, password=settings.pg_password)
        cur = conn.cursor()
        cur.execute(
            """SELECT a.id, a.bufete_id FROM actores a
               WHERE a.nc_login = %s AND a.bufete_id IS NOT NULL""",
            (req.user,))
        row = cur.fetchone()
        conn.close()
        if not row:
            raise HTTPException(403, "Este usuario de Nextcloud no está vinculado a un despacho")
        actor_info = {"actor_id": str(row[0]), "tipo": "abogado",
                      "bufete_id": str(row[1]), "rol": "abogado"}

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

    # normalizar tier: entrar_con_* devuelve es_abogado; via=nc ya trae tipo
    tier = actor_info.get("tipo")
    if tier is None:
        tier = "abogado" if actor_info.get("es_abogado") else "ciudadano"

    # buscar bufete del actor si es abogado (M2: crea el individual si falta)
    bufete_id = actor_info.get("bufete_id")
    if not bufete_id and tier == "abogado":
        bufete_id = dstore.asegurar_bufete_individual(_uuid.UUID(str(actor_info["actor_id"])))
        bufete_id = str(bufete_id) if bufete_id else None

    # emitir par (dossier activo para ciudadanos — restaura sesión con caso)
    resultado = par_tokens(
        actor_info["actor_id"], tier, bufete_id,
        actor_info.get("rol"), actor_info.get("dossier_id"))

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
