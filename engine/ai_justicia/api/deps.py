"""Dependencias comunes de la API (futuro: auth JWT, sesión DB, tenant)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def sse(event: str, data) -> str:
    """Formato Server-Sent Events."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


import json  # noqa: E402  (usado por sse)
