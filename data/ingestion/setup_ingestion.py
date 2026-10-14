"""Crea las tablas del subsistema de adquisición de datos y siembra source_health
con todas las fuentes (32 estados + federales + tratados).

Uso:
    python scripts/setup_ingestion.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg
from ai_justicia.config import settings

SCHEMA_SQL = """
-- ============================================================
-- source_health: estado de cada fuente (una fila por fuente)
-- ============================================================
CREATE TABLE IF NOT EXISTS source_health (
    fuente                  TEXT NOT NULL,
    entidad                 TEXT NOT NULL DEFAULT 'Federal',
    tipo                    TEXT NOT NULL,
    adapter_class           TEXT NOT NULL,
    enabled                 BOOLEAN NOT NULL DEFAULT TRUE,
    cron_expr               TEXT NOT NULL DEFAULT '0 6 * * *',
    expected_min_results    INT NOT NULL DEFAULT 1,
    last_run_at             TIMESTAMPTZ,
    last_success_at         TIMESTAMPTZ,
    consecutive_failures    INT NOT NULL DEFAULT 0,
    consecutive_empty       INT NOT NULL DEFAULT 0,
    health_status           TEXT NOT NULL DEFAULT 'unknown',
    watermark               DATE,
    total_documentos        INT NOT NULL DEFAULT 0,
    listing_page_hash       TEXT,
    rolling_avg_results     REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (fuente, entidad)
);

-- ============================================================
-- ingestion_runs: historial de cada ejecución
-- ============================================================
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id                      BIGSERIAL PRIMARY KEY,
    fuente                  TEXT NOT NULL,
    entidad                 TEXT,
    started_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at            TIMESTAMPTZ,
    duration_ms             INT,
    trigger                 TEXT NOT NULL DEFAULT 'scheduled',
    status                  TEXT NOT NULL,
    documentos_fetched      INT NOT NULL DEFAULT 0,
    documentos_new          INT NOT NULL DEFAULT 0,
    documentos_updated      INT NOT NULL DEFAULT 0,
    documentos_errored      INT NOT NULL DEFAULT 0,
    http_status_codes       INT[] NOT NULL DEFAULT '{}',
    listing_page_hash       TEXT,
    hash_changed            BOOLEAN NOT NULL DEFAULT FALSE,
    error_message           TEXT,
    error_count             INT NOT NULL DEFAULT 0,
    watermark_before        DATE,
    watermark_after         DATE,
    chunks_indexed          INT
);

