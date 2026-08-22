-- ============================================================
-- AI Justicia — Fase B: Dossiers, Actores, Bufetes, Consentimiento
-- Ejecutar: psql -f scripts/migrate_fase_b.sql
-- ============================================================

-- Bufetes (despachos de abogados) — dueños de adapters privados
CREATE TABLE IF NOT EXISTS bufetes (
    id UUID PRIMARY KEY,
    nombre TEXT NOT NULL,
    dominio_email TEXT,                -- p.ej. 'despacho.mx' para auto-invitar abogados
    verificado BOOLEAN NOT NULL DEFAULT FALSE,
    adapter_version TEXT,              -- checkpoint actual del adapter privado
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Actores: ciudadanos y abogados (binario, como acordamos)
CREATE TABLE IF NOT EXISTS actores (
    id UUID PRIMARY KEY,
    es_abogado BOOLEAN NOT NULL DEFAULT FALSE,
    bufete_id UUID REFERENCES bufetes(id),   -- solo abogados; NULL = independiente
    frase_hash TEXT NOT NULL,          -- Argon2 de la frase (la frase jamás sale del cliente)
    llave_publica BYTEA,               -- X25519 pub (abogados: envelopes al compartir)
    email TEXT,
    cedula TEXT,                       -- solo abogados
    especialidades TEXT[],
    verificado BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Dossiers: el caso del ciudadano
CREATE TABLE IF NOT EXISTS dossiers (
    id UUID PRIMARY KEY,
    ciudadano_id UUID NOT NULL REFERENCES actores(id),
    estado TEXT NOT NULL DEFAULT 'activo',   -- activo|compartido|tomado|cerrado|eliminado
    expediente JSONB NOT NULL DEFAULT '{}',
    materia TEXT,
    jurisdiccion TEXT,
    -- CONSENTIMIENTO (LFPDPPP: expreso, revocable, con timestamp como prueba)
    consentimiento_entrenamiento BOOLEAN NOT NULL DEFAULT FALSE,
    consentimiento_en TIMESTAMPTZ,           -- cuándo lo otorgó
    consentimiento_revocado_en TIMESTAMPTZ,  -- cuándo lo revocó (si aplica)
    consentimiento_version TEXT,             -- versión del aviso que aceptó
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Auditoría del ciclo de entrevista
CREATE TABLE IF NOT EXISTS entrevistas_rondas (
    id BIGSERIAL PRIMARY KEY,
    dossier_id UUID REFERENCES dossiers(id),
    ronda INT NOT NULL,
    fase TEXT NOT NULL,                     -- pre_rag | post_rag
    preguntas JSONB,
    respuestas JSONB,
    expediente_resultante JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Manifest de entrenamiento: qué conversaciones entraron a qué run.
-- Permite honrar revocaciones (excluir del PRÓXIMO run) y auditar.
CREATE TABLE IF NOT EXISTS training_manifest (
    id BIGSERIAL PRIMARY KEY,
    adapter_tipo TEXT NOT NULL,             -- 'general' | 'bufete'
    bufete_id UUID NULL,                    -- solo si adapter_tipo='bufete'
    dossier_ids UUID[] NOT NULL DEFAULT '{}',
    checkpoint TEXT,                        -- ruta del adapter producido
    val_loss REAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Mensajes del dossier (conversación persistida; fuente de datos de entrenamiento)
CREATE TABLE IF NOT EXISTS dossier_mensajes (
    id BIGSERIAL PRIMARY KEY,
    dossier_id UUID NOT NULL REFERENCES dossiers(id),
    rol TEXT NOT NULL,                      -- 'ciudadano' | 'asistente' | 'sistema'
    contenido TEXT NOT NULL,
    expediente_tras JSONB,                  -- expediente resultante (solo rol asistente)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dossiers_ciudadano ON dossiers(ciudadano_id);
CREATE INDEX IF NOT EXISTS idx_dossiers_consentimiento ON dossiers(consentimiento_entrenamiento) WHERE consentimiento_entrenamiento = TRUE;
CREATE INDEX IF NOT EXISTS idx_dossier_mensajes_dossier ON dossier_mensajes(dossier_id);
CREATE INDEX IF NOT EXISTS idx_actores_bufete ON actores(bufete_id);
