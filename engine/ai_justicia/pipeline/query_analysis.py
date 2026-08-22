"""Etapa 1 del pipeline: análisis de la consulta.

Extrae del lenguaje natural del usuario:
  - materia (Civil, Penal, Laboral, Mercantil, ...)
  - jurisdicción (federal o entidad federativa)
  - vigencia requerida (fecha a la que aplica la respuesta)
  - entidades mencionadas (personas, instituciones, leyes citadas)

Esto estructura la consulta y alimenta los filtros de recuperación.
En México es crítica: "la respuesta correcta en Nuevo León puede ser
incorrecta en Chiapas." (Plan, sección 7.5 etapa 1)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import date

from ai_justicia.llm.client import get_llm_client

logger = logging.getLogger(__name__)

ENTIDADES_FEDERATIVAS = {
    "aguascalientes", "baja california", "baja california sur", "campeche",
    "coahuila", "colima", "chiapas", "chihuahua", "ciudad de méxico", "cdmx",
    "durango", "guanajuato", "guerrero", "hidalgo", "jalisco", "estado de méxico",
    "edomex", "michoacán", "morelos", "nayarit", "nuevo león", "oaxaca", "puebla",
    "querétaro", "quintana roo", "san luis potósí", "sinaloa", "sonora", "tabasco",
    "tamaulipas", "tlaxcala", "veracruz", "yucatán", "zacatecas",
}


@dataclass
class AnalisisConsulta:
    """Salida estructurada del análisis de la consulta."""
    materia: str | None
    jurisdiccion: str | None        # 'federal' o nombre de entidad
    vigencia_requerida: date | None
    entidades_mencionadas: list[str]
    # Consulta reformulada para mejor recuperación (sin stopwords, en términos jurídicos)
    consulta_reformulada: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["vigencia_requerida"] = (
            self.vigencia_requerida.isoformat() if self.vigencia_requerida else None
        )
        return d


def analizar_consulta(consulta: str) -> AnalisisConsulta:
    """Analiza la consulta del usuario y devuelve su estructura.

    Usa una combinación de heurística rápida (regex + entidades conocidas) y,
    si hace falta desambiguar, el LLM. Para dev ágil, primero prueba heurística.
    """
    texto = consulta.lower()

    # --- Jurisdicción: buscar entidad federativa mencionada ---
    jurisdiccion: str | None = None
    for ent in ENTIDADES_FEDERATIVAS:
        if ent in texto:
            jurisdiccion = ent.upper() if "cdmx" in ent or "ciudad" in ent else ent.title()
            break

    # --- Materia: palabras clave ---
    materia = _detectar_materia(texto)

    # --- Entidades mencionadas (instituciones) ---
    instituciones = re.findall(
        r"\b(PROFECO|CONDUSEF|SAT|IMSS|INFONAVIT|SJP|SJF|SCJN|DOF|SEP|IFDP)\b",
        consulta, flags=re.IGNORECASE,
    )
    entidades_mencionadas = list({i.upper() for i in instituciones})

    # --- Vigencia: por defecto hoy (la ley vigente) ---
    vigencia = date.today()

    # --- Consulta reformulada: quita muletillas y normaliza ---
    consulta_reformulada = _reformular(consulta)

    return AnalisisConsulta(
        materia=materia,
        jurisdiccion=jurisdiccion,
        vigencia_requerida=vigencia,
        entidades_mencionadas=entidades_mencionadas,
        consulta_reformulada=consulta_reformulada,
    )


_KEYWORDS_MATERIA = {
    "Civil": ["civil", "contrato", "renta", "arrendamiento", "obligación", "daños", "propiedad"],
    "Penal": ["penal", "delito", "robo", "fraude", "denuncia", "ministerio público", "carcel"],
    "Laboral": ["trabajo", "laboral", "despido", "despidieron", "despidie", "me corrieron", "me corrieron", "finiquito", "aguinaldo", "salario", "patrón", "patron", "empleado", "obrero", "jornada", "horas extra", "contrato laboral", "renuncia", "renuncié", "renuncia", "sindical", "contrato colectivo", "prestaciones", "incapacidad", "riesgo de trabajo"],
    "Mercantil": ["bancario", "tarjeta", "cargo", "banco", "condusef", "mercantil", "comercio"],
    "Familiar": ["familia", "divorcio", "pensión", "alimentos", "custodia", "paternidad", "hija", "hijo", "visitas", "mi ex", "convivencia"],
    "Constitucional": ["constitución", "amparo", "garantía", "derechos humanos", "constitucional"],
    "Fiscal": ["fiscal", "impuesto", "sat", "iva", "isr"],
    "Administrativo": ["administrativo", "recurso", "nulidad", "autoridad"],
}


def _detectar_materia(texto: str) -> str | None:
    for materia, keywords in _KEYWORDS_MATERIA.items():
        if any(kw in texto for kw in keywords):
            return materia
    return None


_MULETILLAS = [
    r"^\s*(hola|buenas|buenos días|qué tal|oye|disculpe|disculpa)[,\s]*",
    r"(¿)?\s*(qué|que) (puedo hacer|debo hacer|hago)\s*(\?)?",
    r"(¿)?\s*me (pueden|puedes) (ayudar|decir|explicar)\s*(\?)?",
]


def _reformular(consulta: str) -> str:
    """Limpia la consulta para mejor recuperación BM25/vectorial."""
    texto = consulta.strip()
    for pat in _MULETILLAS:
        texto = re.sub(pat, "", texto, flags=re.IGNORECASE).strip()
    if not texto:
        texto = consulta.strip()  # si todo era muletilla, conserva original
    return texto


# ============================================================
# Expansión de consulta por materia (desambiguación semántica)
# ============================================================

# Cuando el usuario usa palabras ambiguas (ej. "cargo" = cobro bancario vs posición),
# añadimos términos del dominio correcto para guiar al RAG hacia los pasajes adecuados.
_EXPANSION_POR_MATERIA: dict[str, dict[str, list[str]]] = {
    "Mercantil": {
        # Triggers: palabras en la consulta → términos a añadir
        "cargo": ["cargo bancario", "transacción no autorizada", "CONDUSSEF", "institución financiera", "tarjeta"],
        "tarjeta": ["tarjeta de crédito", "tarjeta de débito", "cargo no autorizado", "banco", "CONDUSEF"],
        "banco": ["institución financiera", "cargo bancario", "CONDUSEF", "Ley Fintech", "transacción"],
        "cargo no autorizado": ["transacción no autorizada", "cargo bancario", "CONDUSEF", "reclamación", "devolución"],
        "cobranza": ["cobranza extrajudicial", "CONDUSSER", "Ley Fintech", "deuda", "abuso"],
        "comercio": ["PROFECO", "consumidor", "proveedor", "contrato de adhesión", "Ley Federal de Protección al Consumidor"],
    },
    "Laboral": {
        "despido": ["despido injustificado", "indemnización constitucional", "finiquito", "Ley Federal del Trabajo", "renuncia"],
        "finiquito": ["finiquito", "pago de indemnización", "aguinaldo", "vacaciones", "prima vacacional", "Ley Federal del Trabajo"],
        "salario": ["salario", "pago de salario", "Ley Federal del Trabajo", "jornada", "horas extra"],
        "aguinaldo": ["aguinaldo", "pago anual", "Ley Federal del Trabajo", "trabajador"],
    },
    "Civil": {
        "renta": ["arrendamiento", "contrato de arrendamiento", "casero", "inquilino", "aumento de renta", "Código Civil"],
        "casero": ["arrendador", "contrato de arrendamiento", "renta", "desalojo", "Código Civil"],
        "contrato": ["contrato civil", "obligaciones contractuales", "incumplimiento", "Código Civil"],
        "propiedad": ["propiedad", "posesión", "dominio", "Código Civil"],
    },
    "Familiar": {
        "visitas": ["régimen de visitas", "convivencia", "hijos", "Juzgado Familiar", "pensión alimenticia"],
        "hija": ["régimen de visitas", "convivencia", "hijos", "Juzgado Familiar", "patria potestad"],
        "hijo": ["régimen de visitas", "convivencia", "hijos", "Juzgado Familiar", "patria potestad"],
        "pensión": ["pensión alimenticia", "alimentos", "hijos", "obligación alimentaria", "Juzgado Familiar"],
        "divorcio": ["divorcio", "disolución del matrimonio", "manutención", "Juzgado Familiar"],
        "custodia": ["custodia", "guarda y custodia", "patria potestad", "interés superior del menor"],
    },
    "Penal": {
        "robo": ["robo", "delito patrimonial", "denuncia", "ministerio público", "Código Penal"],
        "fraude": ["fraude", "delito", "engaño", "Código Penal", "ministerio público"],
        "denuncia": ["denuncia", "querella", "ministerio público", "Código Nacional de Procedimientos Penales"],
    },
}


def expandir_consulta(analisis: AnalisisConsulta, consulta_original: str) -> str:
    """Expande la consulta con términos del dominio para mejorar la recuperación.

    Cuando el usuario usa palabras ambiguas, añadimos términos específicos del
    dominio jurídico correcto (detectado por materia) para guiar al RAG.
    """
    if not analisis.materia or analisis.materia not in _EXPANSION_POR_MATERIA:
        return analisis.consulta_reformulada

    expansiones = _EXPANSION_POR_MATERIA[analisis.materia]
    consulta_lower = consulta_original.lower()
    terminos_a_anadir: list[str] = []

    for trigger, terminos in expansiones.items():
        if trigger in consulta_lower:
            # Añadir términos que NO estén ya en la consulta
            for t in terminos:
                if t.lower() not in consulta_lower:
                    terminos_a_anadir.append(t)

    if not terminos_a_anadir:
        return analisis.consulta_reformulada

    # Añadir los términos de expansión al final de la consulta reformulada
    expansion_str = " ".join(terminos_a_anadir[:4])  # máximo 4 términos extra
    return f"{analisis.consulta_reformulada} {expansion_str}"


# --- Etapa 1.5: Normalización jurídica de la consulta ---

_PROMPT_NORMALIZAR = """Convierte la pregunta del ciudadano a terminología jurídica mexicana precisa. Mantén el significado pero usa los términos exactos que aparecerían en leyes, códigos y jurisprudencia.

