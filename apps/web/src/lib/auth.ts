/**
 * Autenticación JWT del lado cliente (S3/A1).
 *
 * La sesión se persiste en localStorage bajo "aij_sesion" (la misma clave
 * del store de Zustand — son la misma estructura). Los tokens NUNCA van en
 * URLs; la frase nunca se guarda.
 *
 * - canjearTokens(via, credential): POST /auth/token → sesión con tokens
 * - getAccessToken(): access vigente, con refresh rotatorio transparente
 * - authFetch(): fetch con Authorization + auto-refresh + 1 reintento
 */

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Tokens {
  access: string;
  refresh: string;
}

interface SesionPersistida {
  tipo: "ciudadano" | "abogado";
  actorId: string;
  dossierId?: string;
  bufeteId?: string | null;
  creadoEn: number;
  tokens?: Tokens;
}

const SESION_KEY = "aij_sesion";

function leerSesion(): SesionPersistida | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(SESION_KEY);
    return raw ? (JSON.parse(raw) as SesionPersistida) : null;
  } catch {
    return null;
  }
}

function escribirSesion(s: SesionPersistida | null) {
  if (typeof window === "undefined") return;
  try {
    if (s) window.localStorage.setItem(SESION_KEY, JSON.stringify(s));
    else window.localStorage.removeItem(SESION_KEY);
  } catch {
    /* storage bloqueado */
  }
}

/** ¿El access token sigue vigente? (decode sin verificar — el engine verifica) */
function accessVigente(t: Tokens): boolean {
  try {
    const payload = JSON.parse(atob(t.access.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return (payload.exp ?? 0) > Date.now() / 1000 + 5;
  } catch {
    return false;
  }
}

/** Canjea una credencial (frase | dispositivo | id_token de Google) por el par JWT. */
export async function canjearTokens(
  via: "frase" | "dispositivo" | "google",
  credential: string,
): Promise<SesionPersistida | null> {
  const r = await fetch(`${API_URL}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ via, credential }),
  });
  if (!r.ok) return null;
  const d = await r.json();
  const sesion: SesionPersistida = {
    tipo: d.tipo === "abogado" ? "abogado" : "ciudadano",
    actorId: d.actor_id,
    dossierId: d.dossier_id ?? undefined,
    bufeteId: d.bufete_id ?? null,
    creadoEn: Date.now(),
    tokens: { access: d.access_token, refresh: d.refresh_token },
  };
  escribirSesion(sesion);
  return sesion;
}

/** Guarda tokens ya obtenidos (handoff de Google vía code de un solo uso). */
export function guardarSesionConTokens(d: {
  tipo: string; actor_id: string; dossier_id?: string | null;
  bufete_id?: string | null; access_token: string; refresh_token: string;
}): SesionPersistida {
  const sesion: SesionPersistida = {
    tipo: d.tipo === "abogado" ? "abogado" : "ciudadano",
    actorId: d.actor_id,
    dossierId: d.dossier_id ?? undefined,
    bufeteId: d.bufete_id ?? null,
    creadoEn: Date.now(),
    tokens: { access: d.access_token, refresh: d.refresh_token },
  };
  escribirSesion(sesion);
  return sesion;
}

/** Access token vigente; refresca (rotando) si expiró. null si no hay sesión.
 *
 * Single-flight: si varios fetches disparan refresh a la vez (chat + expediente
 * + documentos tras 15 min), comparten la MISMA promesa — el refresh token es
 * rotatorio y un segundo intento con el ya-rotado fallaría.
 */
let refreshEnVuelo: Promise<string | null> | null = null;

async function _refrescar(s: SesionPersistida): Promise<string | null> {
  const refresh = s.tokens?.refresh;
  if (!refresh) return null;
  const r = await fetch(`${API_URL}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ via: "refresh", credential: refresh }),
  });
  if (!r.ok) {
    escribirSesion(null); // refresh inválido → sesión muerta
    return null;
  }
  const d = await r.json();
  escribirSesion({
    ...s,
    dossierId: d.dossier_id ?? s.dossierId,
    tokens: { access: d.access_token, refresh: d.refresh_token },
  });
  return d.access_token;
}

export async function getAccessToken(): Promise<string | null> {
  const s = leerSesion();
  if (!s?.tokens) return null;
  if (accessVigente(s.tokens)) return s.tokens.access;
  if (!refreshEnVuelo) {
    refreshEnVuelo = _refrescar(s).finally(() => { refreshEnVuelo = null; });
  }
  return refreshEnVuelo;
}

export class SinSesionError extends Error {
  constructor() {
    super("Sesión expirada — entra de nuevo con tu frase");
  }
}

/** fetch con Authorization + auto-refresh (1 reintento). */
export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = await getAccessToken();
  if (!token) throw new SinSesionError();
  const r = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { ...init.headers, Authorization: `Bearer ${token}` },
  });
  if (r.status === 401) {
    // forzar refresh aunque el access pareciera vigente (revocado, clock skew)
    const s = leerSesion();
    const tokensActuales = s?.tokens;
    if (tokensActuales) {
      try {
        const access = await getAccessToken(); // single-flight (refresh rotatorio)
        if (access && access !== token) {
          return fetch(`${API_URL}${path}`, {
            ...init,
            headers: { ...init.headers, Authorization: `Bearer ${access}` },
          });
        }
      } catch { /* sin sesión */ }
      escribirSesion(null);
    }
    throw new SinSesionError();
  }
  return r;
}

/** Registra el token de dispositivo con prueba de posesión (frase o JWT activo). */
export async function registrarDispositivo(
  actorId: string,
  deviceToken: string,
  frase?: string,
): Promise<boolean> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const access = await getAccessToken().catch(() => null);
  if (access) headers.Authorization = `Bearer ${access}`;
  const r = await fetch(`${API_URL}/auth/dispositivo/registrar`, {
    method: "POST",
    headers,
    body: JSON.stringify({ actor_id: actorId, token: deviceToken, frase: frase ?? null }),
  });
  return r.ok;
}
