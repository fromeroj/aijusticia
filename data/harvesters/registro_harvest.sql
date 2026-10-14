-- Registro de scripts de cosecha para recolección diferencial.
-- Cada fuente tiene: código del script, watermark/estado, y cómo obtener solo lo nuevo.
CREATE TABLE IF NOT EXISTS harvest_scripts (
    id serial PRIMARY KEY,
    fuente text NOT NULL,              -- fuente en documentos (DOF, SIVEPJ, BJV...)
    nombre text NOT NULL,              -- archivo del script
    descripcion text,
    metodo text,                       -- oai-pmh | api-rest | scraping-playwright | scraping-http | wayback | ocr | manual
    origen_url text,                   -- portal de origen
    ejecucion text,                    -- server-tmux | mac-local | mac-geo-bloqueo
    codigo text,                       -- contenido del script (versión registrada)
    estado jsonb DEFAULT '{}' NOT NULL,-- watermark, contadores, combinaciones hechas
    diferencial text,                  -- estrategia para traer solo lo nuevo
    frecuencia text,                   -- recomendación de re-cosecha
    completa boolean DEFAULT false,    -- universo agotado (solo incrementos futuros)
    ultima_ejecucion timestamptz,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    UNIQUE (fuente, nombre)
);

COMMENT ON TABLE harvest_scripts IS 'Registro de harvesters: código + watermark para recolección diferencial del corpus';
COMMENT ON COLUMN harvest_scripts.estado IS 'Estado serializado del harvester (ej: fecha watermark, combos hechos, páginas)';
COMMENT ON COLUMN harvest_scripts.diferencial IS 'Cómo consultar solo lo nuevo en la próxima corrida';