Ejemplos:
- "mi ex no me deja ver a mi hija" → "régimen de visitas convivencia patria potestad código civil"
- "me deben dinero y no me pagan" → "obligación de pago exigibilidad juicio ejecutivo mercantil"
- "mi casero sube la renta" → "aumento renta arrendamiento arrendador inquilino código civil"
- "me despidieron estando embarazada" → "despido injustificado embarazo protección laboral inamovilidad ley federal del trabajo"
- "me clonaron la tarjeta" → "fraude electrónico transacción no autorizada tarjeta responsabilidad bancaria"

Reglas:
- Responde SOLO con términos jurídicos separados por espacios.
- Incluye el nombre de la ley o código aplicable cuando sea evidente.
- Máximo 20 palabras.
- No expliques, no añadas texto adicional.

Pregunta: {question}

Términos jurídicos:"""


def normalizar_consulta_juridica(consulta: str, materia: str | None = None) -> str:
    """Etapa 1.5: Normaliza la consulta del ciudadano a terminología jurídica.

    Convierte lenguaje coloquial ("mi ex no me deja ver a mi hija") a términos
    que aparecen en leyes ("régimen de visitas patria potestad código civil").

    Esto mejora DRÁSTICAMENTE la recuperación FTS: los términos jurídicos
    coinciden exactamente con el texto de las leyes.

    Usa el LLM con enable_thinking=False (~1s). Si falla, devuelve la
    consulta original (fail-open: mejor buscar con términos del ciudadano
    que no buscar nada).

    Args:
        consulta: Pregunta original del ciudadano.
        materia: Materia detectada (opcional, mejora la precisión).

    Returns:
        Consulta normalizada a terminología jurídica mexicana.
    """
    try:
        client = get_llm_client()
        prompt = _PROMPT_NORMALIZAR.format(question=consulta[:300])
        if materia:
            prompt = f"Contexto: materia {materia}.\n\n{prompt}"

        response = client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=128,
        )

        # Limpiar respuesta
        response = response.strip()
        # Quitar saltos de línea extras
        response = re.sub(r"\s+", " ", response)
        # Si la respuesta es muy corta o muy larga, descartar
        if len(response) < 5 or len(response) > 300:
            logger.warning("Normalización: respuesta fuera de rango, usando original")
            return consulta

        logger.info("Normalización: '%s' → '%s'", consulta[:40], response[:60])
        return response

    except Exception as e:
        logger.warning("Normalización: error (%s), usando consulta original", str(e)[:80])
        return consulta


# --- Etapa 1.6: Contextualización conversacional ---

_PROMPT_CONTEXTUALIZAR = """Reescribe la última pregunta del usuario como una pregunta autónoma y completa, usando el historial de la conversación.

