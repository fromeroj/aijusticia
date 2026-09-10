"""Gestión práctica del caso: plazos, tareas, clientes (V1 new UI)."""
from __future__ import annotations

from uuid import UUID
from datetime import datetime

import psycopg

from ai_justicia.config import settings
from ai_justicia.ids import nuevo_id


def _conn():
    return psycopg.connect(settings.psycopg_dsn)


# ── Plazos ─────────────────────────────────────────────────────────────────

def crear_plazo(dossier_id: UUID, bufete_id: UUID, titulo: str, fecha,
                fatal: bool = False, tipo: str = "termino",
                creado_por: UUID | None = None) -> str:
    pid = nuevo_id()
    from datetime import datetime as _dt
    if isinstance(fecha, str):
        fecha = _dt.fromisoformat(fecha.replace('Z', '+00:00'))
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO caso_plazos (id, dossier_id, bufete_id, titulo, fecha, fatal, tipo, creado_por)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (pid, dossier_id, bufete_id, titulo[:200], fecha, fatal, tipo, creado_por))
            conn.commit()
    return str(pid)


def listar_plazos(dossier_id: UUID) -> list[dict]:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id::text, titulo, fecha, fatal, tipo, cumplido
                   FROM caso_plazos WHERE dossier_id=%s
                   ORDER BY fecha ASC LIMIT 50""", (dossier_id,))
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


def plazos_proximos(bufete_id: UUID, dias: int = 14) -> list[dict]:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT p.id::text, p.titulo, p.fecha, p.fatal, p.tipo,
                          d.id::text as caso_id, d.expediente->>'nombre' as caso_nombre
                   FROM caso_plazos p JOIN dossiers d ON d.id = p.dossier_id
                   WHERE p.bufete_id=%s AND NOT p.cumplido
                     AND p.fecha <= now() + (%s * interval '1 day')
                   ORDER BY p.fatal DESC, p.fecha ASC LIMIT 30""",
                (bufete_id, dias))
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


def completar_plazo(plazo_id: str, bufete_id: UUID) -> bool:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE caso_plazos SET cumplido=true WHERE id=%s AND bufete_id=%s",
                (plazo_id, bufete_id))
            ok = cur.rowcount > 0
            conn.commit()
    return ok


# ── Tareas ─────────────────────────────────────────────────────────────────

def crear_tarea(dossier_id: UUID, bufete_id: UUID, titulo: str,
                asignado_a: UUID | None = None, vence=None,
                creada_por: UUID | None = None) -> str:
    tid = nuevo_id()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO caso_tareas (id, dossier_id, bufete_id, titulo, asignado_a, vence, creada_por)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (tid, dossier_id, bufete_id, titulo[:200], asignado_a, vence, creada_por))
            conn.commit()
    return str(tid)


def listar_tareas(dossier_id: UUID) -> list[dict]:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT t.id::text, t.titulo, t.vence, t.hecha,
                          coalesce(a.nc_login, a.email, '—') as asignado
                   FROM caso_tareas t LEFT JOIN actores a ON a.id = t.asignado_a
                   WHERE t.dossier_id=%s
                   ORDER BY t.hecha ASC, t.vence ASC NULLS LAST LIMIT 50""",
                (dossier_id,))
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


def toggle_tarea(tarea_id: str, bufete_id: UUID) -> bool:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE caso_tareas
                   SET hecha = NOT hecha, completada_en = CASE WHEN NOT hecha THEN now() ELSE NULL END
                   WHERE id=%s AND bufete_id=%s""",
                (tarea_id, bufete_id))
            ok = cur.rowcount > 0
            conn.commit()
    return ok


# ── Clientes ───────────────────────────────────────────────────────────────

def crear_cliente(bufete_id: UUID, nombre: str, tipo: str = "persona_fisica",
                  email: str | None = None, telefono: str | None = None,
                  notas: str | None = None) -> str:
    cid = nuevo_id()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO clientes (id, bufete_id, nombre, tipo, email, telefono, notas)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (cid, bufete_id, nombre[:200], tipo, email, telefono, notas))
            conn.commit()
    return str(cid)


def listar_clientes(bufete_id: UUID) -> list[dict]:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id::text, nombre, tipo, email, telefono, creado_en::date::text as desde
                   FROM clientes WHERE bufete_id=%s ORDER BY nombre LIMIT 200""",
                (bufete_id,))
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


# ── Dashboard stats ────────────────────────────────────────────────────────

def dashboard(bufete_id: UUID, actor_id: UUID | None = None) -> dict:
    with _conn() as conn:
        with conn.cursor() as cur:
            # casos propios de la firma + compartidos al actor por grant
            cur.execute(
                """SELECT count(*) FROM dossiers d
                   WHERE (d.bufete_id = %s)
                      OR EXISTS (
                          SELECT 1 FROM dossier_accesos g
                          WHERE g.dossier_id = d.id AND g.revocado_en IS NULL
                            AND (g.actor_id = %s OR g.bufete_id = %s))""",
                (bufete_id, actor_id, bufete_id))
            casos = cur.fetchone()[0]
            cur.execute(
                """SELECT count(*) FROM caso_plazos p
                   JOIN dossiers d ON d.id = p.dossier_id
                   WHERE (p.bufete_id = %s)
                      OR EXISTS (
                          SELECT 1 FROM dossier_accesos g
                          WHERE g.dossier_id = d.id AND g.revocado_en IS NULL
                            AND (g.actor_id = %s OR g.bufete_id = %s))
                  AND NOT p.cumplido AND p.fecha <= now() + interval '7 days'""",
                (bufete_id, actor_id, bufete_id))
            plazos_semana = cur.fetchone()[0]
            cur.execute(
                """SELECT count(*) FROM caso_tareas t
                   JOIN dossiers d ON d.id = t.dossier_id
                   WHERE (t.bufete_id = %s)
                      OR EXISTS (
                          SELECT 1 FROM dossier_accesos g
                          WHERE g.dossier_id = d.id AND g.revocado_en IS NULL
                            AND (g.actor_id = %s OR g.bufete_id = %s))
                  AND NOT t.hecha""",
                (bufete_id, actor_id, bufete_id))
            tareas_pend = cur.fetchone()[0]
            cur.execute(
                "SELECT count(*) FROM clientes WHERE bufete_id=%s", (bufete_id,))
            n_clientes = cur.fetchone()[0]
            cur.execute(
                """SELECT count(*) FROM dossier_accesos da
                   WHERE (da.bufete_id=%s OR da.actor_id=%s)
                     AND da.revocado_en IS NULL""",
                (bufete_id, actor_id))
            compartidos = cur.fetchone()[0]
    return {"casos": casos, "plazos_semana": plazos_semana,
            "tareas_pendientes": tareas_pend, "clientes": n_clientes,
            "casos_compartidos": compartidos}
