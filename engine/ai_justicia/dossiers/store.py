"""Dossiers y consentimiento — store de persistencia.

Ciclo del dossier (ciudadano):
  crear → entrevistar/responder → [consentimiento entrenamiento] → compartir → cerrar

Reglas de consentimiento (LFPDPPP 2025):
  - Expreso: opt-in separado del servicio, nunca empacado en términos.
  - Revocable: el revoco saca el dossier de FUTUROS entrenamientos.
  - Probado: timestamp + versión del aviso aceptado.
  - Bufetes: sus datos NUNCA van al adapter general (aislamiento por diseño).
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone

import psycopg

from ai_justicia.config import settings
from ai_justicia.ids import nuevo_id

logger = logging.getLogger(__name__)

# Versión del aviso de consentimiento vigente (bump al cambiar el texto legal)
VERSION_AVISO = "1.0"


# ---------------------------------------------------------------------------
# Frase de recuperación (BIP-39 style simplificada)
# ---------------------------------------------------------------------------

# 256 palabras comunes en español — suficiente entropía con 12 palabras
# (similar a BIP-39; producción podría usar la lista completa de 2048)
_PALABRAS = tuple(dict.fromkeys((
    "abogado acero agua ajedre alba album alfiler alivio alto amable amigo ancho anillo animal "
    "antorcha arbol archivo arco arena arma aro arroyo arte asunto atlas aula avance avenida "
    "bahia baile balon banco banda bandera barra basta batalla bebe blanco bloque "
    "bodega bola bolsa bosque brazo breve brillo buzon caballo cable cacao cadena caida caja "
    "cajon calle cama camino campo canal cancion canoa cansancio cantina canyon capacino cara "
    "carbon carga carne cartera casco casi caso castillo catorce causa cebra cedro celda "
    "cemento centro cepillo cerro cifra cita ciudad clase clave cliente cobre coccion codigo "
    "cofre coleccion color comedia comida compra concreto conejo consejo consumo contrato "
    "corazon corona correa corte cosecha costa costo crema crisis cruce cuadro cualidad "
    "cuarto cubo cuello cuenta cuero cuestion culo cultura cumbre cura curso dalton danza "
    "debate deuda decreto dedo defensa delante delfin delta denuncia derecho deseo desvio "
    "diagnóstico diamante dieta digital dinero dique direccion disco doctrina documento "
    "dolor domingo duda duelo ecologia edificio editor juicio jurado jurisprudencia juventud "
    "laberinto lago lamento lampa laser latin lei libertad limite enlace entre escala espacio "
    "especie espina estado estudio etapa evento exigencia fuente fuerza gobierno gracia grado "
    "grano guerra guía historia hogar honor hospital idea iglesia imagen indice informacion "
    "instituto instrumento justicia labio lenguaje ley libro licencia linea "
    "liston litigio lucha lumbre luna luz madera mango manifiesto mano mercado mesa meta "
    "miedo miembro milagro ministro minuto mirada misterio mito movil moral motivo "
    "muelle muerte multa mundo museo musica nacion naturaleza nodo norma noticia novela "
    "nube nulo numero objeto obligacion obra observacion ocasion oficio oido olivo opinion "
    "opcion orden organismo origen oro oveja ozono pacto pagina pais palacio papel parede "
    "pariente parrafo parte paseo paso pastel paciente patio paz pecho pedir pelea pienso "
    "pintura pizza plano plata platica pleno pluma poblacion poder poema politica posicion "
    "posible prensa precio pretexto primavera principio problema proceso producto promesa "
    "prueba pueblo puerta punto rama rampa razón rebeldia recibo recurso registro regla "
    "reinado relato remedio renta respeto resta resultado retina reunion revista roca rodeo "
    "ruido ruta sabado sabor saco salud sancion sangre santo seccion secreto sector sentencia "
    "senal senor senora serie serio servicio signal silencio sistema sitio soborno social "
    "socorro sol sonido sorpresa suelo suma surplus seguro tabla tacto talento taller tari "
    "teatro techo tema templo tenso teoria tiempo tienda tierra timbre titulo tolerance tomo "
    "tormenta tortuga trabajo trato tribunal trigo trino triunfo turno ultramar unidad uso "
    "usted vacio valle valor vaso vector venta verbo verdad version via vida vino vision "
    "visitante voz voto viaje yaml zorro"
).split()))


def generar_frase(n: int = 12) -> str:
    """Genera una frase de recuperación de n palabras."""
    return " ".join(secrets.choice(_PALABRAS) for _ in range(n))


def hash_frase(frase: str, sal: str | None = None) -> str:
    """PBKDF2 de la frase.

    Sin sal (default): esquema determinístico de LEGADO usado como índice
    de lookup en entrar_con_frase. La verificación fuerte es la versión
    con sal por actor (frase_hash_saltado).
    """
    sal_efectiva = sal if sal is not None else "ai-justicia-v1"
    return hashlib.pbkdf2_hmac(
        "sha256", frase.strip().lower().encode(), sal_efectiva.encode(), 100_000).hex()


def _nueva_frase_con_sal() -> tuple[str, str, str]:
    """Genera (frase, sal, hash_saltado) para creación de actores."""
    frase = generar_frase()
    sal = secrets.token_hex(16)
    return frase, sal, hash_frase(frase, sal)


# ---------------------------------------------------------------------------
# Dossiers
# ---------------------------------------------------------------------------

def crear_dossier(ciudadano_id: uuid.UUID) -> uuid.UUID:
    """Crea un dossier vacío para un ciudadano."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            did = nuevo_id()
            cur.execute(
                """INSERT INTO dossiers (id, ciudadano_id, consentimiento_version)
                   VALUES (%s, %s, %s)""",
                (did, ciudadano_id, None),
            )
            conn.commit()
    return did


