"""Executor de tools — cada handler llama al store directamente.

Es un wrapper delgado sobre los módulos existentes (dossiers/store,
dossiers/practica, dossiers/boveda, etc.) con autenticación del actor.
"""
from __future__ import annotations
import logging
import uuid as _uuid
from typing import Any

from ai_justicia.tools.registry import ToolContext

logger = logging.getLogger(__name__)


def _uid(s: str) -> _uuid.UUID:
    return _uuid.UUID(s)


def _resolver_caso(nombre: str, ctx: ToolContext) -> dict | None:
    """Busca un caso por nombre (parcial, case-insensitive)."""
    import psycopg
    from ai_justicia.config import settings
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT d.id::text, d.expediente->>'nombre', d.estado
                   FROM dossiers d
                   WHERE d.bufete_id::text = %s
                     AND d.expediente->>'nombre' ILIKE %s
                   LIMIT 1""",
                (ctx.bufete_id, f"%{nombre}%"))
            row = cur.fetchone()
    if not row:
        return None
    return {"id": row[0], "nombre": row[1], "estado": row[2]}


def _resolver_caso_o_error(nombre: str, ctx: ToolContext) -> dict:
    c = _resolver_caso(nombre, ctx)
    if not c:
        raise ValueError(f"No encontré el caso '{nombre}'")
    return c


# ── Handlers ───────────────────────────────────────────────────────────────

def _abrir_caso(ctx: ToolContext, nombre: str, **kw) -> dict:
    c = _resolver_caso_o_error(nombre, ctx)
    return {"accion_ui": {"tipo": "navegar", "destino": "casos", "caso_id": c["id"]},
            "caso": c}


def _crear_caso(ctx: ToolContext, nombre: str, materia: str | None = None,
                descripcion: str | None = None, **kw) -> dict:
    from ai_justicia.dossiers import store as dstore
    if not ctx.bufete_id:
        raise ValueError("Se requiere sesión de despacho para crear casos")
    actor_id, _, bufete_id = None, None, _uid(ctx.bufete_id)
    import psycopg
    from ai_justicia.config import settings
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cid = _uuid.uuid4()
            cur.execute(
                "INSERT INTO actores (id, es_abogado, frase_hash) VALUES (%s, true, 'tmp')",
                (cid,))
            did = _uuid.uuid4()
            exp = {"nombre": nombre, "descripcion": descripcion or ""}
            cur.execute(
                "INSERT INTO dossiers (id, ciudadano_id, materia, expediente, bufete_id) VALUES (%s,%s,%s,%s,%s)",
                (did, cid, materia, __import__("json").dumps(exp), bufete_id))
            conn.commit()
    from ai_justicia.dossiers import store as ds
    ds.asignar_caso(did, bufete_id, _uid(ctx.actor_id), "responsable", _uid(ctx.actor_id))
    return {"accion_ui": {"tipo": "navegar", "destino": "casos", "caso_id": str(did)},
            "caso_id": str(did), "nombre": nombre}


def _listar_casos(ctx: ToolContext, **kw) -> list[dict]:
    import psycopg
    from ai_justicia.config import settings
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT d.expediente->>'nombre', d.estado, d.materia, d.id::text
                   FROM dossiers d WHERE d.bufete_id::text = %s LIMIT 20""",
                (ctx.bufete_id,))
            return [{"nombre": r[0], "estado": r[1], "materia": r[2], "id": r[3]}
                    for r in cur.fetchall()]


def _crear_plazo(ctx: ToolContext, caso: str, titulo: str, fecha: str,
                 fatal: bool = False, tipo: str = "termino", **kw) -> dict:
    from ai_justicia.dossiers import practica
    c = _resolver_caso_o_error(caso, ctx)
    pid = practica.crear_plazo(_uid(c["id"]), _uid(ctx.bufete_id),
                               titulo, fecha, fatal, tipo, _uid(ctx.actor_id))
    return {"plazo_id": pid, "titulo": titulo, "fecha": fecha, "caso": c["nombre"],
            "accion_ui": {"tipo": "navegar", "destino": "agenda"}}


def _listar_plazos(ctx: ToolContext, dias: int = 14, **kw) -> list[dict]:
    from ai_justicia.dossiers import practica
    return practica.plazos_proximos(_uid(ctx.bufete_id), dias)


def _completar_plazo(ctx: ToolContext, plazo_id: str, **kw) -> dict:
    from ai_justicia.dossiers import practica
    ok = practica.completar_plazo(plazo_id, _uid(ctx.bufete_id))
    return {"ok": ok}


