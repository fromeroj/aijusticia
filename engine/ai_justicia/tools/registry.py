"""Tool Registry para Izel — cada tool es una acción ejecutable.

El LLM (MiniMax M3, OpenAI-compatible) recibe el schema de estas tools
via function calling y decide cuáles invocar. El executor las corre
directamente contra el store (no via HTTP a sí mismo).

Cada tool recibe `ctx: ToolContext` con el actor autenticado.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolContext:
    """Contexto de autenticación para cada tool call."""
    actor_id: str
    bufete_id: str | None = None
    rol: str | None = None
    nombre: str = "usuario"

    @property
    def tiene_firma(self) -> bool:
        return self.bufete_id is not None


# ── JSON schemas para function calling ─────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "abrir_caso",
            "description": "Abre/navega a un caso por nombre. Retorna el caso con su expediente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string", "description": "Nombre o parte del nombre del caso"}
                },
                "required": ["nombre"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "crear_caso",
            "description": "Crea un nuevo caso en el despacho",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string", "description": "Nombre del caso"},
                    "materia": {"type": "string", "enum": ["Civil","Mercantil","Laboral","Familiar","Penal","Amparo","Administrativo","Fiscal"], "description": "Materia jurídica"},
                    "descripcion": {"type": "string", "description": "Descripción del caso"},
                },
                "required": ["nombre"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_casos",
            "description": "Lista los casos visibles para el usuario",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "crear_plazo",
            "description": "Crea un plazo, deadline o evento en el calendario de un caso",
            "parameters": {
                "type": "object",
                "properties": {
                    "caso": {"type": "string", "description": "Nombre del caso"},
                    "titulo": {"type": "string", "description": "Título del plazo (ej: 'Llamada con Pari', 'Audiencia de consiliación')"},
                    "fecha": {"type": "string", "description": "Fecha ISO 8601 (ej: 2026-09-15T09:00:00)"},
                    "fatal": {"type": "boolean", "description": "True si es plazo fatal (preclusión)"},
                    "tipo": {"type": "string", "enum": ["termino","audiencia","vencimiento","entrega","junta"], "description": "Tipo de plazo"},
                },
                "required": ["caso", "titulo", "fecha"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_plazos",
            "description": "Lista los próximos plazos del despacho (o de un caso)",
            "parameters": {
                "type": "object",
                "properties": {
                    "dias": {"type": "integer", "description": "Próximos N días (default 14)"}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "completar_plazo",
            "description": "Marca un plazo como cumplido",
            "parameters": {
                "type": "object",
                "properties": {"plazo_id": {"type": "string"}},
                "required": ["plazo_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "crear_tarea",
            "description": "Crea una tarea asignada a un miembro del despacho",
            "parameters": {
                "type": "object",
                "properties": {
                    "caso": {"type": "string", "description": "Nombre del caso"},
                    "titulo": {"type": "string"},
                    "asignado_a": {"type": "string", "description": "Email o nombre del miembro"},
                    "vence": {"type": "string", "description": "Fecha límite ISO"},
                },
                "required": ["caso", "titulo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "crear_nota",
            "description": "Agrega una nota al caso (visible a participantes)",
            "parameters": {
                "type": "object",
                "properties": {
                    "caso": {"type": "string"},
                    "texto": {"type": "string"},
                },
                "required": ["caso", "texto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compartir_caso",
            "description": "Comparte un caso con un abogado o despacho (genera invitación)",
            "parameters": {
                "type": "object",
                "properties": {
                    "caso": {"type": "string"},
                    "email": {"type": "string", "description": "Email del abogado (opcional, para enviar invitación)"},
                    "rol": {"type": "string", "enum": ["lectura", "edicion"]},
                },
                "required": ["caso"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_global",
            "description": "Búsqueda global en casos, documentos, clientes y notas",
            "parameters": {
                "type": "object",
                "properties": {"q": {"type": "string", "description": "Texto a buscar"}},
                "required": ["q"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "crear_cliente",
            "description": "Registra un cliente nuevo",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string"},
                    "tipo": {"type": "string", "enum": ["persona_fisica", "persona_moral"]},
                    "email": {"type": "string"},
                    "telefono": {"type": "string"},
                },
                "required": ["nombre"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_clientes",
            "description": "Lista los clientes del despacho",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ver_documento",
            "description": "Retorna el texto de un documento del caso",
            "parameters": {
                "type": "object",
                "properties": {
                    "caso": {"type": "string"},
                    "documento": {"type": "string", "description": "Nombre o parte del nombre"},
                },
                "required": ["caso", "documento"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generar_documento",
            "description": "Genera un documento desde plantilla con variables",
            "parameters": {
                "type": "object",
                "properties": {
                    "caso": {"type": "string"},
                    "plantilla": {"type": "string"},
                    "variables": {"type": "object", "description": "Dict de variables para la plantilla"},
                },
                "required": ["caso", "plantilla"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "revisar_documento",
            "description": "Izel revisa y corrige un documento basándose en comentarios y notas",
            "parameters": {
                "type": "object",
                "properties": {
                    "caso": {"type": "string"},
                    "documento": {"type": "string"},
                    "instrucciones": {"type": "string", "description": "Qué corregir"},
                },
                "required": ["caso", "documento", "instrucciones"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "marcar_confidencial",
            "description": "Marca/desmarca un caso como confidencial (solo asignados lo ven)",
            "parameters": {
                "type": "object",
                "properties": {
                    "caso": {"type": "string"},
                    "valor": {"type": "boolean"},
                },
                "required": ["caso", "valor"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "enviar_email",
            "description": "Envía un email desde no-reply@aijusticia.mx",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Email del destinatario"},
                    "asunto": {"type": "string"},
                    "mensaje": {"type": "string"},
                },
                "required": ["to", "asunto", "mensaje"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "registrar_horas",
            "description": "Registra horas trabajadas en un caso",
            "parameters": {
                "type": "object",
                "properties": {
                    "caso": {"type": "string"},
                    "horas": {"type": "number"},
                    "concepto": {"type": "string"},
                    "facturable": {"type": "boolean"},
                },
                "required": ["caso", "horas", "concepto"],
            },
        },
    },
]


def get_tools_schema() -> list[dict]:
    """Retorna el schema de tools para pasarle al LLM."""
    return TOOL_SCHEMAS
