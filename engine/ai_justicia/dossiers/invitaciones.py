"""Invitaciones de acceso al caso (F4b + E1 tipadas).

Modelo day-1:
  - relacion: 'parte' (contraparte/colaborador, p.ej. compraventa) | 'asesor' (abogado)
  - para_bufete: la invitación es para UNA FIRMA (canjea un admin; la firma
    recibe el grant y asigna internamente quién trabaja el caso)
  - rol: lectura | edicion (las partes suelen necesitar edicion)
  - etiqueta: cómo se presenta quien entra ("Berto — comprador")

El código sigue siendo una CAPACIDAD: random, hasheado en DB, TTL 72h,
uso único, revocable.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import psycopg

from ai_justicia.config import settings
from ai_justicia.ids import nuevo_id

logger = logging.getLogger(__name__)

TTL_HORAS = 72
CODIGO_LEN = 10
AVISO_VERSION = "casos-compartidos-1.0"
# Crockford base32 sin ambiguos (sin 0/O, 1/I/l, U)
_ALFABETO = "23456789ABCDEFGHJKMNPQRSTVWXYZ"


def _nuevo_codigo() -> str:
    return "".join(secrets.choice(_ALFABETO) for _ in range(CODIGO_LEN))


def _hash_codigo(codigo: str) -> str:
    return hashlib.sha256(codigo.strip().upper().encode()).hexdigest()


def _normalizar(codigo: str) -> str:
    return codigo.strip().upper().replace(" ", "").replace("-", "")


def crear_invitacion(dossier_id: UUID, creada_por: UUID,
                     relacion: str = "asesor", rol: str = "lectura",
                     para_bufete: bool = False,
                     ttl_horas: int = TTL_HORAS) -> dict:
    """Crea una invitación. El código plano se devuelve UNA sola vez."""
    if relacion not in ("parte", "asesor"):
        raise ValueError("relacion inválida")
    if rol not in ("lectura", "edicion"):
        raise ValueError("rol inválido")
    codigo = _nuevo_codigo()
    iid = nuevo_id()
    expira = datetime.now(timezone.utc) + timedelta(hours=ttl_horas)
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE invitaciones_caso SET estado = 'expirada'
                   WHERE dossier_id = %s AND estado IN ('activa','solicitada')
                     AND expira_en < now()""", (dossier_id,))
            cur.execute(
                """INSERT INTO invitaciones_caso
                   (id, dossier_id, creada_por, codigo_hash, expira_en,
                    relacion, rol, para_bufete)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (iid, dossier_id, creada_por, _hash_codigo(codigo), expira,
                 relacion, rol, para_bufete))
            conn.commit()
    logger.info("Invitación %s (%s/%s%s) para dossier %s", iid, relacion, rol,
                " firma" if para_bufete else "", dossier_id)
    return {"id": str(iid), "codigo": codigo, "relacion": relacion, "rol": rol,
            "para_bufete": para_bufete,
            "expira_en": expira.isoformat(), "ttl_horas": ttl_horas}


def canjear(codigo: str, abogado_id: UUID, bufete_del_actor: UUID | None = None,
            etiqueta: str | None = None) -> dict:
    """Canjea el código → solicitud pendiente que el dueño/admin acepta.

    Si la invitación es para firma, el actor debe ser admin de su bufete
    y la solicitud se registra a nombre de la FIRMA (bufete_solicitante).
    """
    h = _hash_codigo(_normalizar(codigo))
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, dossier_id, estado, expira_en, para_bufete, relacion
                   FROM invitaciones_caso WHERE codigo_hash = %s""", (h,))
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": "Código no válido"}
            iid, dossier_id, estado, expira, para_bufete, relacion = row
            if estado == "usada":
                return {"ok": False, "error": "Este código ya fue usado"}
            if estado in ("revocada", "rechazada"):
                return {"ok": False, "error": "Esta invitación fue cancelada"}
            if estado == "solicitada":
                return {"ok": False, "error": "Ya hay una solicitud pendiente con este código"}
            if expira < datetime.now(timezone.utc):
                cur.execute("UPDATE invitaciones_caso SET estado='expirada' WHERE id=%s", (iid,))
                conn.commit()
                return {"ok": False, "error": "El código expiró"}

            bufete_solicitante = None
            if para_bufete:
                if not bufete_del_actor:
                    return {"ok": False,
                            "error": "Esta invitación es para un despacho; entra con tu cuenta de firma"}
                cur.execute(
                    """SELECT rol FROM bufete_miembros
                       WHERE bufete_id = %s AND actor_id = %s AND estado = 'activo'""",
                    (bufete_del_actor, abogado_id))
                m = cur.fetchone()
                if not m or m[0] != "admin":
                    return {"ok": False, "error": "Solo un socio/admin de la firma puede aceptar casos"}
                bufete_solicitante = bufete_del_actor

            cur.execute(
                """UPDATE invitaciones_caso
                   SET estado='solicitada', solicitada_por=%s, solicitada_en=now(),
                       bufete_solicitante=%s, etiqueta=%s
                   WHERE id=%s""",
                (abogado_id, bufete_solicitante,
                 (etiqueta or "").strip()[:60] or None, iid))
            conn.commit()
    return {"ok": True, "invitacion_id": str(iid), "dossier_id": str(dossier_id),
            "para_bufete": para_bufete}


