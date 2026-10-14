/**
 * Cliente SSE para POST /chat/stream — arquitectura de 2 agentes.
 *
 * Izel responde en streaming (token) mientras el Bibliotecario busca leyes
 * en paralelo (laws). El done incluye los pasajes verificados para la
 * tarjeta de referencias.
 *
 *   { type: "token", data: "texto parcial" }
 *   { type: "laws",  data: { ley, institucion, resumen, pasajes: [...] } }
 *   { type: "done",  data: { respuesta, pasajes, ley, institucion, ... } }
 *   { type: "error", data: { mensaje } }
 */
import { getAccessToken, API_URL } from "./auth";

export interface LeyesPrevias {
  titulo: string;
  fuente: string;
  clave_cita: string;
  vinculante: boolean;
  fragmento: string;
  jerarquia: number;
}

export interface TriagePrevio {
  ley?: string;
  institucion?: string;
}

export type ChatStreamEvent =
  | { type: "token"; data: string }
  | { type: "reset"; data: unknown }
  | {
      type: "laws";
      data: {
        ley: string;
        institucion: string;
        resumen: string;
        pasajes: Array<{ fuente: string; titulo: string; texto: string }>;
      };
    }
  | { type: "done"; data: import("./streamQuery").DonePayload & { ley?: string; institucion?: string } }
  | { type: "error"; data: { mensaje: string } };

export async function* chatStream(
  consulta: string,
  opts: {
    nivel?: string;
    dossierId?: string | null;
    historial?: Array<{ role: "user" | "assistant"; text: string }>;
    leyesPrevias?: LeyesPrevias[] | null;
    triagePrevio?: TriagePrevio | null;
    signal?: AbortSignal;
  } = {},
): AsyncGenerator<ChatStreamEvent> {
  const token = await getAccessToken().catch(() => null);
  const res = await fetch(`${API_URL}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      consulta,
      nivel: opts.nivel || "Nivel0",
      dossier_id: opts.dossierId || null,
      historial:
        opts.historial && opts.historial.length > 0
          ? opts.historial.map((h) => ({ rol: h.role, texto: h.text }))
          : null,
      leyes_previas: opts.leyesPrevias && opts.leyesPrevias.length > 0 ? opts.leyesPrevias : null,
      triage_previo: opts.triagePrevio || null,
    }),
    signal: opts.signal,
  });

  if (!res.ok || !res.body) {
    throw new Error(`HTTP ${res.status}`);
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += value;
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";

    for (const rawEvent of events) {
      const parsed = parseEvent(rawEvent);
      if (parsed) yield parsed;
    }
  }

  if (buffer.trim()) {
    const parsed = parseEvent(buffer);
    if (parsed) yield parsed;
  }
}

function parseEvent(raw: string): ChatStreamEvent | null {
  let event = "message";
  let data = "";

  for (const line of raw.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice(7).trim();
    else if (line.startsWith("data: ")) data += line.slice(6);
  }
  if (!data) return null;

  try {
    const parsed = JSON.parse(data);
    return { type: event as ChatStreamEvent["type"], data: parsed } as ChatStreamEvent;
  } catch {
    if (event === "token") return { type: "token", data };
    return null;
  }
}
