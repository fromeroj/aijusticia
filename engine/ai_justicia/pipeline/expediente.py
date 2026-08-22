"""Expediente del caso — motor de entrevista dinámica.

El expediente es la memoria estructurada del caso del ciudadano:
hechos extraídos, actores involucrados, materia, jurisdicción y el
estado de las rondas de entrevista. Reemplaza las preguntas fijas
del clarify original por preguntas generadas por LLM según el caso.

Regla federal/estatal:
  - Materias de competencia FEDERAL (laboral, consumidor, fiscal,
    amparo, migratorio) NO requieren preguntar la entidad.
  - Materias de competencia ESTATAL (civil en propiedad/contratos,
    familiar) SÍ la requieren.
  Esto vive en el prompt, no en reglas de código.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from ai_justicia.config import settings

if TYPE_CHECKING:
    from ai_justicia.retrieval.vector_index import Resultado

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------

@dataclass
class Pregunta:
    """Una pregunta de la entrevista, serializable al SSE clarify."""
    id: str
    texto: str
    tipo: str = "texto"                  # 'texto' | 'opcion' | 'numero'
    opciones: list[str] | None = None


@dataclass
class Expediente:
    """Memoria estructurada del caso."""
    materia: str | None = None
    jurisdiccion: str | None = None
    hechos: dict[str, str] = field(default_factory=dict)   # {"donde_vive_menor": "Puebla"}
    actores_caso: list[str] = field(default_factory=list)  # ["madre", "menor de 8 años"]
    rondas_pre_rag: int = 0
    rondas_post_rag: int = 0
    suficiente: bool = False

    def resumen(self) -> str:
        """Versión compacta para inyectar en prompts."""
        partes = []
        if self.materia:
            partes.append(f"Materia: {self.materia}")
        if self.jurisdiccion:
            partes.append(f"Jurisdicción: {self.jurisdiccion}")
        if self.actores_caso:
            partes.append("Actores: " + ", ".join(self.actores_caso))
        if self.hechos:
            hechos = "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in self.hechos.items())
            partes.append(f"Hechos: {hechos}")
        return " | ".join(partes) if partes else "(aún sin datos)"

    def a_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def desde_dict(cls, d: dict | None) -> "Expediente":
        if not d:
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


# ---------------------------------------------------------------------------
# Prompt del entrevistador (una sola llamada: extraer + evaluar + preguntar)
# ---------------------------------------------------------------------------

_PROMPT_ENTREVISTA = """Eres el entrevistador jurídico de AI Justicia. Un ciudadano planteó un caso y tu trabajo es preparar la información mínima para poder buscar la ley aplicable con precisión.

REGLA DE COMPETENCIA (crítica):
- Materias FEDERALES (laboral, consumidor/bancario, fiscal, amparo, migratorio): la ley aplica igual en todo el país. NO preguntes la entidad federativa.
- Materias ESTATALES (civil: propiedad, contratos, arrendamiento; familiar: divorcio, pensión, custodia, visitas): la ley cambia por entidad. SÍ necesitas la entidad donde ocurre el caso o donde viven las personas (p. ej., dónde vive la menor).
- Penal: depende del fuero; pregúntala solo si el delito claramente es estatal.

QUÉ PREGUNTAR:
- Solo hechos que CAMBIEN qué artículo o procedimiento aplica. Nada de curiosidad.
- 1 a {max_preguntas} preguntas, en lenguaje ciudadano, con opciones cerradas cuando sea posible.
- Si preguntas por una UBICACIÓN, las opciones deben ser ENTIDADES FEDERATIVAS (estados: Puebla, Jalisco, Nuevo León, Ciudad de México...), NUNCA ciudades (no "Guadalajara", es "Jalisco").
- NO repitas nada de lo que ya sabes del expediente.
- Si ya tienes suficiente para buscar la ley, marca suficiente=true y no hagas preguntas.

CONTEXTO DE LA CONVERSACIÓN:
{historial}

CONSULTA ACTUAL DEL CIUDADANO:
{consulta}

EXPEDIENTE ACUMULADO:
{expediente}