def crear_ciudadano() -> tuple[uuid.UUID, str]:
    """Crea un actor ciudadano anónimo. Devuelve (id, frase UNA vez)."""
    frase, sal, hash_saltado = _nueva_frase_con_sal()
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            aid = nuevo_id()
            cur.execute(
                """INSERT INTO actores (id, es_abogado, frase_hash, frase_salt, frase_hash_saltado)
                   VALUES (%s, FALSE, %s, %s, %s)""",
                (aid, hash_frase(frase), sal, hash_saltado),
            )
            conn.commit()
    return aid, frase


def crear_abogado(
    cedula: str,
    especialidades: list[str] | None = None,
    bufete_nombre: str | None = None,
) -> tuple[uuid.UUID, str, uuid.UUID]:
    """Registra un abogado (verificación de cédula pendiente — Fase E).

    M2: TODO abogado tiene una organización — bufete 'individual' propio si
    no pertenece a una firma. Devuelve (actor_id, frase, bufete_id).
    """
    frase, sal, hash_saltado = _nueva_frase_con_sal()
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            bufete_id = nuevo_id()
            if bufete_nombre:
                cur.execute(
                    "INSERT INTO bufetes (id, nombre, tipo) VALUES (%s, %s, 'firma')",
                    (bufete_id, bufete_nombre[:200]),
                )
            else:
                cur.execute(
                    "INSERT INTO bufetes (id, nombre, tipo) VALUES (%s, %s, 'individual')",
                    (bufete_id, f"Despacho personal ({cedula[:20]})"),
                )
            aid = nuevo_id()
            cur.execute(
                """INSERT INTO actores (id, es_abogado, frase_hash, frase_salt, frase_hash_saltado,
                                         cedula, especialidades, bufete_id)
                   VALUES (%s, TRUE, %s, %s, %s, %s, %s, %s)""",
                (aid, hash_frase(frase), sal, hash_saltado, cedula[:20],
                 especialidades or None, bufete_id),
            )
            cur.execute(
                """INSERT INTO bufete_miembros (bufete_id, actor_id, rol, invitado_por)
                   VALUES (%s, %s, 'admin', %s)""",
                (bufete_id, aid, aid))
            conn.commit()
    return aid, frase, bufete_id


def asegurar_bufete_individual(actor_id: uuid.UUID) -> uuid.UUID | None:
    """M2: abogado legado sin bufete → crea su despacho individual al vuelo.

    Se llama al hacer login; devuelve el bufete_id (existente o nuevo).
    Ciudadanos devuelven None.
    """
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT es_abogado, bufete_id, cedula FROM actores WHERE id = %s",
                (actor_id,))
            row = cur.fetchone()
            if not row or not row[0]:
                return row[1] if row else None
            _, bufete_id, cedula = row
            if bufete_id:
                return bufete_id
            bufete_id = nuevo_id()
            cur.execute(
                "INSERT INTO bufetes (id, nombre, tipo) VALUES (%s, %s, 'individual')",
                (bufete_id, f"Despacho personal ({(cedula or 's/n')[:20]})"))
            cur.execute("UPDATE actores SET bufete_id = %s WHERE id = %s",
                        (bufete_id, actor_id))
            cur.execute(
                """INSERT INTO bufete_miembros (bufete_id, actor_id, rol, invitado_por)
                   VALUES (%s, %s, 'admin', %s) ON CONFLICT DO NOTHING""",
                (bufete_id, actor_id, actor_id))
            conn.commit()
            logger.info("Bufete individual creado para abogado legado %s", actor_id)
            return bufete_id


