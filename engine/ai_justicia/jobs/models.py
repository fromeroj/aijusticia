"""Modelos de datos para jobs de ingesta on-demand (Caso B)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class EstadoJob(str, Enum):
    """Estados del ciclo de vida de un job de ingesta on-demand."""
    PENDIENTE = "pendiente"          # en cola, esperando al worker
    DESCARGANDO = "descargando"      # el worker está descargando la norma
    INGIRIENDO = "ingiriendo"        # indexando en pgvector + BM25
    COMPLETADO = "completado"        # descarga + reintento listos, respuesta disponible
    FALLIDO = "fallido"              # no se pudo completar (ver `error`)


@dataclass
class PendingJob:
    """Un job de ingesta on-demand en la cola."""
    id: int | None
    consulta: str                    # la consulta original del usuario
    traza_id: int | None             # traza de la primera ejecución (la que detectó Caso B)
    norma_faltante: str | None       # "Ley Fintech" / "SJF 2024156789" / ...
    fuente: str | None               # 'SJF' | 'LeyesBiblio' | 'DOF' | 'GacetaEstatal'
    id_externo: str | None           # registro SJF / ley code si aplica
    estado: EstadoJob
    respuesta: str | None            # respuesta final tras el reintento del pipeline
    traza_reintento: int | None      # traza del reintento
    webhook_url: str | None          # URL a notificar al completar (opcional)
    error: str | None
    created_at: datetime | None
    updated_at: datetime | None
    completed_at: datetime | None