Devuelve SOLO un JSON:
{{
  "hechos_nuevos": {{"clave_snake_case": "valor"}},
  "actores_caso": ["..."],
  "materia": "..." o null,
  "jurisdiccion": "..." o null,
  "suficiente": true|false,
  "preguntas": [
    {{"id": "clave_snake_case", "texto": "¿...?", "tipo": "opcion", "opciones": ["...", "..."]}}
  ]
}}"""


def actualizar_expediente(
    consulta: str,
    historial: list[dict] | None,
    expediente: Expediente | None = None,
    respuestas_previas: dict[str, str] | None = None,
) -> tuple[Expediente, list[Pregunta]]:
    """Extrae hechos, evalúa suficiencia y genera preguntas dinámicas.

    UNA sola llamada LLM que hace las tres cosas (baja latencia).

    Args:
        consulta: Mensaje actual del ciudadano (ya contextualizado idealmente).
        historial: Turnos previos [{role, text}].
        expediente: Expediente acumulado de rondas anteriores (si hay).
        respuestas_previas: Respuestas de rondas previas {pregunta_id: respuesta}.

    Returns:
        (expediente actualizado, preguntas de esta ronda — vacías si suficiente).
    """
    expediente = expediente or Expediente()

    # Incorporar respuestas previas como hechos conocidos (para que el LLM no re-pregunte)
    contexto_adicional = ""
    if respuestas_previas:
        contexto_adicional = "\nRESPUESTAS ANTERIORES DEL CIUDADANO:\n" + "\n".join(
            f"- {k.replace('_', ' ')}: {v}" for k, v in respuestas_previas.items()
        )

    # Formatear historial (últimos 6 turnos, truncado)
    historial_str = ""
    if historial:
        lineas = []
        for t in historial[-6:]:
            role = "Usuario" if t.get("role") == "user" else "Asistente"
            texto = re.sub(r"\s+", " ", t.get("text", ""))[:300]
            lineas.append(f"{role}: {texto}")
        historial_str = "\n".join(lineas)

    prompt = _PROMPT_ENTREVISTA.format(
        max_preguntas=settings.entrevista_max_preguntas_por_ronda,
        historial=historial_str or "(sin historial)",
        consulta=consulta[:600],
        expediente=expediente.resumen(),
    ) + contexto_adicional

    try:
        from ai_justicia.llm.client import get_llm_client
        client = get_llm_client()
        response = client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=1024,
        )
        data = _parsear_json(response)

        if data is None:
            # Fail-open: no bloquear al usuario por fallo del entrevistador
            expediente.suficiente = True
            return expediente, []

        # Fusionar hechos nuevos (no sobrescribir con nulls/vacíos)
        for k, v in (data.get("hechos_nuevos") or {}).items():
            if v is not None and str(v).strip():
                expediente.hechos[str(k)] = str(v)[:300]

        # Actores: reemplazar si vienen y no están vacíos
        actores = data.get("actores_caso")
        if isinstance(actores, list) and actores:
            expediente.actores_caso = [str(a)[:100] for a in actores][:10]

        # Materia/jurisdicción: solo llenar si vienen y no hay
        materia = data.get("materia")
        if materia and not expediente.materia:
            expediente.materia = str(materia)[:40]
        jur = data.get("jurisdiccion")
        if jur and not expediente.jurisdiccion:
            expediente.jurisdiccion = str(jur)[:60]

        expediente.suficiente = bool(data.get("suficiente", False))

        preguntas = []
        for p in (data.get("preguntas") or [])[: settings.entrevista_max_preguntas_por_ronda]:
            if not isinstance(p, dict) or not p.get("texto"):
                continue
            preguntas.append(Pregunta(
                id=str(p.get("id") or f"p{len(preguntas)}")[:60],
                texto=str(p["texto"])[:300],
                tipo=str(p.get("tipo") or "texto"),
                opciones=[str(o)[:120] for o in (p.get("opciones") or [])][:6] or None,
            ))

        logger.info(
            "Expediente: +hechos=%d, suficiente=%s, preguntas=%d",
            len(data.get("hechos_nuevos") or {}), expediente.suficiente, len(preguntas),
        )
        return expediente, preguntas

    except Exception as e:
        logger.warning("Expediente: error (%s), fail-open a suficiente", str(e)[:80])
        expediente.suficiente = True
        return expediente, []


# ---------------------------------------------------------------------------
# Huecos post-RAG: la ley revela qué falta
# ---------------------------------------------------------------------------

_PROMPT_HUECOS = """Eres analista jurídico. Se buscó la ley aplicable a un caso y obtuviste los artículos recuperados. Tu trabajo: determinar si falta un HECHO CRÍTICO que cambiaría qué norma o procedimiento aplica.