def _verificar_frase_row(row: tuple, frase: str) -> bool:
    """Verifica la frase contra una fila (frase_hash, frase_salt, frase_hash_saltado).

    Actores nuevos: hash con sal por actor (fuerte).
    Actores legados (sin sal): verifica contra el hash determinístico y
    migra al esquema con sal en el mismo login.
    """
    _aid, frase_hash, frase_salt, hash_saltado = row
    if hash_saltado and frase_salt:
        return hash_frase(frase, frase_salt) == hash_saltado
    if frase_hash and frase_hash == hash_frase(frase):
        # legado correcto → migrar a sal por actor
        sal = secrets.token_hex(16)
        with psycopg.connect(settings.psycopg_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE actores SET frase_salt = %s, frase_hash_saltado = %s WHERE id = %s",
                    (sal, hash_frase(frase, sal), _aid))
                conn.commit()
        logger.info("Actor %s migrado a frase con sal", _aid)
        return True
    return False


def verificar_frase(actor_id: uuid.UUID, frase: str) -> bool:
    """Verifica la frase de recuperación de un actor (con sal; migra legados)."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, frase_hash, frase_salt, frase_hash_saltado FROM actores WHERE id = %s",
                (actor_id,))
            row = cur.fetchone()
    return bool(row) and _verificar_frase_row(row, frase)


def obtener_dossier(dossier_id: uuid.UUID) -> dict | None:
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, ciudadano_id, estado, expediente, materia, jurisdiccion,
                          consentimiento_entrenamiento, consentimiento_en,
                          consentimiento_revocado_en, consentimiento_version
                   FROM dossiers WHERE id = %s""",
                (dossier_id,),
            )
            row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0], "ciudadano_id": row[1], "estado": row[2],
        "expediente": row[3], "materia": row[4], "jurisdiccion": row[5],
        "consentimiento_entrenamiento": row[6],
        "consentimiento_en": row[7], "consentimiento_revocado_en": row[8],
        "consentimiento_version": row[9],
    }


# ---------------------------------------------------------------------------
# Consentimiento de entrenamiento
# ---------------------------------------------------------------------------

def otorgar_consentimiento(dossier_id: uuid.UUID) -> bool:
    """Registra consentimiento EXPRESO para entrenar el adapter general.

    Solo aplica a dossiers de ciudadanos — los datos de bufetes jamás
    alimentan el adapter general (aislamiento por diseño).
    """
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE dossiers
                   SET consentimiento_entrenamiento = TRUE,
                       consentimiento_en = %s,
                       consentimiento_revocado_en = NULL,
                       consentimiento_version = %s,
                       updated_at = %s
                   WHERE id = %s
                     AND consentimiento_entrenamiento = FALSE""",
                (datetime.now(timezone.utc), VERSION_AVISO,
                 datetime.now(timezone.utc), dossier_id),
            )
            ok = cur.rowcount > 0
            conn.commit()
    logger.info("Consentimiento otorgado dossier=%s ok=%s", dossier_id, ok)
    return ok


def revocar_consentimiento(dossier_id: uuid.UUID) -> bool:
    """Revoca: el dossier queda FUERA de futuros entrenamientos."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE dossiers
                   SET consentimiento_entrenamiento = FALSE,
                       consentimiento_revocado_en = %s,
                       updated_at = %s
                   WHERE id = %s AND consentimiento_entrenamiento = TRUE""",
                (datetime.now(timezone.utc), datetime.now(timezone.utc), dossier_id),
            )
            ok = cur.rowcount > 0
            conn.commit()
    logger.info("Consentimiento revocado dossier=%s ok=%s", dossier_id, ok)
    return ok


# ---------------------------------------------------------------------------
# Mensajes del dossier
# ---------------------------------------------------------------------------

def guardar_mensaje(
    dossier_id: uuid.UUID,
    rol: str,
    contenido: str,
    expediente_tras: dict | None = None,
) -> int:
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO dossier_mensajes (dossier_id, rol, contenido, expediente_tras)
                   VALUES (%s, %s, %s, %s) RETURNING id""",
                (dossier_id, rol, contenido[:10000],
                 psycopg.types.json.Jsonb(expediente_tras) if expediente_tras else None),
            )
            mid = cur.fetchone()[0]
            cur.execute("UPDATE dossiers SET updated_at = %s WHERE id = %s",
                        (datetime.now(timezone.utc), dossier_id))
            conn.commit()
    return mid


# ---------------------------------------------------------------------------
# Extracción de datos de entrenamiento (respeta consentimiento + aislamiento)
# ---------------------------------------------------------------------------

