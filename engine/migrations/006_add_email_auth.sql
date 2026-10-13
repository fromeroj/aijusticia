-- Migración: soporte de autenticación por correo
ALTER TABLE actores ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);
CREATE UNIQUE INDEX IF NOT EXISTS idx_actores_email ON actores(email) WHERE email IS NOT NULL AND email != '';
