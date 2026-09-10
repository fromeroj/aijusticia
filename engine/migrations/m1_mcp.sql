-- M1: tablas para plataforma action-driven
CREATE TABLE IF NOT EXISTS notificaciones (
    id UUID PRIMARY KEY,
    actor_id UUID NOT NULL REFERENCES actores(id),
    dossier_id UUID REFERENCES dossiers(id),
    tipo TEXT NOT NULL DEFAULT 'info',
    texto TEXT NOT NULL,
    detalle TEXT,
    leida BOOLEAN NOT NULL DEFAULT false,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_notif_actor ON notificaciones(actor_id, leida, creado_en DESC);

CREATE TABLE IF NOT EXISTS registro_tiempo (
    id UUID PRIMARY KEY,
    dossier_id UUID REFERENCES dossiers(id),
    bufete_id UUID NOT NULL REFERENCES bufetes(id),
    actor_id UUID NOT NULL REFERENCES actores(id),
    fecha DATE NOT NULL DEFAULT CURRENT_DATE,
    horas NUMERIC(4,1) NOT NULL,
    concepto TEXT NOT NULL,
    facturable BOOLEAN NOT NULL DEFAULT true,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tiempo_bufete ON registro_tiempo(bufete_id, fecha);

ALTER TABLE dossiers ADD COLUMN IF NOT EXISTS cliente_id UUID REFERENCES clientes(id);