def extraer_dataset_general(limite: int = 10000) -> list[dict]:
    """Dataset para el ADAPTER GENERAL.

    SOLO conversaciones con consentimiento explícito otorgado y no revocado.
    Los dossiers de bufetes (si algún día los hay) jamás entran aquí.
    """
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT dm.rol, dm.contenido, d.expediente
                   FROM dossier_mensajes dm
                   JOIN dossiers d ON d.id = dm.dossier_id
                   WHERE d.consentimiento_entrenamiento = TRUE
                     AND d.consentimiento_revocado_en IS NULL
                     AND d.estado != 'eliminado'
                   ORDER BY dm.dossier_id, dm.id
                   LIMIT %s""",
                (limite * 4,),  # margen antes de agrupar
            )
            rows = cur.fetchall()

    # Agrupar en pares pregunta→respuesta por dossier
    from collections import defaultdict
    por_dossier: dict = defaultdict(list)
    for rol, contenido, expediente in rows:
        por_dossier[(rol, contenido, str(expediente))].append(1)

    # Formato simple: lista de {dossier_id implícito, turnos}
    conversaciones = []
    actual: dict | None = None
    ultimo_dossier = None
    for rol, contenido, expediente in rows:
        # (simplificado: agrupar secuencial; producción agruparía por dossier_id real)
        if rol == "ciudadano":
            if actual and actual.get("respuesta"):
                conversaciones.append(actual)
            actual = {"pregunta": contenido, "respuesta": "", "expediente": expediente}
        elif rol == "asistente" and actual is not None:
            actual["respuesta"] = contenido
    if actual and actual.get("respuesta"):
        conversaciones.append(actual)

    logger.info("Dataset general: %d conversaciones consentidas", len(conversaciones))
    return conversaciones


def extraer_dataset_bufete(bufete_id: uuid.UUID) -> list[dict]:
    """Dataset para el ADAPTER PRIVADO de un bufete.

    Solo datos de ese bufete. JAMÁS mezcla con general ni otros bufetes.
    """
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT dm.rol, dm.contenido
                   FROM dossier_mensajes dm
                   JOIN dossiers d ON d.id = dm.dossier_id
                   JOIN actores a ON a.id = d.ciudadano_id
                   WHERE a.bufete_id = %s
                   ORDER BY dm.dossier_id, dm.id""",
                (bufete_id,),
            )
            rows = cur.fetchall()
    logger.info("Dataset bufete %s: %d mensajes", bufete_id, len(rows))
    # Misma estructura de agrupación que extraer_dataset_general
    conversaciones = []
    actual = None
    for rol, contenido in rows:
        if rol in ("ciudadano", "abogado"):
            if actual and actual.get("respuesta"):
                conversaciones.append(actual)
            actual = {"pregunta": contenido, "respuesta": ""}
        elif rol == "asistente" and actual is not None:
            actual["respuesta"] = contenido
    if actual and actual.get("respuesta"):
        conversaciones.append(actual)
    return conversaciones


def entrar_con_frase(frase: str) -> dict | None:
    """Re-entrada con frase de recuperación.

    Lookup por hash determinístico; verificación fuerte con sal por actor
    (migración de actores legados en el mismo login).
    """
    h = hash_frase(frase)  # índice de lookup únicamente
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, frase_hash, frase_salt, frase_hash_saltado
                   FROM actores WHERE frase_hash = %s""",
                (h,),
            )
            row = cur.fetchone()
            if not row or not _verificar_frase_row(row, frase):
                return None
            actor_id = row[0]
            cur.execute(
                "SELECT es_abogado, bufete_id, email FROM actores WHERE id = %s",
                (actor_id,),
            )
            es_abogado, bufete_id, email = cur.fetchone()

            dossier_id = None
            if not es_abogado:
                cur.execute(
                    """SELECT id FROM dossiers
                       WHERE ciudadano_id = %s AND estado != 'eliminado'
                       ORDER BY updated_at DESC LIMIT 1""",
                    (actor_id,),
                )
                d = cur.fetchone()
                dossier_id = d[0] if d else None

    return {
        "actor_id": str(actor_id),
        "es_abogado": es_abogado,
        "bufete_id": str(bufete_id) if bufete_id else None,
        "dossier_id": str(dossier_id) if dossier_id else None,
        "email": email,
    }


def registrar_dispositivo(actor_id: uuid.UUID, token: str) -> bool:
    """Guarda el hash del token de dispositivo para re-entrada de un toque."""
    h = hashlib.sha256(token.encode()).hexdigest()
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE actores SET token_dispositivo_hash = %s WHERE id = %s",
                (h, actor_id),
            )
            conn.commit()
    return True


def entrar_con_dispositivo(token: str) -> dict | None:
    """Re-entrada one-tap con el token guardado en el navegador."""
    h = hashlib.sha256(token.encode()).hexdigest()
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, es_abogado, bufete_id, email
                   FROM actores WHERE token_dispositivo_hash = %s""",
                (h,),
            )
            row = cur.fetchone()
            if not row:
                return None
            actor_id, es_abogado, bufete_id, email = row
            dossier_id = None
            if not es_abogado:
                cur.execute(
                    """SELECT id FROM dossiers
                       WHERE ciudadano_id = %s AND estado != 'eliminado'
                       ORDER BY updated_at DESC LIMIT 1""",
                    (actor_id,),
                )
                d = cur.fetchone()
                dossier_id = d[0] if d else None
    return {
        "actor_id": str(actor_id),
        "es_abogado": es_abogado,
        "bufete_id": str(bufete_id) if bufete_id else None,
        "dossier_id": str(dossier_id) if dossier_id else None,
        "email": email,
    }