def listar_pendientes(dossier_id: UUID) -> list[dict]:
    """Solicitudes esperando al dueño (para el panel del ciudadano)."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT i.id, i.solicitada_en, i.etiqueta, i.para_bufete,
                          i.bufete_solicitante, i.relacion,
                          a.verificado, a.especialidades,
                          CASE WHEN b.tipo IN ('firma','individual') THEN b.nombre ELSE NULL END as firma
                   FROM invitaciones_caso i
                   JOIN actores a ON a.id = i.solicitada_por
                   LEFT JOIN bufetes b ON b.id = i.bufete_solicitante
                   WHERE i.dossier_id = %s AND i.estado = 'solicitada'
                   ORDER BY i.solicitada_en ASC""",
                (dossier_id,))
            cols = [c[0] for c in cur.description]
            out = []
            for r in cur.fetchall():
                d = dict(zip(cols, r))
                d["id"] = str(d["id"])
                d["solicitada_en"] = d["solicitada_en"].isoformat()
                if d.get("bufete_solicitante"):
                    d["bufete_solicitante"] = str(d["bufete_solicitante"])
                out.append(d)
    return out


def listar_invitaciones(dossier_id: UUID) -> list[dict]:
    """Invitaciones vivas del caso (para que el dueño vea/revoque). Sin códigos."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, estado, creado_en, expira_en, relacion, rol, para_bufete,
                          (expira_en < now()) as vencida
                   FROM invitaciones_caso
                   WHERE dossier_id = %s AND estado IN ('activa','solicitada')
                   ORDER BY creado_en DESC""",
                (dossier_id,))
            cols = [c[0] for c in cur.description]
            out = []
            for r in cur.fetchall():
                d = dict(zip(cols, r))
                d["id"] = str(d["id"])
                d["creado_en"] = d["creado_en"].isoformat()
                d["expira_en"] = d["expira_en"].isoformat()
                out.append(d)
    return out


def aceptar(invitacion_id: UUID, dossier_id: UUID, gestor: UUID) -> bool:
    """El dueño/admin acepta la solicitud → grant tipado. Si es de firma,
    el grant va al bufete y quien canjeó queda asignado como responsable."""
    from ai_justicia.dossiers import store as dstore
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT solicitada_por, bufete_solicitante, relacion, rol, etiqueta
                   FROM invitaciones_caso
                   WHERE id = %s AND dossier_id = %s AND estado = 'solicitada'""",
                (invitacion_id, dossier_id))
            row = cur.fetchone()
            if not row:
                return False
            solicitante, bufete_solicitante, relacion, rol, etiqueta = row
            cur.execute(
                "UPDATE invitaciones_caso SET estado='usada', resuelta_en=now() WHERE id=%s",
                (invitacion_id,))
            conn.commit()

    if bufete_solicitante:
        dstore.otorgar_acceso(dossier_id, gestor, bufete_id=bufete_solicitante,
                              rol="lectura", relacion=relacion,
                              aviso_version=AVISO_VERSION)
        # quien canjeó (admin de la firma) arranca como responsable del caso
        dstore.asignar_caso(dossier_id, bufete_solicitante, solicitante,
                            "responsable", asignado_por=gestor)
    else:
        dstore.otorgar_acceso(dossier_id, gestor, actor_id=solicitante,
                              rol=rol, relacion=relacion, etiqueta=etiqueta,
                              aviso_version=AVISO_VERSION)
    dstore.marcar_estado(dossier_id, "compartido")
    logger.info("Invitación %s aceptada: dossier %s → %s", invitacion_id, dossier_id,
                f"bufete {bufete_solicitante}" if bufete_solicitante else f"actor {solicitante}")
    return True


def rechazar(invitacion_id: UUID, dossier_id: UUID) -> bool:
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE invitaciones_caso
                   SET estado='rechazada', resuelta_en=now()
                   WHERE id=%s AND dossier_id=%s AND estado='solicitada'""",
                (invitacion_id, dossier_id))
            ok = cur.rowcount > 0
            conn.commit()
    return ok


def revocar(invitacion_id: UUID, dossier_id: UUID) -> bool:
    """Dueño/admin cancela una invitación (activa o solicitada)."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE invitaciones_caso
                   SET estado='revocada', revocada_en=now()
                   WHERE id=%s AND dossier_id=%s AND estado IN ('activa','solicitada')""",
                (invitacion_id, dossier_id))
            ok = cur.rowcount > 0
            conn.commit()
    return ok