def _crear_tarea(ctx: ToolContext, caso: str, titulo: str,
                 asignado_a: str | None = None, vence: str | None = None, **kw) -> dict:
    from ai_justicia.dossiers import practica
    c = _resolver_caso_o_error(caso, ctx)
    asignado_id = None
    if asignado_a:
        # buscar miembro por email o login
        import psycopg
        from ai_justicia.config import settings
        with psycopg.connect(settings.psycopg_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT a.id FROM actores a
                       JOIN bufete_miembros m ON m.actor_id = a.id
                       WHERE m.bufete_id::text = %s AND m.estado='activo'
                         AND (a.email ILIKE %s OR a.nc_login ILIKE %s) LIMIT 1""",
                    (ctx.bufete_id, f"%{asignado_a}%", f"%{asignado_a}%"))
                row = cur.fetchone()
                if row: asignado_id = row[0]
    tid = practica.crear_tarea(_uid(c["id"]), _uid(ctx.bufete_id), titulo,
                               asignado_id, vence, _uid(ctx.actor_id))
    return {"tarea_id": tid, "titulo": titulo, "caso": c["nombre"]}


def _crear_nota(ctx: ToolContext, caso: str, texto: str, **kw) -> dict:
    from ai_justicia.dossiers import gestion
    c = _resolver_caso_o_error(caso, ctx)
    gestion.crear_nota(_uid(c["id"]), _uid(ctx.actor_id), texto)
    return {"ok": True, "caso": c["nombre"], "accion_ui": {"tipo": "refresh"}}


def _compartir_caso(ctx: ToolContext, caso: str, email: str | None = None,
                    rol: str = "lectura", **kw) -> dict:
    from ai_justicia.dossiers import invitaciones
    c = _resolver_caso_o_error(caso, ctx)
    inv = invitaciones.crear_invitacion(_uid(c["id"]), _uid(ctx.actor_id),
                                        relacion="asesor", rol=rol, para_bufete=True)
    url = f"https://aijusticia.mx/reclamar?c={inv['codigo']}"
    if email:
        from ai_justicia.email.cliente import enviar_invitacion_caso
        enviar_invitacion_caso(email, ctx.nombre, inv["codigo"], url)
    return {"codigo": inv["codigo"], "url": url, "expira": inv["expira_en"]}


def _buscar_global(ctx: ToolContext, q: str, **kw) -> dict:
    import psycopg
    from ai_justicia.config import settings
    results = {"casos": [], "clientes": [], "notas": [], "documentos": []}
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT d.id::text, d.expediente->>'nombre', d.estado
                   FROM dossiers d WHERE d.bufete_id::text = %s
                     AND d.expediente->>'nombre' ILIKE %s LIMIT 5""",
                (ctx.bufete_id, f"%{q}%"))
            results["casos"] = [{"id": r[0], "nombre": r[1], "estado": r[2]} for r in cur.fetchall()]
            cur.execute(
                """SELECT id::text, nombre FROM clientes
                   WHERE bufete_id::text = %s AND nombre ILIKE %s LIMIT 5""",
                (ctx.bufete_id, f"%{q}%"))
            results["clientes"] = [{"id": r[0], "nombre": r[1]} for r in cur.fetchall()]
            cur.execute(
                """SELECT n.dossier_id::text, left(n.texto, 80)
                   FROM caso_notas n JOIN dossiers d ON d.id = n.dossier_id
                   WHERE d.bufete_id::text = %s AND n.texto ILIKE %s LIMIT 5""",
                (ctx.bufete_id, f"%{q}%"))
            results["notas"] = [{"caso_id": r[0], "texto": r[1]} for r in cur.fetchall()]
    return results


def _crear_cliente(ctx: ToolContext, nombre: str, tipo: str = "persona_fisica",
                   email: str | None = None, telefono: str | None = None, **kw) -> dict:
    from ai_justicia.dossiers import practica
    cid = practica.crear_cliente(_uid(ctx.bufete_id), nombre, tipo, email, telefono)
    return {"cliente_id": cid, "nombre": nombre}


def _listar_clientes(ctx: ToolContext, **kw) -> list[dict]:
    from ai_justicia.dossiers import practica
    return practica.listar_clientes(_uid(ctx.bufete_id))