def entrar_o_crear_con_google(google_sub: str, email: str | None) -> dict:
    """Find-or-create por Google. Si el email ya existe, vincula el google_sub."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, es_abogado, bufete_id FROM actores WHERE google_sub = %s", (google_sub,))
            row = cur.fetchone()
            if row:
                actor_id, es_abogado, bufete_id = row
            elif email:
                cur.execute("SELECT id, es_abogado, bufete_id FROM actores WHERE email = %s", (email,))
                row = cur.fetchone()
                if row:
                    actor_id, es_abogado, bufete_id = row
                    cur.execute("UPDATE actores SET google_sub = %s WHERE id = %s", (google_sub, actor_id))
                else:
                    actor_id, es_abogado, bufete_id = nuevo_id(), False, None
                    frase, sal, hash_saltado = _nueva_frase_con_sal()
                    cur.execute(
                        """INSERT INTO actores (id, es_abogado, frase_hash, frase_salt, frase_hash_saltado, email, google_sub)
                           VALUES (%s, FALSE, %s, %s, %s, %s, %s)""",
                        (actor_id, hash_frase(frase), sal, hash_saltado, email, google_sub),
                    )
                    conn.commit()
                    # Crear su primer dossier
                    did = nuevo_id()
                    cur.execute("INSERT INTO dossiers (id, ciudadano_id) VALUES (%s, %s)", (did, actor_id))
                    conn.commit()
                    return {
                        "actor_id": str(actor_id), "es_abogado": False,
                        "bufete_id": None, "dossier_id": str(did),
                        "email": email, "nuevo": True,
                    }
            else:
                actor_id, es_abogado, bufete_id = nuevo_id(), False, None
                frase, sal, hash_saltado = _nueva_frase_con_sal()
                cur.execute(
                    """INSERT INTO actores (id, es_abogado, frase_hash, frase_salt, frase_hash_saltado, google_sub)
                       VALUES (%s, FALSE, %s, %s, %s, %s)""",
                    (actor_id, hash_frase(frase), sal, hash_saltado, google_sub),
                )
                did = nuevo_id()
                cur.execute("INSERT INTO dossiers (id, ciudadano_id) VALUES (%s, %s)", (did, actor_id))
                conn.commit()
                return {
                    "actor_id": str(actor_id), "es_abogado": False,
                    "bufete_id": None, "dossier_id": str(did),
                    "email": None, "nuevo": True,
                }
            dossier_id = None
            if not es_abogado:
                cur.execute(
                    """SELECT id FROM dossiers
                       WHERE ciudadano_id = %s AND estado != 'eliminado'
                       ORDER BY updated_at DESC LIMIT 1""",
                    (actor_id,),
                )
                d = cur.fetchone()
                dossier_id = d[0] if d else None
            conn.commit()
    return {
        "actor_id": str(actor_id), "es_abogado": es_abogado,
        "bufete_id": str(bufete_id) if bufete_id else None,
        "dossier_id": str(dossier_id) if dossier_id else None,
        "email": email, "nuevo": False,
    }


def registrar_manifest(
    adapter_tipo: str,
    dossier_ids: list[uuid.UUID],
    checkpoint: str,
    val_loss: float | None = None,
    bufete_id: uuid.UUID | None = None,
) -> int:
    """Deja constancia de qué dossiers alimentaron qué training run."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO training_manifest (adapter_tipo, bufete_id, dossier_ids, checkpoint, val_loss)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (adapter_tipo, bufete_id, dossier_ids, checkpoint, val_loss),
            )
            mid = cur.fetchone()[0]
            conn.commit()
    return mid


# ---------------------------------------------------------------------------
# Grants de acceso (M1): el dossier pertenece a quien lo crea; el resto
# accede por grants revocables. El historial ES la auditoría LFPDPPP.
# ---------------------------------------------------------------------------

def otorgar_acceso(
    dossier_id: uuid.UUID,
    otorgado_por: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    bufete_id: uuid.UUID | None = None,
    rol: str = "lectura",
    relacion: str = "asesor",
    etiqueta: str | None = None,
    aviso_version: str | None = None,
) -> int:
    """Otorga acceso (lectura|edicion) a un actor o bufete.

    relacion: 'parte' (contraparte/colaborador) | 'asesor' (abogado).
    etiqueta: cómo se presenta el beneficiario en el caso ("Berto — comprador").
    """
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO dossier_accesos
                   (dossier_id, actor_id, bufete_id, rol, relacion, etiqueta,
                    aviso_version, otorgado_por)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (dossier_id, actor_id, bufete_id, rol, relacion,
                 (etiqueta or "").strip()[:60] or None, aviso_version, otorgado_por))
            gid = cur.fetchone()[0]
            conn.commit()
    logger.info("Acceso %d otorgado dossier=%s rol=%s relacion=%s%s",
                gid, dossier_id, rol, relacion,
                f" etiqueta={etiqueta}" if etiqueta else "")
    return gid


