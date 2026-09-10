/**
 * Invitaciones de acceso al caso (F4b — modelo A+C).
 * Código corto (10 chars) + QR/WhatsApp que el ciudadano pasa a SU abogado;
 * el abogado canjea; el ciudadano acepta con un click.
 */
import { authFetch, API_URL } from "./auth";

export interface InvitacionCreada {
  id: string;
  codigo: string;          // se muestra UNA vez
  url: string;             // aijusticia.mx/reclamar?c=CODIGO
  expira_en: string;
  ttl_horas: number;
}

export interface InvitacionViva {
  id: string;
  estado: "activa" | "solicitada";
  creado_en: string;
  expira_en: string;
}

export interface SolicitudPendiente {
  id: string;
  solicitada_en: string;
  verificado: boolean;
  especialidades: string[] | null;
  firma: string | null;          // si canjea una firma, su nombre
  etiqueta: string | null;       // "Berto — comprador" (invitaciones a persona)
  para_bufete: boolean;
  bufete_solicitante: string | null;
  relacion: string | null;
}

export interface OpcionesInvitacion {
  relacion: "asesor" | "parte";
  para_bufete: boolean;
  rol: "lectura" | "edicion";
}

export async function crearInvitacion(
  dossierId: string, opts?: OpcionesInvitacion,
): Promise<InvitacionCreada | null> {
  const r = await authFetch(`/dossiers/${dossierId}/invitaciones`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(opts ?? { relacion: "asesor", para_bufete: false, rol: "lectura" }),
  });
  if (!r.ok) return null;
  return r.json();
}

export async function estadoInvitaciones(dossierId: string): Promise<{
  invitaciones: InvitacionViva[]; solicitudes: SolicitudPendiente[];
} | null> {
  const r = await authFetch(`/dossiers/${dossierId}/invitaciones`);
  if (!r.ok) return null;
  return r.json();
}

export async function revocarInvitacion(dossierId: string, invId: string): Promise<boolean> {
  const r = await authFetch(`/dossiers/${dossierId}/invitaciones/${invId}`, { method: "DELETE" });
  return r.ok;
}

export async function canjearInvitacion(
  codigo: string, token: string, etiqueta?: string,
): Promise<{ ok: boolean; error?: string }> {
  const r = await fetch(`${API_URL}/invitaciones/canjear`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ codigo, etiqueta: etiqueta ?? null }),
  });
  const d = await r.json().catch(() => ({}));
  return r.ok ? { ok: true } : { ok: false, error: d.detail || "Código no válido" };
}

export async function salirDelCaso(dossierId: string): Promise<boolean> {
  const r = await authFetch(`/dossiers/${dossierId}/salir`, { method: "POST" });
  return r.ok;
}

export async function aceptarSolicitud(dossierId: string, invId: string): Promise<boolean> {
  const r = await authFetch(`/invitaciones/${invId}/aceptar`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dossier_id: dossierId }),
  });
  return r.ok;
}

export async function rechazarSolicitud(dossierId: string, invId: string): Promise<boolean> {
  const r = await authFetch(`/invitaciones/${invId}/rechazar`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dossier_id: dossierId }),
  });
  return r.ok;
}

/** QR del URL de reclamo como dataURL (lib qrcode, import dinámico). */
export async function qrDataUrl(texto: string, tamaño = 180): Promise<string | null> {
  try {
    const QR = (await import("qrcode")).default;
    return await QR.toDataURL(texto, {
      width: tamaño, margin: 1,
      color: { dark: "#047857", light: "#ffffff" },
    });
  } catch {
    return null;
  }
}

/** Link de WhatsApp con el mensaje de invitación. */
export function linkWhatsApp(url: string): string {
  const msg = encodeURIComponent(
    `Te comparto el acceso a mi caso en AI Justicia. Entra aquí para aceptarlo: ${url}`);
  return `https://wa.me/?text=${msg}`;
}
