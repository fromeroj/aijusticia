"""Chat de Izel por caso — persistente, visible a participantes."""
from __future__ import annotations
import json
import logging
from uuid import UUID

import psycopg
from ai_justicia.config import settings
from ai_justicia.ids import nuevo_id

logger = logging.getLogger(__name__)


def guardar(dossier_id: UUID, rol: str, texto: str,
            actor_id: UUID | None = None, citas: list | None = None) -> int:
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO caso_chat (dossier_id, actor_id, rol, texto, citas)
                   VALUES (%s,%s,%s,%s,%s) RETURNING id""",
                (dossier_id, actor_id, rol, texto[:8000],
                 json.dumps(citas) if citas else None))
            mid = cur.fetchone()[0]
            conn.commit()
    return mid


def listar(dossier_id: UUID, limit: int = 200) -> list[dict]:
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT c.id, c.rol, c.texto, c.citas, c.creado_en,
                          coalesce(a.nc_login, a.email, 'usuario') as autor
                   FROM caso_chat c
                   LEFT JOIN actores a ON a.id = c.actor_id
                   WHERE c.dossier_id = %s
                   ORDER BY c.creado_en ASC LIMIT %s""",
                (dossier_id, limit))
            cols = [c[0] for c in cur.description]
            out = []
            for r in cur.fetchall():
                d = dict(zip(cols, r))
                d["creado_en"] = d["creado_en"].isoformat()
                if d["citas"]:
                    try: d["citas"] = json.loads(d["citas"])
                    except Exception: d["citas"] = None
                out.append(d)
    return out