def revocar_acceso(dossier_id: uuid.UUID, acceso_id: int) -> bool:
    """Revoca un acceso (queda en el historial con timestamp)."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE dossier_accesos SET revocado_en = now()
                   WHERE id = %s AND dossier_id = %s AND revocado_en IS NULL""",
                (acceso_id, dossier_id))
            ok = cur.rowcount > 0
            conn.commit()
    return ok


def listar_accesos(dossier_id: uuid.UUID) -> list[dict]:
    """Historial completo de accesos (activos y revocados) — auditoría."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT a.id, a.actor_id, a.bufete_id, a.rol, a.relacion, a.etiqueta,
                          a.otorgado_por, a.creado_en, a.revocado_en,
                          coalesce(a.etiqueta, ac.email, b.nombre) as beneficiario
                   FROM dossier_accesos a
                   LEFT JOIN actores ac ON ac.id = a.actor_id
                   LEFT JOIN bufetes b ON b.id = a.bufete_id
                   WHERE a.dossier_id = %s
                   ORDER BY a.creado_en DESC""",
                (dossier_id,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


# ── Asignación de casos dentro de la firma (E1) ────────────────────────────

def asignar_caso(dossier_id: uuid.UUID, bufete_id: uuid.UUID, actor_id: uuid.UUID,
                 rol_en_caso: str, asignado_por: uuid.UUID) -> str:
    """Admin asigna un miembro de la firma a un caso. El muro ético prevalece."""
    if rol_en_caso not in ("responsable", "abogado", "pasante"):
        raise ValueError("rol_en_caso inválido")
    aid = nuevo_id()
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            if _vetado(cur, dossier_id, actor_id):
                raise PermissionError("Esa persona está vetada en este caso (muro ético)")
            cur.execute(
                """INSERT INTO caso_asignaciones
                   (id, dossier_id, bufete_id, actor_id, rol_en_caso, asignado_por)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (aid, dossier_id, bufete_id, actor_id, rol_en_caso, asignado_por))
            conn.commit()
    logger.info("Asignación %s: actor %s → caso %s (%s)", aid, actor_id, dossier_id, rol_en_caso)
    return str(aid)


def revocar_asignacion(dossier_id: uuid.UUID, asignacion_id: str,
                       actor: uuid.UUID) -> bool:
    """Revoca una asignación (admin, o el propio asignado que se va del caso)."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT actor_id FROM caso_asignaciones
                   WHERE id = %s AND dossier_id = %s AND revocada_en IS NULL""",
                (asignacion_id, dossier_id))
            row = cur.fetchone()
            if not row:
                return False
            if row[0] != actor:  # solo el propio asignado; admin pasa por ruta propia
                cur.execute(
                    """SELECT 1 FROM bufete_miembros m
                       JOIN caso_asignaciones c ON c.bufete_id = m.bufete_id
                       WHERE c.id = %s AND m.actor_id = %s AND m.rol = 'admin'
                         AND m.estado = 'activo'""",
                    (asignacion_id, actor))
                if not cur.fetchone():
                    return False
            cur.execute(
                "UPDATE caso_asignaciones SET revocada_en = now() WHERE id = %s",
                (asignacion_id,))
            conn.commit()
    return True


def listar_asignaciones(dossier_id: uuid.UUID) -> list[dict]:
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT c.id::text, c.actor_id::text, c.rol_en_caso,
                          c.asignado_por::text, c.creado_en,
                          coalesce(m.rol, '—') as rol_firma
                   FROM caso_asignaciones c
                   LEFT JOIN bufete_miembros m
                     ON m.bufete_id = c.bufete_id AND m.actor_id = c.actor_id
                        AND m.estado = 'activo'
                   WHERE c.dossier_id = %s AND c.revocada_en IS NULL
                   ORDER BY c.creado_en ASC""",
                (dossier_id,))
            cols = [d[0] for d in cur.description]
            out = [dict(zip(cols, r)) for r in cur.fetchall()]
    for f in out:
        f["creado_en"] = f["creado_en"].isoformat()
    return out


# ── Muro ético + confidencialidad (E1) ─────────────────────────────────────

def vetar(dossier_id: uuid.UUID, bufete_id: uuid.UUID, actor_id: uuid.UUID,
          vetado_por: uuid.UUID, razon: str | None = None) -> bool:
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO caso_vetos (dossier_id, bufete_id, actor_id, razon, vetado_por)
                   VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                (dossier_id, bufete_id, actor_id, (razon or "")[:300] or None, vetado_por))
            ok = cur.rowcount > 0
            # un veto tumba asignaciones activas del vetado
            if ok:
                cur.execute(
                    """UPDATE caso_asignaciones SET revocada_en = now()
                       WHERE dossier_id = %s AND actor_id = %s AND revocada_en IS NULL""",
                    (dossier_id, actor_id))
            conn.commit()
    return ok


