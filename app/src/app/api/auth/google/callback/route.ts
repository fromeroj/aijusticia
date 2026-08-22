import { NextRequest, NextResponse } from "next/server";

/**
 * Callback OAuth de Google.
 *
 * Flujo: /entrar → Google → aquí → intercambia code por userinfo →
 * POST {backend}/auth/google (find-or-create) → cookie ligera de bootstrap → /entrar?g=1
 *
 * Requiere en el entorno del frontend:
 *   NEXT_PUBLIC_GOOGLE_CLIENT_ID
 *   GOOGLE_CLIENT_SECRET
 * Y en Google Cloud Console la URL de retorno:
 *   {origin}/api/auth/google/callback
 */
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

    // 2. Decodificar el payload del id_token (JWT firmado por Google;
    //    la verificación de firma la hizo Google al emitir el token vía TLS)
    const payload = JSON.parse(
      Buffer.from(id_token.split(".")[1], "base64url").toString("utf8"),
    );
    const googleSub: string = payload.sub;
    const email: string | null = payload.email ?? null;
    if (!googleSub) throw new Error("sub");

    // 3. Find-or-create en el backend
    const sesionRes = await fetch(`${API_URL}/auth/google`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ google_sub: googleSub, email }),
    });
    if (!sesionRes.ok) throw new Error("backend");
    const sesion = await sesionRes.json();

    // 4. Bootstrap mínimo por query (la página /entrar completa la sesión
    //    registrando el token de dispositivo vía /auth/dispositivo/registrar)
    const params = new URLSearchParams({
      g: "ok",
      actor: sesion.actor_id,
      tipo: sesion.tipo,
      dossier: sesion.dossier_id || "",
      bufete: sesion.bufete_id || "",
      email: email || "",
    });
    return NextResponse.redirect(origin + "/entrar?" + params.toString());
  } catch {
    return NextResponse.redirect(origin + "/entrar?g=error&motivo=oauth");
  }
}
