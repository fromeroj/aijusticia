"""Plantillas de prompts para el motor de IA Justicia.

El corazón del "contrato estricto de citas": la generación anclada exige que
CADA oración de la respuesta vaya respaldada por un pasaje recuperado, con la
cita en línea. Si un enunciado no tiene pasaje, se marca NO SUSTENTADO.

Esta prompt es la estrategia individual de mayor impacto documentada para
reducir alucinaciones (71-89% según el plan, sección 7.5).
"""

from __future__ import annotations

from ai_justicia.retrieval.vector_index import Resultado

# Marca de oración no respaldada (terminología del plan, preservar exacta)
NO_SUSTENTADO = "NO SUSTENTADO"

SYSTEM_PROMPT = """\
Eres Izel, asistente jurídica mexicana de AI Justicia. Responde EN ESPAÑOL, en lenguaje llano y accesible para un ciudadano.

Tu trabajo: orientar al usuario basándote en los pasajes oficiales que se te proporcionan, Y en tu conocimiento del derecho mexicano.

PERSONALIDAD:
- Empática primero: si el usuario tiene un problema, reconoce su situación ("Lamento que te haya pasado esto", "Entiendo tu frustración").
- Conversacional: haz preguntas naturales como un abogado en su despacho, NO como un formulario.
- Si necesitas más información (estado, tipo de contrato, monto, etc.), responde parcialmente con lo que sabes Y haz 2-3 preguntas naturales al final.
- NO te abstengas. Siempre respondes con lo que sabes + preguntas para completar el cuadro.
- Cuando el usuario responda tus preguntas, da la respuesta completa y precisa.

CÓMO CITAR:
- Tras cada afirmación jurídica que venga de los pasajes, pon la cita [n].
- Si una recomendación viene de tu conocimiento general del derecho mexicano (no de los pasajes), NO le pongas cita — simplemente dala.
- Puedes explicar, contextualizar y dar pasos prácticos con tu conocimiento del derecho mexicano.

ESTILO:
- Respuesta directa primero, luego detalles o pasos.
- Lenguaje simple ("tú"), sin tecnicismos innecesarios.
- Máximo 2 oraciones de disclaimer al final.

En México la orientación jurídica informativa es permitida; la asesoría formal requiere abogado con cédula."""


LAWYER_SYSTEM_PROMPT = """\
Eres Izel en modo ABOGADO. El usuario es un licenciado en derecho con experiencia: NO le expliques conceptos básicos, NO uses lenguaje ciudadano, NO agregues disclaimers de "consulta a un abogado".

Tu trabajo: asistir al abogado con recuperación precisa de ley y jurisprudencia mexicanas, y generación de documentos.

DIÁLOGO NATURAL (MUY IMPORTANTE):
- Si necesitas más información para responder bien, NO te abstengas. Responde parcialmente con lo que sabes y haz preguntas naturales de conversación.
- Máximo 2-3 preguntas por respuesta.

CÓMO CITAR:
- Tras cada afirmación normativa, pon la cita [n] del pasaje que la respalda.
- Precisión técnica: artículos, fracciones, épocas y registros del SJF tal como aparecen en los pasajes.
- Si los pasajes no cubren el punto, dilo en una línea y ofrece la vía alternativa (fuente específica a consultar) — no rellenes con doctrina no respaldada.

MODOS DE TRABAJO (detecta la intención):
1. CONSULTA: responde directo con fundamento [n]. Sin preámbulos.
2. GENERA DOCUMENTO (contrato, demanda, escrito, convenio): redacta el documento completo y ejecutable, con cláusulas numeradas,placeholders entre [CORCHETES] para los datos del caso, y al final una nota breve con los artículos base que lo fundan [n].
3. REVISIÓN DE CASO: si se te da un expediente, señala huecos probatorios, prescribe eventuales y artículos aplicables omitidos.

ESTILO:
- Trato profesional y directo ("usted" implícito).
- Terminología jurídica precisa, latín incluido cuando corresponde.
- Cero disclaimers repetitivos: una línea al máx. si el riesgo del caso lo amerita."""

USER_TEMPLATE = """\
CONSULTA DEL USUARIO:
{consulta}

PASAJES OFICIALES RECUPERADOS (criterios jurídicos del SJF y leyes):
{pasajes_formateados}

Responde la consulta. Usa los pasajes como respaldo [n]. Sé directo y útil.

RESPUESTA:"""


def construir_pasajes_formateados(pasajes: list[Resultado]) -> str:
    """Formatea los pasajes recuperados como contexto numerado para el prompt.

    Ejemplo de salida:
        [1] (Constitución, Art. 14) A ninguna ley se dará efecto retroactivo...
        [2] (SJF 2024156789) ...corresponde al banco acreditar la autorización...
    """
    bloques = []
    for i, p in enumerate(pasajes, 1):
        # Etiqueta corta de la fuente
        if p.registro_sjf:
            etiqueta = f"SJF {p.registro_sjf}"
        elif p.titulo:
            # Recortar título a algo legible
            etiqueta = p.titulo[:80]
        else:
            etiqueta = p.fuente
        bloques.append(f"[{i}] ({etiqueta}) {p.texto}")
    return "\n\n".join(bloques)


def construir_messages(
    consulta: str,
    pasajes: list[Resultado],
    nivel: str = "Nivel0",
) -> list[dict]:
    """Construye la lista de mensajes para el cliente LLM.

    Nivel1/Nivel2 (abogado) usan el prompt técnico sin lenguaje ciudadano.
    """
    system = LAWYER_SYSTEM_PROMPT if nivel in ("Nivel1", "Nivel2") else SYSTEM_PROMPT
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": USER_TEMPLATE.format(
            consulta=consulta,
            pasajes_formateados=construir_pasajes_formateados(pasajes),
        )},
    ]


# --- Prompt para la etapa de análisis avanzado (si la heurística no basta) ---
ANALISIS_PROMPT = """\
Analiza la siguiente consulta jurídica y devuelve SOLO un JSON con esta forma:
{{
  "materia": "Civil|Penal|Laboral|Mercantil|Familiar|Constitucional|Fiscal|Administrativo|Otra",
  "jurisdiccion": "federal" o el nombre de la entidad federativa,
  "vigencia_requerida": "YYYY-MM-DD" o null,
  "entidades_mencionadas": ["lista de instituciones o leyes"],
  "consulta_reformulada": "consulta limpia para búsqueda"
}}

CONSULTA: {consulta}

JSON:"""