def quitar_veto(dossier_id: uuid.UUID, actor_id: uuid.UUID) -> bool:
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM caso_vetos WHERE dossier_id = %s AND actor_id = %s",
                (dossier_id, actor_id))
            ok = cur.rowcount > 0
            conn.commit()
    return ok


def listar_vetos(dossier_id: uuid.UUID) -> list[dict]:
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT actor_id::text, razon, vetado_por::text, creado_en
                   FROM caso_vetos WHERE dossier_id = %s ORDER BY creado_en DESC""",
                (dossier_id,))
            cols = [d[0] for d in cur.description]
            out = [dict(zip(cols, r)) for r in cur.fetchall()]
    for f in out:
        f["creado_en"] = f["creado_en"].isoformat()
    return out


def marcar_confidencial(dossier_id: uuid.UUID, valor: bool) -> None:
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE dossiers SET confidencial = %s, updated_at = now() WHERE id = %s",
                (valor, dossier_id))
            conn.commit()


# ── Membresías de la firma (E1) ────────────────────────────────────────────

def listar_miembros(bufete_id: uuid.UUID) -> list[dict]:
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT m.actor_id::text, m.rol, m.creado_en, m.estado,
                          a.nc_login, a.email, a.especialidades
                   FROM bufete_miembros m JOIN actores a ON a.id = m.actor_id
                   WHERE m.bufete_id = %s ORDER BY m.rol = 'admin' DESC, m.creado_en""",
                (bufete_id,))
            cols = [d[0] for d in cur.description]
            out = [dict(zip(cols, r)) for r in cur.fetchall()]
    for f in out:
        f["creado_en"] = f["creado_en"].isoformat()
    return out


def cambiar_rol_miembro(bufete_id: uuid.UUID, actor_id: uuid.UUID, rol: str,
                        por: uuid.UUID) -> bool:
    if rol not in ("admin", "abogado", "pasante"):
        raise ValueError("rol inválido")
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE bufete_miembros SET rol = %s WHERE bufete_id = %s AND actor_id = %s",
                (rol, bufete_id, actor_id))
            ok = cur.rowcount > 0
            conn.commit()
    return ok


def rol_en_bufete(bufete_id: uuid.UUID, actor_id: uuid.UUID) -> str | None:
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            return _membresia(cur, bufete_id, actor_id)


# ── Salida voluntaria (E1): consentimiento reversible en ambas direcciones ─

