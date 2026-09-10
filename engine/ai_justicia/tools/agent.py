"""Bucle agéntico de Izel — detecta intención, llama tools, responde.

Cuando el usuario pregunta algo a Izel en /studio, en vez de solo hacer RAG,
el LLM puede:
  1. Responder directamente (conocimiento general + contexto del caso)
  2. Llamar una o más tools (crear plazo, compartir caso, buscar, etc.)
  3. Encadenar tools (buscar caso → crear plazo → enviar email)

El bucle corre hasta 5 iteraciones. Cada tool call se ejecuta contra el
store del engine con el contexto de autenticación del actor.
"""
from __future__ import annotations
import json
import logging
from typing import Any

from ai_justicia.config import settings
from ai_justicia.tools.registry import get_tools_schema, ToolContext
from ai_justicia.tools.executor import ejecutar

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres Izel, asistente jurídica de AI Justicia especializada en derecho mexicano.

Tienes acceso a herramientas (tools) para gestionar casos, plazos, tareas, documentos, clientes y más.
Cuando el usuario pida una acción (crear, abrir, buscar, compartir, agendar, corregir, etc.),
USA las tools disponibles — no solo respondas con texto.

REGLAS:
1. Si el usuario pide una ACCIÓN (crear, abrir, compartir, agendar, buscar, corregir), usa la tool apropiada.
2. Si el usuario hace una PREGUNTA jurídica, responde directamente con tu conocimiento + el contexto del caso.
3. Si necesitas información antes de actuar (ej: "¿cuál caso?"), usa la tool de búsqueda primero.
4. Cuando uses una tool, el sistema te devolverá el resultado — incorpora esa información en tu respuesta final.
5. Si una acción implica navegación (abrir caso, ver agenda), incluye accion_ui en tu respuesta.
6. IMPORTANTE: Cuando ejecutes una tool exitosamente, confirma al usuario qué hiciste de forma natural.
7. Responde SIEMPRE en español mexicano.

CONTEXTO DEL CASO ACTIVO:
{contexto_caso}
"""


async def agentic_query(
    consulta: str,
    ctx: ToolContext,
    contexto_caso: str = "",
    historial: list[dict] | None = None,
) -> dict:
    """Ejecuta el bucle agéntico: detecta herramientas, las llama, responde.

    Retorna: {respuesta, accion_ui, tool_calls_ejecutados, datos}
    """
    from openai import OpenAI

    client = OpenAI(
        base_url=settings.lmstudio_base_url,
        api_key=settings.lmstudio_api_key,
        timeout=120.0,
    )

    system = SYSTEM_PROMPT.format(
        contexto_caso=contexto_caso[:3000] if contexto_caso else "(sin caso activo)"
    )

    messages = [{"role": "system", "content": system}]
    if historial:
        for h in historial[-6:]:
            messages.append({"role": h.get("rol", "user"), "content": h.get("texto", "")})
    messages.append({"role": "user", "content": consulta})

    tools_schema = get_tools_schema()
    tool_calls_ejecutados = []

    for iteration in range(5):
        response = client.chat.completions.create(
            model=settings.lmstudio_llm_model,
            messages=messages,
            tools=tools_schema,
            tool_choice="auto",
            temperature=0.1,
            max_tokens=8000,
        )

        choice = response.choices[0]
        message = choice.message

        # Si el LLM quiere llamar tools
        if message.tool_calls:
            messages.append(message)
            for tc in message.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except json.JSONDecodeError:
                    args = {}

                logger.info("Izel tool call: %s(%s)", name, json.dumps(args, ensure_ascii=False)[:200])

                try:
                    result = ejecutar(name, args, ctx)
                    result_str = json.dumps(result, ensure_ascii=False, default=str)[:4000]
                    tool_calls_ejecutados.append({"tool": name, "args": args, "ok": True})
                except Exception as e:
                    result_str = json.dumps({"error": str(e)[:300]}, ensure_ascii=False)
                    tool_calls_ejecutados.append({"tool": name, "args": args, "ok": False, "error": str(e)[:200]})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })
            continue  # siguiente iteración (el LLM procesa los resultados)

        # El LLM respondió sin tools — respuesta final
        texto = message.content or ""
        accion_ui = None

        # detectar accion_ui en las tools ejecutadas
        for tc in reversed(tool_calls_ejecutados):
            if tc["ok"]:
                # re-ejecutar para obtener accion_ui (el resultado puede tenerla)
                try:
                    result = ejecutar(tc["tool"], tc["args"], ctx)
                    if isinstance(result, dict) and "accion_ui" in result:
                        accion_ui = result["accion_ui"]
                        break
                except Exception:
                    pass

        return {
            "respuesta": texto,
            "accion_ui": accion_ui,
            "tool_calls_ejecutados": tool_calls_ejecutados,
        }

    # agotamos iteraciones
    return {
        "respuesta": "Procesé varias acciones pero necesitaba más pasos. Intenta de nuevo con más detalle.",
        "accion_ui": None,
        "tool_calls_ejecutados": tool_calls_ejecutados,
    }
