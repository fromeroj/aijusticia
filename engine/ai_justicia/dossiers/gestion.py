"""Gestión de caso: notas, timeline y invitaciones de membresía (U2).

El timeline es la vista viva del caso: union de creación, documentos,
accesos, asignaciones y notas — cada evento con autor y timestamp.
"""
from __future__ import annotations

import hashlib
import secrets
from uuid import UUID

import psycopg

from ai_justicia.config import settings
from ai_justicia.ids import nuevo_id

_TTL_MIEMBRO_HORAS = 7 * 24
_ALFABETO = "23456789ABCDEFGHJKMNPQRSTVWXYZ"


# ── Notas ──────────────────────────────────────────────────────────────────

def crear_nota(dossier_id: UUID, actor_id: UUID, texto: str) -> str:
    nid = nuevo_id()
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO caso_notas (id, dossier_id, actor_id, texto) VALUES (%s, %s, %s, %s)",
                (nid, dossier_id, actor_id, texto.strip()[:2000]))
            conn.commit()
    return str(nid)


def listar_notas(dossier_id: UUID) -> list[dict]:
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT n.id::text, n.texto, n.creado_en, n.actor_id::text,
                          coalesce(a.nc_login, a.email, 'miembro') as autor
                   FROM caso_notas n JOIN actores a ON a.id = n.actor_id
                   WHERE n.dossier_id = %s ORDER BY n.creado_en DESC LIMIT 100""",
                (dossier_id,))
            cols = [c[0] for c in cur.description]
            out = [dict(zip(cols, r)) for r in cur.fetchall()]
    for n in out:
        n["creado_en"] = n["creado_en"].isoformat()
    return out


def borrar_nota(dossier_id: UUID, nota_id: str, actor_id: UUID) -> bool:
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM caso_notas WHERE id = %s AND dossier_id = %s AND actor_id = %s",
                (nota_id, dossier_id, actor_id))
            ok = cur.rowcount > 0
            conn.commit()
    return ok


# ── Timeline ───────────────────────────────────────────────────────────────

def timeline(dossier_id: UUID) -> list[dict]:
    """Eventos del caso en orden cronológico inverso."""
    eventos: list[dict] = []
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT created_at, expediente->>'nombre' FROM dossiers WHERE id = %s""",
                (dossier_id,))
            row = cur.fetchone()
            if row:
                eventos.append({"tipo": "caso_creado", "cuando": row[0].isoformat(),
                                "quien": None, "detalle": row[1] or "Caso iniciado"})
            cur.execute(
                """SELECT d.creado_en, d.nombre, d.metodo_texto,
                          coalesce(a.nc_login, a.email, 'miembro') as autor
                   FROM dossier_documentos d JOIN actores a ON a.id = d.actor_id
                   WHERE d.dossier_id = %s ORDER BY d.creado_en DESC LIMIT 50""",
                (dossier_id,))
            for creado, nombre, metodo, autor in cur.fetchall():
                eventos.append({"tipo": "documento", "cuando": creado.isoformat(),
                                "quien": autor,
                                "detalle": f"{nombre} ({metodo or 'subido'})"})
            cur.execute(
                """SELECT g.creado_en, g.revocado_en, g.rol, g.relacion,
                          coalesce(g.etiqueta, ac.email, b.nombre, 'beneficiario') as quien
                   FROM dossier_accesos g
                   LEFT JOIN actores ac ON ac.id = g.actor_id
                   LEFT JOIN bufetes b ON b.id = g.bufete_id
                   WHERE g.dossier_id = %s ORDER BY g.creado_en DESC LIMIT 50""",
                (dossier_id,))
            for creado, revocado, rol, relacion, quien in cur.fetchall():
                eventos.append({
                    "tipo": "acceso_revocado" if revocado else "acceso_otorgado",
                    "cuando": (revocado or creado).isoformat(), "quien": quien,
                    "detalle": f"{relacion or 'asesor'} · {rol}"})
            cur.execute(
                """SELECT z.creado_en, z.revocada_en, z.rol_en_caso,
                          coalesce(a.nc_login, a.email, 'miembro') as quien
                   FROM caso_asignaciones z JOIN actores a ON a.id = z.actor_id
                   WHERE z.dossier_id = %s ORDER BY z.creado_en DESC LIMIT 50""",
                (dossier_id,))
            for creado, revocada, rol, quien in cur.fetchall():
                eventos.append({
                    "tipo": "asignacion_revocada" if revocada else "asignacion",
                    "cuando": (revocada or creado).isoformat(), "quien": quien,
                    "detalle": rol})
            cur.execute(
                """SELECT n.creado_en, n.texto,
                          coalesce(a.nc_login, a.email, 'miembro') as quien
                   FROM caso_notas n JOIN actores a ON a.id = n.actor_id
                   WHERE n.dossier_id = %s ORDER BY n.creado_en DESC LIMIT 50""",
                (dossier_id,))
            for creado, texto, quien in cur.fetchall():
                eventos.append({"tipo": "nota", "cuando": creado.isoformat(),
                                "quien": quien, "detalle": texto[:120]})
    eventos.sort(key=lambda e: e["cuando"], reverse=True)
    return eventos[:80]


# ── Invitaciones de membresía a la firma ───────────────────────────────────

def _hash_codigo(codigo: str) -> str:
    return hashlib.sha256(codigo.strip().upper().encode()).hexdigest()


def crear_invitacion_miembro(bufete_id: UUID, creada_por: UUID,
                             rol: str = "abogado") -> dict:
    codigo = "".join(secrets.choice(_ALFABETO) for _ in range(8))
    iid = nuevo_id()
    from datetime import datetime, timedelta, timezone
    expira = datetime.now(timezone.utc) + timedelta(hours=_TTL_MIEMBRO_HORAS)
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO bufete_invitaciones (id, bufete_id, creada_por, codigo_hash, rol, expira_en)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (iid, bufete_id, creada_por, _hash_codigo(codigo), rol, expira))
            conn.commit()
    return {"id": str(iid), "codigo": codigo, "rol": rol,
            "expira_en": expira.isoformat()}


def unirse_con_codigo(codigo: str, actor_id: UUID) -> dict:
    """Abogado canjea código de membresía → entra a la firma."""
    h = _hash_codigo(codigo)
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, bufete_id, rol, estado, expira_en FROM bufete_invitaciones
                   WHERE codigo_hash = %s""", (h,))
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": "Código no válido"}
            iid, bufete_id, rol, estado, expira = row
            if estado == "usada":
                return {"ok": False, "error": "Este código ya fue usado"}
            if estado != "activa" or expira < _get_now():
                return {"ok": False, "error": "La invitación expiró o fue revocada"}
            # el actor pasa a la firma (su bufete individual queda atrás)
            cur.execute("UPDATE actores SET bufete_id = %s WHERE id = %s",
                        (bufete_id, actor_id))
            cur.execute(
                """INSERT INTO bufete_miembros (bufete_id, actor_id, rol, invitado_por)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (bufete_id, actor_id) DO UPDATE SET rol = EXCLUDED.rol, estado = 'activo'""",
                (bufete_id, actor_id, rol, (row and None) or actor_id))
            cur.execute("UPDATE bufete_invitaciones SET estado='usada', usada_por=%s, usada_en=now() WHERE id=%s",
                        (actor_id, iid))
            conn.commit()
    return {"ok": True, "bufete_id": str(bufete_id), "rol": rol}


def _get_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