def _ver_documento(ctx: ToolContext, caso: str, documento: str, **kw) -> dict:
    import psycopg
    from ai_justicia.config import settings
    c = _resolver_caso_o_error(caso, ctx)
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT nombre, left(texto_extraido, 3000)
                   FROM dossier_documentos
                   WHERE dossier_id::text = %s AND nombre ILIKE %s AND texto_extraido IS NOT NULL
                   ORDER BY creado_en DESC LIMIT 1""",
                (c["id"], f"%{documento}%"))
            row = cur.fetchone()
    if not row:
        return {"error": f"No encontré el documento '{documento}' en el caso '{caso}'"}
    return {"documento": row[0], "texto": row[1]}


def _generar_documento(ctx: ToolContext, caso: str, plantilla: str,
                       variables: dict | None = None, **kw) -> dict:
    from ai_justicia.dossiers import practica  # noqa
    from ai_justicia.jobs.cola import encolar
    c = _resolver_caso_o_error(caso, ctx)
    job_id = encolar("generar_documento", {
        "plantilla": plantilla, "caso_id": c["id"], "variables": variables or {},
        "bufete_id": ctx.bufete_id, "actor_id": ctx.actor_id,
    }, prioridad=2)
    return {"job_id": job_id, "estado": "encolado", "caso": c["nombre"]}


def _revisar_documento(ctx: ToolContext, caso: str, documento: str,
                       instrucciones: str, **kw) -> dict:
    from ai_justicia.dossiers import boveda, revision
    c = _resolver_caso_o_error(caso, ctx)
    import psycopg
    from ai_justicia.config import settings
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id FROM dossier_documentos
                   WHERE dossier_id::text = %s AND nombre ILIKE %s LIMIT 1""",
                (c["id"], f"%{documento}%"))
            row = cur.fetchone()
    if not row:
        raise ValueError(f"No encontré el documento '{documento}'")
    result = revision.revisar_y_editar(_uid(c["id"]), row[0], instrucciones, _uid(ctx.actor_id))
    return {"archivo": result["archivo"], "cambios": result["cambios"][:500]}


def _marcar_confidencial(ctx: ToolContext, caso: str, valor: bool, **kw) -> dict:
    from ai_justicia.dossiers import store as dstore
    c = _resolver_caso_o_error(caso, ctx)
    dstore.marcar_confidencial(_uid(c["id"]), valor)
    return {"ok": True, "confidencial": valor}


def _enviar_email(ctx: ToolContext, to: str, asunto: str, mensaje: str, **kw) -> dict:
    from ai_justicia.email.cliente import _enviar, _base
    ok = _enviar(to, asunto, _base(asunto, f"<p>{mensaje}</p>"))
    return {"ok": ok}


def _registrar_horas(ctx: ToolContext, caso: str, horas: float, concepto: str,
                     facturable: bool = True, **kw) -> dict:
    import psycopg
    from ai_justicia.config import settings
    c = _resolver_caso_o_error(caso, ctx)
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO registro_tiempo (id, dossier_id, bufete_id, actor_id, horas, concepto, facturable)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (_uuid.uuid4(), _uid(c["id"]), _uid(ctx.bufete_id),
                 _uid(ctx.actor_id), horas, concepto, facturable))
            conn.commit()
    return {"ok": True, "horas": horas, "caso": c["nombre"]}


# ── Dispatcher ─────────────────────────────────────────────────────────────

HANDLERS: dict[str, Any] = {
    "abrir_caso": _abrir_caso,
    "crear_caso": _crear_caso,
    "listar_casos": _listar_casos,
    "crear_plazo": _crear_plazo,
    "listar_plazos": _listar_plazos,
    "completar_plazo": _completar_plazo,
    "crear_tarea": _crear_tarea,
    "crear_nota": _crear_nota,
    "compartir_caso": _compartir_caso,
    "buscar_global": _buscar_global,
    "crear_cliente": _crear_cliente,
    "listar_clientes": _listar_clientes,
    "ver_documento": _ver_documento,
    "generar_documento": _generar_documento,
    "revisar_documento": _revisar_documento,
    "marcar_confidencial": _marcar_confidencial,
    "enviar_email": _enviar_email,
    "registrar_horas": _registrar_horas,
}


def ejecutar(tool_name: str, params: dict, ctx: ToolContext) -> Any:
    """Ejecuta una tool con el contexto del actor. Lanza excepción si falla."""
    handler = HANDLERS.get(tool_name)
    if not handler:
        raise ValueError(f"Tool desconocida: {tool_name}")
    return handler(ctx=ctx, **params)
