"""Crea el esquema de la base de datos PostgreSQL + pgvector.

Tablas:
  - documentos: el corpus oficial (DOF, LeyesBiblio, SJF, gacetas) + metadatos
  - documentos_chunks: fragmentos indexados vectorialmente (uno por pasaje)
  - citas: registro de citas verificadas (para trazabilidad y auditoría)
  - trazas: bitácora de cada interacción del pipeline (etapas, scores, abstención)
  - pares_destilacion: pares borrador-IA / aprobación-abogado (volante de datos)

Uso:
    python scripts/setup_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Añadir la raíz del paquete al path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg
from pgvector.psycopg import register_vector

from ai_justicia.config import settings

SCHEMA_SQL = """
-- Extensión pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- documentos: corpus oficial completo (una fila por documento fuente)
-- ============================================================
CREATE TABLE IF NOT EXISTS documentos (
    id              BIGSERIAL PRIMARY KEY,
    fuente          TEXT NOT NULL,          -- 'DOF' | 'LeyesBiblio' | 'SJF' | 'OrdenJuridico' | 'GacetaEstatal'
    entidad         TEXT,                   -- entidad federativa (NULL si federal)
    materia         TEXT,                   -- 'Civil' | 'Penal' | 'Laboral' | 'Administrativo' | ... (NULL si mixto)
    tipo            TEXT,                   -- 'ley' | 'reglamento' | 'jurisprudencia' | 'tesis_aislada' | 'acuerdo' | ...
    titulo          TEXT NOT NULL,
    texto           TEXT NOT NULL,
    -- Claves de verificación de citas (Capa 3)
    registro_sjf    TEXT,                   -- número de registro digital del SJF (si aplica)
    fecha_reforma   DATE,                   -- fecha de reforma en LeyesBiblio (si aplica)
    fecha_publicacion DATE,                 -- fecha de publicación en el DOF (si aplica)
    fecha_vigencia  DATE,                   -- vigencia (NULL = vigente)
    derogado        BOOLEAN NOT NULL DEFAULT FALSE,
    jerarquia       SMALLINT NOT NULL DEFAULT 100,  -- peso jerárquico (art. 133): Constitución=0 > tratados>ley>reglamento>...
    vinculante      BOOLEAN NOT NULL DEFAULT TRUE,  -- jurisprudencia vinculante vs. tesis persuasiva
    -- Metadatos
    url_origen      TEXT,
    raw             JSONB,                  -- datos crudos extraídos de la fuente
    dedup_key       TEXT NOT NULL,          -- clave de idempotencia calculada al insertar
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Idempotencia: un documento se identifica por (fuente, dedup_key)
CREATE UNIQUE INDEX IF NOT EXISTS uq_documento ON documentos (fuente, dedup_key);

CREATE INDEX IF NOT EXISTS idx_documentos_fuente ON documentos (fuente);
CREATE INDEX IF NOT EXISTS idx_documentos_entidad ON documentos (entidad);
CREATE INDEX IF NOT EXISTS idx_documentos_materia ON documentos (materia);
CREATE INDEX IF NOT EXISTS idx_documentos_vigencia ON documentos (fecha_vigencia);
CREATE INDEX IF NOT EXISTS idx_documentos_derogado ON documentos (derogado);

-- ============================================================
-- documentos_chunks: fragmentos para el índice vectorial (un pasaje por fila)
-- El BM25 corre en memoria desde estos textos; pgvector almacena el embedding.
-- ============================================================
CREATE TABLE IF NOT EXISTS documentos_chunks (
    id              BIGSERIAL PRIMARY KEY,
    documento_id    BIGINT NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
    ordinal         INT NOT NULL,           -- orden del chunk dentro del documento
    texto           TEXT NOT NULL,          -- el pasaje (típicamente 200-500 tokens)
    embedding       vector(768),            -- nomic-embed-text-v1.5 = 768 dim
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (documento_id, ordinal)
);

CREATE INDEX IF NOT EXISTS idx_chunks_documento ON documentos_chunks (documento_id);
-- Índice vectorial IVFFlat para búsqueda por similitud (cosine)
CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON documentos_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ============================================================
-- citas: registro de cada cita generada y verificada (trazabilidad)
-- ============================================================
CREATE TABLE IF NOT EXISTS citas (
    id              BIGSERIAL PRIMARY KEY,
    traza_id        BIGINT,                 -- referencia a trazas.id
    oracion         TEXT NOT NULL,          -- la oración de la respuesta que cita
    documento_id    BIGINT REFERENCES documentos(id),
    chunk_id        BIGINT REFERENCES documentos_chunks(id),
    clave_cita      TEXT,                   -- ej. "Art. 14 Ley Fintech", "SJF 2023456"
    -- Resultado de verificación (Capa 3)
    registro_resuelto   BOOLEAN,            -- (a) la cita existe contra el registro real
    nli_label       TEXT,                   -- (b) 'entails' | 'contradice' | 'desconocido'
    nli_score       REAL,                   -- probabilidad del NLI
    sustentado      BOOLEAN NOT NULL DEFAULT FALSE,  -- True si pasa ambos controles
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_citas_traza ON citas (traza_id);
CREATE INDEX IF NOT EXISTS idx_citas_sustentado ON citas (sustentado);

-- ============================================================
-- trazas: bitácora de cada interacción del pipeline (auditoría)
-- ============================================================
CREATE TABLE IF NOT EXISTS trazas (
    id              BIGSERIAL PRIMARY KEY,
    consulta        TEXT NOT NULL,
    -- Salidas de cada etapa
    analisis        JSONB,                  -- etapa 1: materia, jurisdicción, vigencia, entidades
    pasajes         JSONB,                  -- etapa 2-3: pasajes recuperados y rerankeados
    respuesta       TEXT,                   -- etapa 4: texto generado
    -- Verificación (etapa 5)
    n_oraciones     INT,
    n_sustentadas   INT,
    ratio_sustento  REAL,                   -- n_sustentadas / n_oraciones
    abstenido       BOOLEAN NOT NULL DEFAULT FALSE,
    -- Metadatos
    nivel           TEXT,                   -- 'Nivel0' | 'Nivel1' | 'Nivel2'
    tipo_abstencion TEXT,                   -- 'EVIDENCIA_INSUFICIENTE' (Caso A) | 'NORMA_FALTANTE' (Caso B) | NULL
    norma_faltante  TEXT,                   -- si Caso B: la norma identificada como faltante
    duracion_ms     INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trazas_created ON trazas (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trazas_abstencion ON trazas (abstenido);

-- ============================================================
-- pares_destilacion: volante de datos (paso 5 de entrenamiento)
-- pares borrador-IA / versión-aprobada-por-abogado, con consentimiento
-- ============================================================
CREATE TABLE IF NOT EXISTS pares_destilacion (
    id              BIGSERIAL PRIMARY KEY,
    consulta        TEXT NOT NULL,
    borrador_ia     TEXT NOT NULL,          -- lo que generó la IA
    version_abogado TEXT NOT NULL,          -- lo que firmó el abogado
    pasajes         JSONB,                  -- contexto recuperado
    consentimiento  BOOLEAN NOT NULL DEFAULT FALSE,  -- el titular autorizó uso para re-afinado
    validado_por    TEXT,                   -- cédula del abogado validador
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pares_consentimiento ON pares_destilacion (consentimiento) WHERE consentimiento = TRUE;

-- ============================================================
-- pending_jobs: cola de ingesta on-demand (Caso B — norma faltante)
-- ============================================================
CREATE TABLE IF NOT EXISTS pending_jobs (
    id              BIGSERIAL PRIMARY KEY,
    consulta        TEXT NOT NULL,           -- la consulta original del usuario
    traza_id        BIGINT,                  -- traza de la primera ejecución (la que detectó la abstención)
    norma_faltante  TEXT,                    -- "Ley Fintech" / "SJF 2024156789" / ...
    fuente          TEXT,                    -- 'SJF' | 'LeyesBiblio' | 'DOF' | 'GacetaEstatal'
    id_externo      TEXT,                    -- registro SJF / ley code si aplica
    estado          TEXT NOT NULL DEFAULT 'pendiente',
        -- 'pendiente' | 'descargando' | 'ingiriendo' | 'completado' | 'fallido'
    respuesta       TEXT,                    -- respuesta final tras el reintento del pipeline
    traza_reintento BIGINT,                  -- traza del reintento
    webhook_url     TEXT,                    -- URL a notificar al completar (opcional)
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_jobs_estado ON pending_jobs (estado);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON pending_jobs (created_at);
"""


def setup_database() -> None:
    """Crea el esquema completo. Idempotente (CREATE IF NOT EXISTS)."""
def setup_database(drop_existing: bool = False) -> None:
    """Crea el esquema completo. Idempotente (CREATE IF NOT EXISTS).

    Si drop_existing=True, borra las tablas antes (útil cuando el esquema cambia en dev).
    """
    print(f"Conectando a PostgreSQL: {settings.pg_host}:{settings.pg_port}/{settings.pg_db}")
    with psycopg.connect(settings.psycopg_dsn, autocommit=True) as conn:
        # Primero crear la extensión vector, luego registrar el tipo
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        register_vector(conn)

        if drop_existing:
            print("Borrando tablas existentes (--reset)...")
            with conn.cursor() as cur:
                cur.execute(
                    "DROP TABLE IF EXISTS pares_destilacion, citas, trazas, "
                    "documentos_chunks, documentos CASCADE;"
                )

        print("Ejecutando esquema...")
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        print("✓ Esquema creado. Tablas: documentos, documentos_chunks, citas, trazas, pares_destilacion")

        # Verificación
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' ORDER BY table_name"
            )
            tables = [r[0] for r in cur.fetchall()]
        print(f"✓ Tablas presentes: {', '.join(tables)}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Crea el esquema de la base de datos")
    parser.add_argument("--reset", action="store_true", help="Borra las tablas antes de crear (dev)")
    args = parser.parse_args()
    try:
        setup_database(drop_existing=args.reset)
    except psycopg.OperationalError as e:
        print(f"❌ No se pudo conectar a PostgreSQL: {e}", file=sys.stderr)
        print("   ¿Está corriendo el contenedor? `docker compose up -d` desde engine/", file=sys.stderr)
        sys.exit(1)
