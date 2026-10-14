import { NextRequest, NextResponse } from "next/server";

/**
 * Callback OAuth de Google.
 *
 * Flujo: /entrar → Google → aquí → intercambia code por id_token →
 * POST {backend}/auth/token via=google (el ENGINE valida firma/audiencia
 * del id_token contra Google — A4) → tokens guardados tras un code de un
 * solo uso (60s) que /entrar canjea — nunca viajan por la URL.
 *
 * Requiere en el entorno del frontend:
 *   NEXT_PUBLIC_GOOGLE_CLIENT_ID
 *   GOOGLE_CLIENT_SECRET
 * Y en Google Cloud Console la URL de retorno:
 *   {origin}/api/auth/google/callback
 */
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Handoff de un solo uso: code → sesión con tokens. Registro en globalThis
// para compartirlo con /api/auth/google/handoff (módulos distintos).
const pendientes: Map<string, Record<string, unknown>> =
  (globalThis as { __aij_google_handoff?: Map<string, Record<string, unknown>> })
    .__aij_google_handoff ?? new Map();
(globalThis as { __aij_google_handoff?: Map<string, Record<string, unknown>> })
  .__aij_google_handoff = pendientes;

export async function GET(req: NextRequest) {
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
  const clientSecret = process.env.GOOGLE_CLIENT_SECRET;
  const origin = req.nextUrl.origin;

  if (!clientId || !clientSecret) {
    return NextResponse.redirect(origin + "/entrar?g=error&motivo=config");
  }

  const code = req.nextUrl.searchParams.get("code");
  if (!code) {
    return NextResponse.redirect(origin + "/entrar?g=error&motivo=cancelado");
  }

  try {
    // 1. Intercambiar code por tokens
    const tokenRes = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        code,
        client_id: clientId,
        client_secret: clientSecret,
        redirect_uri: `${origin}/api/auth/google/callback`,
        grant_type: "authorization_code",
      }),
    });
    if (!tokenRes.ok) throw new Error("token");
    const { id_token } = await tokenRes.json();
    if (!id_token) throw new Error("id_token");

    // 2. El engine valida el id_token (firma/audiencia vía Google) y emite
    //    nuestro par JWT — ya NO confiamos en un sub enviado sin verificar.
    const sesionRes = await fetch(`${API_URL}/auth/token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ via: "google", credential: id_token }),
    });
    if (!sesionRes.ok) throw new Error("backend");
    const sesion = await sesionRes.json();

    // 3. Code de un solo uso para el handoff a /entrar (localStorage es del
    //    navegador; los tokens jamás van en la URL/history)
    const handoff = crypto.randomUUID();
    pendientes.set(handoff, sesion);
    setTimeout(() => pendientes.delete(handoff), 60_000);

    return NextResponse.redirect(origin + `/entrar?g=ok&code=${handoff}`);
  } catch {
    return NextResponse.redirect(origin + "/entrar?g=error&motivo=oauth");
  }
}
