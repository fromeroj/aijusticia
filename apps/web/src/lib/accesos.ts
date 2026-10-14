/**
 * Accesos del caso (grants M1) — el dossier SIEMPRE es del ciudadano;
 * el abogado accede por grant revocable. La creación de grants ocurre vía
 * invitaciones (lib/invitaciones.ts); aquí queda la gestión del dueño.
 */
import { authFetch } from "./auth";

export interface Acceso {
  id: number;
  actor_id: string | null;
  bufete_id: string | null;
  rol: "lectura" | "edicion";
  otorgado_por: string;
  creado_en: string;
  revocado_en: string | null;
  beneficiario: string | null;  // email del actor o nombre del bufete
}

export async function listarAccesos(dossierId: string): Promise<Acceso[]> {
  const r = await authFetch(`/dossiers/${dossierId}/accesos`);
  if (!r.ok) return [];
  const d = await r.json();
  return d.accesos ?? [];
}

export async function revocarAcceso(dossierId: string, accesoId: number): Promise<boolean> {
  const r = await authFetch(`/dossiers/${dossierId}/accesos/${accesoId}`, { method: "DELETE" });
  return r.ok;
}
