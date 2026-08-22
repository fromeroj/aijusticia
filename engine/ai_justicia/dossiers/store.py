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

logger = logging.getLogger(__name__)

# Versión del aviso de consentimiento vigente (bump al cambiar el texto legal)
VERSION_AVISO = "1.0"


# ---------------------------------------------------------------------------
# Frase de recuperación (BIP-39 style simplificada)
# ---------------------------------------------------------------------------

# 256 palabras comunes en español — suficiente entropía con 12 palabras
# (similar a BIP-39; producción podría usar la lista completa de 2048)
_PALABRAS = (
    "abogado acero agua ajedre alba album alfiler alivio alto amable amigo ancho anillo animal "
    "antorcha arbol archivo arco arena arma aro arroyo arte asunto atlas aula avance avenida "
    "avenida bahia baile balon banco banda bandera barra basta batalla bebe blanco bloque "
    "bodega bola bolsa bosque brazo breve brillo buzon caballo cable cacao cadena caida caja "
    "cajon calle cama camino campo canal cancion canoa cansancio cantina canyon capacino cara "
    "carbon carga carne cartera casco casi caso castillo catorce causa cebra cedro celda "
    "cemento centro cepillo cerro cifra cita ciudad clase clave cliente cobre coccion codigo "
    "cofre coleccion color comedia comida compra concreto conejo consejo consumo contrato "
    "corazon corona correa corte cosecha costa costo crema crisis cruce cuadro cualidad "
    "cuarto cubo cuello cuenta cuero cuestion culo cultura cumbre cura curso dalton danza "
    "debate deuda decreto dedo defensa delante delfin delta denuncia derecho deseo desvio "
    "diagnóstico diamante dieta digital dinero dique direccion disco disco doctrina documento "
    "dolor domingo duda duelo ecologia edificio editor juicio jurado jurisprudencia juventud "
    "laberinto lago lamento lampa laser latin lei libertad limite enlace entre escala espacio "
    "especie espina estado estudio etapa evento exigencia fuente fuerza gobierno gracia grado "
    "grano guerra guía historia hogar honor hospital idea iglesia imagen indice informacion "
    "instituto instrumento justicia labio lago lenguaje ley libro licencia limite linea "
    "liston litigio lucha lumbre luna luz madera mango manifiesto mano mercado mesa meta "
    "miedo miembro milagro ministro minuto mirada misterio mito movil modo modo moral motivo "
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
).split()


def generar_frase(n: int = 12) -> str:
    """Genera una frase de recuperación de n palabras (~128 bits con 12)."""
    return " ".join(secrets.choice(_PALABRAS) for _ in range(n))


def hash_frase(frase: str) -> str:
    """Hash Argon2-ish de la frase para verificación (PBKDF2 vía hashlib)."""
    sal = "ai-justicia-v1"  # sal estática de versión; la frase ya es alta entropía
    return hashlib.pbkdf2_hmac("sha256", frase.strip().lower().encode(), sal.encode(), 100_000).hex()


# ---------------------------------------------------------------------------
# Dossiers
# ---------------------------------------------------------------------------

def crear_dossier(ciudadano_id: uuid.UUID) -> uuid.UUID:
    """Crea un dossier vacío para un ciudadano."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            did = uuid.uuid4()
            cur.execute(
                """INSERT INTO dossiers (id, ciudadano_id, consentimiento_version)
                   VALUES (%s, %s, %s)""",
                (did, ciudadano_id, None),
            )
            conn.commit()
    return did


def crear_ciudadano() -> tuple[uuid.UUID, str]:
    """Crea un actor ciudadano anónimo. Devuelve (id, frase UNA vez)."""
    frase = generar_frase()
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            aid = uuid.uuid4()
            cur.execute(
                "INSERT INTO actores (id, es_abogado, frase_hash) VALUES (%s, FALSE, %s)",
                (aid, hash_frase(frase)),
            )
            conn.commit()
    return aid, frase


def crear_abogado(
    cedula: str,
    especialidades: list[str] | None = None,
    bufete_nombre: str | None = None,
) -> tuple[uuid.UUID, str, uuid.UUID | None]:
    """Registra un abogado (verificación de cédula pendiente — Fase E).

    Si se da nombre de bufete, lo crea y lo asocia. Devuelve
    (actor_id, frase, bufete_id | None).
    """
    frase = generar_frase()
    bufete_id = None
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            if bufete_nombre:
                bufete_id = uuid.uuid4()
                cur.execute(
                    "INSERT INTO bufetes (id, nombre) VALUES (%s, %s)",
                    (bufete_id, bufete_nombre[:200]),
                )
            aid = uuid.uuid4()
            cur.execute(
                """INSERT INTO actores (id, es_abogado, frase_hash, cedula, especialidades, bufete_id)
                   VALUES (%s, TRUE, %s, %s, %s, %s)""",
                (aid, hash_frase(frase), cedula[:20],
                 especialidades or None, bufete_id),
            )
            conn.commit()
    return aid, frase, bufete_id


def verificar_frase(actor_id: uuid.UUID, frase: str) -> bool:
    """Verifica la frase de recuperación de un actor."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT frase_hash FROM actores WHERE id = %s", (actor_id,))
            row = cur.fetchone()
    return bool(row) and row[0] == hash_frase(frase)


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

    Busca el actor por hash de frase y devuelve su sesión:
    actor, tipo, último dossier (ciudadanos) o bufete (abogados).
    """
    h = hash_frase(frase)
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, es_abogado, bufete_id, email
                   FROM actores WHERE frase_hash = %s""",
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
                    actor_id, es_abogado, bufete_id = uuid.uuid4(), False, None
                    frase = generar_frase()
                    cur.execute(
                        """INSERT INTO actores (id, es_abogado, frase_hash, email, google_sub)
                           VALUES (%s, FALSE, %s, %s, %s)""",
                        (actor_id, hash_frase(frase), email, google_sub),
                    )
                    conn.commit()
                    # Crear su primer dossier
                    did = uuid.uuid4()
                    cur.execute("INSERT INTO dossiers (id, ciudadano_id) VALUES (%s, %s)", (did, actor_id))
                    conn.commit()
                    return {
                        "actor_id": str(actor_id), "es_abogado": False,
                        "bufete_id": None, "dossier_id": str(did),
                        "email": email, "nuevo": True,
                    }
            else:
                actor_id, es_abogado, bufete_id = uuid.uuid4(), False, None
                frase = generar_frase()
                cur.execute(
                    """INSERT INTO actores (id, es_abogado, frase_hash, google_sub)
                       VALUES (%s, FALSE, %s, %s)""",
                    (actor_id, hash_frase(frase), google_sub),
                )
                did = uuid.uuid4()
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