CREATE INDEX IF NOT EXISTS idx_runs_fuente_started ON ingestion_runs (fuente, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status ON ingestion_runs (status, started_at DESC);
"""

# Semilla: todas las fuentes del sistema
# (fuente, entidad, tipo, adapter_class, cron_expr, expected_min_results)
SEED_SOURCES = [
    # === Federales ===
    ("SJF", "Federal", "jurisprudencia", "sjf", "0 6 * * *", 10),
    ("DOF", "Federal", "publicacion", "dof", "0 6 * * *", 5),
    ("LeyesBiblio", "Federal", "ley", "leyes_biblio", "0 7 * * 1", 1),
    ("TratadosSCJN", "Federal", "tratado", "tratados_scjn", "0 7 * * 1", 1),

    # === 32 estados (los 4 ya hechos = enabled; el resto = disabled hasta tener adapter) ===
    ("GacetaEstatal", "Ciudad de México", "ley", "cdmx", "0 7 * * 1", 1),
    ("GacetaEstatal", "Estado de México", "ley", "edomex", "0 7 * * 1", 1),
    ("GacetaEstatal", "Nuevo León", "ley", "nuevo_leon", "0 7 * * 1", 1),
    ("GacetaEstatal", "Jalisco", "ley", "jalisco", "0 7 * * 1", 1),

    # Los 28 restantes: disabled hasta crear sus adapters
    ("GacetaEstatal", "Aguascalientes", "ley", "aguascalientes", "0 7 * * 1", 1),
    ("GacetaEstatal", "Baja California", "ley", "baja_california", "0 7 * * 1", 1),
    ("GacetaEstatal", "Baja California Sur", "ley", "baja_california_sur", "0 7 * * 1", 1),
    ("GacetaEstatal", "Campeche", "ley", "campeche", "0 7 * * 1", 1),
    ("GacetaEstatal", "Coahuila", "ley", "coahuila", "0 7 * * 1", 1),
    ("GacetaEstatal", "Colima", "ley", "colima", "0 7 * * 1", 1),
    ("GacetaEstatal", "Chiapas", "ley", "chiapas", "0 7 * * 1", 1),
    ("GacetaEstatal", "Chihuahua", "ley", "chihuahua", "0 7 * * 1", 1),
    ("GacetaEstatal", "Durango", "ley", "durango", "0 7 * * 1", 1),
    ("GacetaEstatal", "Guanajuato", "ley", "guanajuato", "0 7 * * 1", 1),
    ("GacetaEstatal", "Guerrero", "ley", "guerrero", "0 7 * * 1", 1),
    ("GacetaEstatal", "Hidalgo", "ley", "hidalgo", "0 7 * * 1", 1),
    ("GacetaEstatal", "Michoacán", "ley", "michoacan", "0 7 * * 1", 1),
    ("GacetaEstatal", "Morelos", "ley", "morelos", "0 7 * * 1", 1),
    ("GacetaEstatal", "Nayarit", "ley", "nayarit", "0 7 * * 1", 1),
    ("GacetaEstatal", "Oaxaca", "ley", "oaxaca", "0 7 * * 1", 1),
    ("GacetaEstatal", "Puebla", "ley", "puebla", "0 7 * * 1", 1),
    ("GacetaEstatal", "Querétaro", "ley", "queretaro", "0 7 * * 1", 1),
    ("GacetaEstatal", "Quintana Roo", "ley", "quintana_roo", "0 7 * * 1", 1),
    ("GacetaEstatal", "San Luis Potosí", "ley", "san_luis_potosi", "0 7 * * 1", 1),
    ("GacetaEstatal", "Sinaloa", "ley", "sinaloa", "0 7 * * 1", 1),
    ("GacetaEstatal", "Sonora", "ley", "sonora", "0 7 * * 1", 1),
    ("GacetaEstatal", "Tabasco", "ley", "tabasco", "0 7 * * 1", 1),
    ("GacetaEstatal", "Tamaulipas", "ley", "tamaulipas", "0 7 * * 1", 1),
    ("GacetaEstatal", "Tlaxcala", "ley", "tlaxcala", "0 7 * * 1", 1),
    ("GacetaEstatal", "Veracruz", "ley", "veracruz", "0 7 * * 1", 1),
    ("GacetaEstatal", "Yucatán", "ley", "yucatan", "0 7 * * 1", 1),
    ("GacetaEstatal", "Zacatecas", "ley", "zacatecas", "0 7 * * 1", 1),
]

SEED_SQL = """
INSERT INTO source_health (fuente, entidad, tipo, adapter_class, cron_expr, expected_min_results, enabled)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (fuente, entidad) DO UPDATE SET
    tipo = EXCLUDED.tipo,
    adapter_class = EXCLUDED.adapter_class,
    cron_expr = EXCLUDED.cron_expr,
    expected_min_results = EXCLUDED.expected_min_results
"""


def setup():
    print("Creando tablas del subsistema de adquisición...")
    with psycopg.connect(settings.psycopg_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            print(f"✓ Tablas creadas: source_health, ingestion_runs")

            # Sembrar fuentes
            for fuente, entidad, tipo, adapter, cron, min_res in SEED_SOURCES:
                # Los 4 estados ya hechos + 3 federales = enabled
                enabled = (entidad == "Federal" and adapter in ("sjf", "dof", "leyes_biblio")) or entidad in ("Ciudad de México", "Estado de México", "Nuevo León", "Jalisco")
                cur.execute(SEED_SQL, (fuente, entidad, tipo, adapter, cron, min_res, enabled))

            cur.execute("SELECT COUNT(*) FROM source_health")
            total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM source_health WHERE enabled = TRUE")
            enabled_count = cur.fetchone()[0]
            print(f"✓ Fuentes sembradas: {total} total ({enabled_count} habilitadas)")

            # Mostrar resumen
            cur.execute("SELECT fuente, entidad, enabled, health_status FROM source_health ORDER BY fuente, entidad")
            print("\n=== Fuente | Entidad | Enabled | Status ===")
            for f, e, en, hs in cur.fetchall():
                flag = "✅" if en else "⬜"
                print(f"  {flag} {f:<15} {e or 'Federal':<20} {hs}")


if __name__ == "__main__":
    setup()
