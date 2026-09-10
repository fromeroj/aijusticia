-- Chat de Izel por caso — persistente, visible a todos los participantes
CREATE TABLE IF NOT EXISTS caso_chat (
    id BIGSERIAL PRIMARY KEY,
    dossier_id UUID NOT NULL REFERENCES dossiers(id),
    actor_id UUID REFERENCES actores(id),
    rol TEXT NOT NULL CHECK (rol IN ('user','izel')),
    texto TEXT NOT NULL,
    citas JSONB,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_caso ON caso_chat(dossier_id, creado_en);