Reglas:
- Resuelve SOLO referencias ambiguas: pronombres ("¿y cuánto tiempo tengo?" → tiempo para QUÉ), "ese", "allí", "el caso".
- La pregunta reescrita debe centrarse en el TEMA PROPIO de la pregunta, no en el historial.
- Si la pregunta introduce un TEMA NUEVO (aunque diga "ya que estamos"), NO antepongas la situación anterior: reescríbela solo sobre el tema nuevo.
- Si la pregunta ya es autónoma, devuélvela igual (sin cambios).
- Responde SOLO con la pregunta reescrita, sin explicaciones. Máximo 40 palabras.

Historial de la conversación:
{historial}

Pregunta del usuario: {consulta}

Pregunta autónoma:"""


def contextualizar_consulta(consulta: str, historial: list[dict] | None) -> str:
    """Etapa 1.6: Contextualiza una pregunta de seguimiento usando el historial.

    En una conversación, las preguntas de seguimiento son ambiguas por sí solas
    ("¿y cuánto tiempo tengo?"). Sin contexto, la recuperación busca en todas
    las materias y devuelve temas no relacionados. Esta etapa reescribe la
    pregunta como autónoma antes de recuperar.

    Ejemplo:
      Historial: [user: "Me despidieron sin motivo...", ...]
      Consulta:  "¿y cuánto tiempo tengo?"
      Salida:    "¿Cuánto tiempo tengo para reclamar el despido injustificado?"

    Fail-open: si no hay historial, es el primer mensaje, o el LLM falla,
    devuelve la consulta original.

    Args:
        consulta: Pregunta nueva del usuario.
        historial: Turnos previos [{role: "user"|"assistant", text: "..."}].

    Returns:
        Consulta autónoma para usar en análisis + recuperación.
    """
    # Sin historial o muy corto → nada que contextualizar
    if not historial:
        return consulta

    turnos = [t for t in historial if isinstance(t, dict) and t.get("text")]
    if not turnos:
        return consulta

    # Formatear los últimos 6 turnos, truncando textos largos
    historial_fmt = []
    for t in turnos[-6:]:
        role = "Usuario" if t.get("role") == "user" else "Asistente"
        texto = re.sub(r"\s+", " ", t["text"]).strip()[:300]
        historial_fmt.append(f"{role}: {texto}")
    historial_str = "\n".join(historial_fmt)

    try:
        client = get_llm_client()
        prompt = _PROMPT_CONTEXTUALIZAR.format(
            historial=historial_str,
            consulta=consulta[:500],
        )

        response = client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=128,
        )

        response = response.strip()
        # Quitar comillas envolventes si las pone
        response = response.strip('"«»')
        response = re.sub(r"\s+", " ", response)

        # Validar: debe ser una pregunta razonable
        if len(response) < 10 or len(response) > 400:
            logger.warning("Contextualización: respuesta fuera de rango, usando original")
            return consulta

        logger.info("Contextualización: '%s' → '%s'", consulta[:40], response[:70])
        return response

    except Exception as e:
        logger.warning("Contextualización: error (%s), usando consulta original", str(e)[:80])
        return consulta


def resumir_contexto_conversacion(historial: list[dict] | None) -> str | None:
    """Produce un contexto breve de la conversación para el filtro de relevancia.

    No usa LLM: toma la primera pregunta del usuario (el tema del caso) y la
    trunca. Suficiente para que el filtro de relevancia sepa de qué va el caso.
    """
    if not historial:
        return None
    for t in historial:
        if t.get("role") == "user" and t.get("text"):
            texto = re.sub(r"\s+", " ", t["text"]).strip()
            return texto[:200]
    return None


# ============================================================
# Detección de información faltante + preguntas aclaratorias
# ============================================================


@dataclass
class PreguntaAclaratoria:
    """Una pregunta que el sistema hace al usuario para completar el contexto."""
    id: str            # 'jurisdiccion', 'materia', 'tiempo_renta', etc.
    texto: str         # "¿En qué estado de la república?"
    tipo: str          # 'texto' | 'opcion' | 'numero'
    opciones: list[str] | None = None  # si tipo='opcion'


# Reglas materia-aware: qué información extra necesitamos según la materia detectada
_PREGUNTAS_POR_MATERIA: dict[str, list[PreguntaAclaratoria]] = {
    "Civil": [
        PreguntaAclaratoria(
            "detalle_civil",
            "¿Tu problema es sobre la casa que rentas, un contrato que firmaste, o algo distinto?",
            "opcion",
            ["Rento una casa o departamento", "Firmé un contrato", "Es sobre una propiedad", "Otra cosa"],
        ),
    ],
    "Laboral": [
        PreguntaAclaratoria(
            "tipo_relacion",
            "¿Qué tipo de trabajo tenías?",
            "opcion",
            ["Trabajaba fijo (tiempo completo)", "Era por temporada o eventual", "Trabajo de confianza", "No estoy seguro"],
        ),
        PreguntaAclaratoria(
            "tiempo_trabajo",
            "¿Cuánto tiempo trabajaste ahí?",
            "opcion",
            ["Menos de 1 año", "Entre 1 y 5 años", "Más de 5 años"],
        ),
    ],
    "Familiar": [
        PreguntaAclaratoria(
            "tipo_caso_familiar",
            "¿Tu problema familiar es sobre qué?",
            "opcion",
            ["Divorcio", "Pensión para mis hijos", "Ver a mis hijos (visitas)", "Custodia", "Otra cosa"],
        ),
    ],
    "Mercantil": [
        PreguntaAclaratoria(
            "tipo_caso_mercantil",
            "¿Tu problema es con el banco, un comercio, o una deuda?",
            "opcion",
            ["El banco me cobró algo que no autorizo", "Problema con una compra o comercio", "Me están cobrando una deuda", "Otra cosa"],
        ),
    ],
}


def detectar_info_faltante(
    analisis: AnalisisConsulta,
    consulta_original: str = "",
) -> list[PreguntaAclaratoria]:
    """Detecta qué información falta para poder orientar bien al usuario.

    Devuelve una lista de preguntas aclaratorias. Si la lista es vacía, no
    hace falta más información y el pipeline puede proceder.
    """
    preguntas: list[PreguntaAclaratoria] = []
    texto = consulta_original.lower()

    # 1. Jurisdicción: crítica en México (la ley cambia por estado)
    if not analisis.jurisdiccion:
        preguntas.append(PreguntaAclaratoria(
            "jurisdiccion",
            "¿En qué estado de la república vives o pasó el problema? (las leyes cambian según el estado)",
            "opcion",
            [
                "Ciudad de México", "Estado de México", "Jalisco", "Nuevo León",
                "Puebla", "Guanajuato", "Veracruz", "Otro / No estoy seguro",
            ],
        ))

    # 2. Preguntas específicas según la materia detectada
    if analisis.materia and analisis.materia in _PREGUNTAS_POR_MATERIA:
        preguntas.extend(_PREGUNTAS_POR_MATERIA[analisis.materia])

    return preguntas


def aplicar_respuestas(
    analisis: AnalisisConsulta,
    respuestas: dict[str, str],
) -> AnalisisConsulta:
    """Aplica las respuestas aclaratorias del usuario al análisis.

    Modifica y devuelve el análisis con la información completada.
    """
    # Jurisdicción
    jurisdiccion = respuestas.get("jurisdiccion", "").strip()
    if jurisdiccion and "no estoy seguro" not in jurisdiccion.lower() and jurisdiccion != "Otro":
        analisis.jurisdiccion = jurisdiccion

    # Enriquecer la consulta reformulada con las respuestas
    extras = []
    for key, val in respuestas.items():
        if key == "jurisdiccion":
            continue  # ya se procesó arriba
        if val and val.strip() and "no estoy seguro" not in val.lower():
            extras.append(val.strip())

    if extras:
        analisis.consulta_reformulada = (
            f"{analisis.consulta_reformulada} "
            f"(Contexto: {'. '.join(extras)})"
        )

    return analisis