Ejemplos de huecos críticos:
- La ley de visitas distingue padres casados vs concubinatos → si el expediente no dice la unión, pregúntalo.
- La indemnización laboral depende de la antigüedad → si no está, pregúntala.
- La prescripción depende de la fecha del hecho → si no hay fecha, pregúntala.

NO es hueco: información que no cambia el resultado legal, o que ya está en el expediente.

EXPEDIENTE DEL CASO:
{expediente}

CONSULTA ORIGINAL:
{consulta}

ARTÍCULOS RECUPERADOS (extractos):
{pasajes}

Devuelve SOLO un JSON:
{{
  "hay_hueco_critico": true|false,
  "preguntas": [
    {{"id": "clave_snake_case", "texto": "¿...?", "tipo": "opcion", "opciones": ["..."]}}
  ]
}}
Máximo {max_preguntas} preguntas. Si no hay hueco, preguntas vacío."""


def detectar_huecos_post_rag(
    consulta: str,
    expediente: Expediente,
    pasajes: list["Resultado"],
) -> list[Pregunta]:
    """Detecta si los artículos recuperados revelan hechos faltantes críticos.

    Se ejecuta DESPUÉS del RAG, solo si quedan rondas post-RAG disponibles.
    """
    if not pasajes:
        return []

    pasajes_str = "\n\n".join(
        f"[{i+1}] ({p.fuente} / {p.titulo[:60]}) {p.texto[:350]}"
        for i, p in enumerate(pasajes[:5])
    )

    prompt = _PROMPT_HUECOS.format(
        expediente=expediente.resumen(),
        consulta=consulta[:400],
        pasajes=pasajes_str,
        max_preguntas=settings.entrevista_max_preguntas_por_ronda,
    )

    try:
        from ai_justicia.llm.client import get_llm_client
        client = get_llm_client()
        response = client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=768,
        )
        data = _parsear_json(response)
        if not data or not data.get("hay_hueco_critico"):
            return []

        preguntas = []
        for p in (data.get("preguntas") or [])[: settings.entrevista_max_preguntas_por_ronda]:
            if not isinstance(p, dict) or not p.get("texto"):
                continue
            preguntas.append(Pregunta(
                id=str(p.get("id") or f"h{len(preguntas)}")[:60],
                texto=str(p["texto"])[:300],
                tipo=str(p.get("tipo") or "texto"),
                opciones=[str(o)[:120] for o in (p.get("opciones") or [])][:6] or None,
            ))
        logger.info("Huecos post-RAG: %d preguntas", len(preguntas))
        return preguntas

    except Exception as e:
        logger.warning("Huecos post-RAG: error (%s), continúa sin preguntar", str(e)[:80])
        return []


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _parsear_json(texto: str) -> dict | None:
    """Extrae el primer objeto JSON balanceado de la respuesta del LLM."""
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?\s*", "", texto)
    texto = re.sub(r"\s*```$", "", texto).strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass
    for start in range(len(texto)):
        if texto[start] == "{":
            depth, in_str, esc = 0, False, False
            for end in range(start, len(texto)):
                ch = texto[end]
                if esc:
                    esc = False
                    continue
                if ch == "\\":
                    esc = True
                    continue
                if ch == '"':
                    in_str = not in_str
                    continue
                if in_str:
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(texto[start : end + 1])
                        except json.JSONDecodeError:
                            break
            break
    return None
