"""Configuración centralizada del motor AI Justicia.

Toda la configuración se carga desde variables de entorno (ver .env.example).
Usar `from ai_justicia.config import settings` en cualquier módulo.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings del motor. Carga desde entorno y/o archivo .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Inferencia (LM Studio / API OpenAI-compatible) ---
    # LLM: apunta a mlx_lm.server (:1235) con LoRA adapter, o LM Studio (:1234)
    lmstudio_base_url: str = "http://localhost:1234/v1"
    lmstudio_api_key: str = "lm-studio"
    lmstudio_llm_model: str = "qwen3.6-35b-a3b"
    lmstudio_embed_model: str = "text-embedding-nomic-embed-text-v1.5"
    # Embeddings: URL separada (siempre LM Studio, aunque el LLM use mlx_lm.server)
    embed_base_url: str = "http://localhost:1234/v1"
    # Timeout de generación en segundos.
    # El modelo carga hasta 262144 tokens de contexto y es de razonamiento:
    # generaciones largas con contexto legal pueden tardar varios minutos.
    llm_timeout: float = 600.0
    # Temperatura base para generación anclada (baja = más determinista)
    llm_temperature: float = 0.1
    # Ruta al adapter LoRA fine-tuned (data/lora_adapter_v5/adapters.safetensors).
    # Para usarlo, cargar el adapter en LM Studio (GUI: Settings → Adapters).
    # En producción con mlx-lm: mlx_lm.load(model, adapter_path=...).
    # Vacío = usar modelo base sin adapter.
    lora_adapter_path: str = ""
    # Habilitar búsqueda vectorial (embeddings). False = solo FTS.
    # Cuando el modelo propio esté listo, activar de nuevo.
    embeddings_habilitados: bool = False

    # --- Entrevista dinámica (ciclo de recaudación de información) ---
    # Rondas de preguntas ANTES de buscar la ley (pre-RAG).
    entrevista_rondas_pre_rag: int = 2
    # Rondas de preguntas DESPUÉS de ver la ley (huecos que la ley revela).
    entrevista_rondas_post_rag: int = 1
    # Máximo de preguntas por ronda.
    entrevista_max_preguntas_por_ronda: int = 3
    # Activar/desactivar la entrevista (False = comportamiento directo anterior).
    entrevista_habilitada: bool = True

    # --- PostgreSQL + pgvector ---
    database_url: str = "postgresql+psycopg://aijusticia:aijusticia@localhost:5433/aijusticia"
    pg_host: str = "localhost"
    pg_port: int = 5433
    pg_db: str = "aijusticia"
    pg_user: str = "aijusticia"
    pg_password: str = "aijusticia"
    # Secret para firmar JWT (HS256) — generar con: openssl rand -hex 32
    jwt_secret: str = "dev-secret-cambiar-en-produccion"

    # --- Pipeline / umbrales ---
    retrieval_quality_threshold: float = 0.20
    retrieval_top_k: int = 8
    rerank_top_k: int = 5
    nli_entailment_threshold: float = 0.40
    abstention_min_backed_ratio: float = 0.30  # dev alpha: permisivo, ajustar con datos

    # --- OCR ---
    tesseract_cmd: str = "/opt/homebrew/bin/tesseract"

    # --- App ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"

    @property
    def psycopg_dsn(self) -> str:
        """DSN para psycopg3 (sin el driver SQLAlchemy)."""
        return (
            f"host={self.pg_host} port={self.pg_port} dbname={self.pg_db} "
            f"user={self.pg_user} password={self.pg_password}"
        )

    @property
    def embedding_dim(self) -> int:
        """Dimensión del modelo nomic-embed-text-v1.5."""
        return 768


@lru_cache
def get_settings() -> Settings:
    """Settings singleton (cacheado)."""
    return Settings()


# Alias global para uso sencillo: `from ai_justicia.config import settings`
settings = get_settings()