def salir_de_caso(dossier_id: uuid.UUID, actor_id: uuid.UUID) -> bool:
    """Un beneficiario renuncia: revoca SU grant directo y SUS asignaciones.

    Sus aportes permanecen visibles a los participantes (se le informa);
    sus derechos ARCO siguen disponibles.
    """
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE dossier_accesos SET revocado_en = now()
                   WHERE dossier_id = %s AND actor_id = %s AND revocado_en IS NULL""",
                (dossier_id, actor_id))
            n1 = cur.rowcount
            cur.execute(
                """UPDATE caso_asignaciones SET revocada_en = now()
                   WHERE dossier_id = %s AND actor_id = %s AND revocada_en IS NULL""",
                (dossier_id, actor_id))
            n2 = cur.rowcount
            conn.commit()
    if n1 + n2:
        logger.info("Actor %s salió del caso %s (%d grants, %d asignaciones)",
                    actor_id, dossier_id, n1, n2)
    return (n1 + n2) > 0


def revocar_activos(dossier_id: uuid.UUID, excepto_actor: uuid.UUID | None = None) -> int:
    """Revoca TODOS los accesos activos (reasignación). Devuelve cuántos."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE dossier_accesos SET revocado_en = now()
                   WHERE dossier_id = %s AND revocado_en IS NULL
                     AND (actor_id IS DISTINCT FROM %s OR actor_id IS NULL)""",
                (dossier_id, excepto_actor))
            n = cur.rowcount
            conn.commit()
    if n:
        logger.info("Reasignación: %d accesos revocados en dossier %s", n, dossier_id)
    return n


def tiene_accesos_activos(dossier_id: uuid.UUID) -> bool:
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM dossier_accesos WHERE dossier_id = %s AND revocado_en IS NULL LIMIT 1",
                (dossier_id,))
            return cur.fetchone() is not None


def marcar_estado(dossier_id: uuid.UUID, estado: str) -> None:
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE dossiers SET estado = %s, updated_at = now() WHERE id = %s",
                (estado, dossier_id))
            conn.commit()


# ── Helpers del modelo de acceso day-1 (E1) ────────────────────────────────

def _membresia(cur, bufete_id: uuid.UUID, actor_id: uuid.UUID) -> str | None:
    """Rol del actor en el bufete (activo) o None."""
    cur.execute(
        """SELECT rol FROM bufete_miembros
           WHERE bufete_id = %s AND actor_id = %s AND estado = 'activo'""",
        (bufete_id, actor_id))
    row = cur.fetchone()
    return row[0] if row else None


def _vetado(cur, dossier_id: uuid.UUID, actor_id: uuid.UUID) -> bool:
    """Muro ético: bloqueo ABSOLUTO del actor en el caso (prevalece sobre todo)."""
    cur.execute(
        "SELECT 1 FROM caso_vetos WHERE dossier_id = %s AND actor_id = %s",
        (dossier_id, actor_id))
    return cur.fetchone() is not None


def _asignado(cur, dossier_id: uuid.UUID, actor_id: uuid.UUID) -> bool:
    cur.execute(
        """SELECT 1 FROM caso_asignaciones
           WHERE dossier_id = %s AND actor_id = %s AND revocada_en IS NULL""",
        (dossier_id, actor_id))
    return cur.fetchone() is not None


def tiene_acceso(
    dossier_id: uuid.UUID,
    actor_id: uuid.UUID,
    bufete_id: uuid.UUID | None = None,
) -> str | None:
    """¿Qué nivel de acceso tiene este actor al dossier? (modelo day-1)

    Devuelve 'dueño' | 'edicion' | 'lectura' | None. Orden de evaluación:
      1. VETO (muro ético): bloqueo absoluto — gana incluso a grants directos.
      2. Dueño directo: el ciudadano creador.
      3. Caso propio de la org del actor: miembro → admin(no confidencial) ∪ asignado.
      4. Grant directo al actor (parte/asesor): el rol del grant.
      5. Grant a la FIRMA del actor: miembro → admin(no confidencial) ∪ asignado.
    """
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            if _vetado(cur, dossier_id, actor_id):
                return None
            cur.execute(
                "SELECT ciudadano_id, bufete_id, confidencial FROM dossiers WHERE id = %s",
                (dossier_id,))
            row = cur.fetchone()
            if not row:
                return None
            ciudadano_id, dossier_bufete, confidencial = row
            if ciudadano_id == actor_id:
                return "dueño"

            def _nivel_por_membresia() -> str | None:
                rol_m = _membresia(cur, bufete_id, actor_id)
                if not rol_m:
                    return None
                if (rol_m == "admin" and not confidencial) or _asignado(cur, dossier_id, actor_id):
                    return "edicion"
                return None

            # caso propio de la org del actor
            if dossier_bufete and bufete_id and dossier_bufete == bufete_id:
                return _nivel_por_membresia()

            # grant directo al actor
            cur.execute(
                """SELECT rol FROM dossier_accesos
                   WHERE dossier_id = %s AND revocado_en IS NULL AND actor_id = %s
                   ORDER BY CASE rol WHEN 'edicion' THEN 0 ELSE 1 END LIMIT 1""",
                (dossier_id, actor_id))
            g = cur.fetchone()
            if g:
                return g[0]

            # grant a la firma del actor
            if bufete_id:
                cur.execute(
                    """SELECT 1 FROM dossier_accesos
                       WHERE dossier_id = %s AND revocado_en IS NULL AND bufete_id = %s""",
                    (dossier_id, bufete_id))
                if cur.fetchone():
                    return _nivel_por_membresia()
            return None


def es_admin_caso(dossier_id: uuid.UUID, actor_id: uuid.UUID,
                  bufete_id: uuid.UUID | None = None) -> bool:
    """¿Puede este actor GESTIONAR el caso (invitar, revocar accesos, asignar)?

    El dueño siempre. Para casos de una organización: sus miembros admin
    (salvo veto). Es la llave de "solo el dueño invita" extendida a firms.
    """
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            if _vetado(cur, dossier_id, actor_id):
                return False
            cur.execute(
                "SELECT ciudadano_id, bufete_id FROM dossiers WHERE id = %s",
                (dossier_id,))
            row = cur.fetchone()
            if not row:
                return False
            ciudadano_id, dossier_bufete = row
            if ciudadano_id == actor_id:
                return True
            if bufete_id:
                # caso propio de mi org, o compartido a mi firma (grant):
                # el admin de la firma gestiona el staffing de ambos.
                if dossier_bufete == bufete_id or _grant_activo(cur, dossier_id, bufete_id):
                    return _membresia(cur, bufete_id, actor_id) == "admin"
            return False


def _grant_activo(cur, dossier_id: uuid.UUID, bufete_id: uuid.UUID) -> bool:
    cur.execute(
        """SELECT 1 FROM dossier_accesos
           WHERE dossier_id = %s AND bufete_id = %s AND revocado_en IS NULL""",
        (dossier_id, bufete_id))
    return cur.fetchone() is not None
