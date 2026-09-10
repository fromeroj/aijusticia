import { NextRequest, NextResponse } from "next/server";

/**
 * Canjea el code de un solo uso del callback de Google por la sesión con
 * tokens. El code vive 60s en memoria del servidor y se borra al usarse —
 * los tokens nunca aparecen en URLs ni historial.
 */
const pendientes: Map<string, Record<string, unknown>> =
  (globalThis as { __aij_google_handoff?: Map<string, Record<string, unknown>> })
    .__aij_google_handoff ?? new Map();
(globalThis as { __aij_google_handoff?: Map<string, Record<string, unknown>> })
  .__aij_google_handoff = pendientes;

export async function GET(req: NextRequest) {
  const code = req.nextUrl.searchParams.get("code");
  if (!code || !pendientes.has(code)) {
    return NextResponse.json({ error: "code inválido o expirado" }, { status: 410 });
  }
  const sesion = pendientes.get(code)!;
  pendientes.delete(code); // un solo uso
  return NextResponse.json(sesion);
}
