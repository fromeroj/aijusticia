"""IDs de la plataforma.

Política (F4b): TODA entidad nueva usa UUID v7 — time-ordered (orden natural
por creación, mejor locality en índices B-tree) y no enumerable, igual que v4.
Los v4 existentes siguen siendo válidos (mismo tipo); no se migran valores.

Capacidades (frases, tokens, códigos de invitación) NO son IDs: son secretos
random con hash en DB, TTL y revocación — ver dossiers/store.py e invitaciones.

PG 16 no trae uuidv7() nativo (llega en PG 18); generamos en la app, así el
esquema es idéntico en cualquier versión.
"""
from __future__ import annotations

import uuid

try:
    _uuid7 = uuid.uuid7  # Python ≥ 3.14
except AttributeError:  # entornos dev < 3.14: v4 (mismo tipo, sin orden)
    _uuid7 = uuid.uuid4


def nuevo_id() -> uuid.UUID:
    """UUID v7 para PKs de entidades."""
    return _uuid7()
