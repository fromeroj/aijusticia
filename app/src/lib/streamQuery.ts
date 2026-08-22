/**
 * Cliente SSE para el endpoint /query/stream de FastAPI.
 *
 * No usa EventSource (que es GET-only). Usa fetch + ReadableStream para poder
 * enviar un POST con body JSON — necesario para la consulta del usuario.
 *
 * Eventos que emite el generator:
 *   { type: "stage",   data: { stage, label } }
 *   { type: "token",   data: "texto parcial" }
 *   { type: "done",    data: { respuesta, citas, pasajes, traza_id, ... } }
 *   { type: "error",   data: { mensaje } }
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ClarifyQuestion {
  id: string;
  texto: string;
  tipo: "texto" | "opcion" | "numero";
  opciones?: string[];
}

export interface Expediente {
  materia: string | null;
  jurisdiccion: string | null;
  hechos: Record<string, string>;
  actores_caso: string[];
  rondas_pre_rag: number;
  rondas_post_rag: number;
  suficiente: boolean;
}

export interface ClarifyPayload {
  materia: string | null;
  ronda?: number;
  rondas_max?: number;
  fase?: "pre_rag" | "post_rag";
  expediente?: Expediente;
  questions: ClarifyQuestion[];
}

export type SSEEvent =
  | { type: "stage"; data: { stage: string; label: string } }
  | { type: "token"; data: string }
  | { type: "clarify"; data: ClarifyPayload }
  | { type: "done"; data: DonePayload }
  | { type: "error"; data: { mensaje: string } };

export interface DonePayload {
  respuesta: string;
  abstenido: boolean;
  tipo_abstencion: string | null;
  job_id: number | null;
  traza_id: number | null;
  expediente?: Expediente;
  n_oraciones: number;
  n_sustentadas: number;
  pasajes: Array<{
    titulo: string;
    fuente: string;
    clave_cita: string;
    vinculante: boolean;
    fragmento: string;
    jerarquia: number;
  }>;
  citas: Array<{
    texto: string;
    sustentado: boolean;
    nli: string | null;
  }>;
}

export interface TurnoHistorial {
  role: "user" | "assistant";
  text: string;
}

export async function* streamQuery(
  consulta: string,
  nivel: string = "Nivel0",
  signal?: AbortSignal,
  respuestasAclaratorias?: Record<string, string>,
  historial?: TurnoHistorial[],
  respuestasAcumuladas?: Record<string, string>,
  expedientePrev?: Expediente | null,
): AsyncGenerator<SSEEvent> {
  const res = await fetch(`${API_URL}/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      consulta,
      nivel,
      respuestas_aclaratorias: respuestasAclaratorias || null,
      respuestas_acumuladas: respuestasAcumuladas && Object.keys(respuestasAcumuladas).length > 0 ? respuestasAcumuladas : null,
      expediente_prev: expedientePrev || null,
      historial: historial && historial.length > 0 ? historial : null,
    }),
    signal,
  });

  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }

  const reader = res.body!.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += value;
    // Los eventos SSE terminan con \n\n
    const events = buffer.split("\n\n");
    buffer = events.pop() || ""; // el último puede estar incompleto

    for (const rawEvent of events) {
      const parsed = parseSSEEvent(rawEvent);
      if (parsed) yield parsed;
    }
  }

  // Procesar cualquier evento restante en el buffer
  if (buffer.trim()) {
    const parsed = parseSSEEvent(buffer);
    if (parsed) yield parsed;
  }
}

function parseSSEEvent(raw: string): SSEEvent | null {
  const lines = raw.split("\n");
  let event = "message";
  let data = "";

  for (const line of lines) {
    if (line.startsWith("event: ")) {
      event = line.slice(7).trim();
    } else if (line.startsWith("data: ")) {
      data += line.slice(6);
    }
  }

  if (!data) return null;

  try {
    if (event === "token") {
      return { type: "token", data };
    }
    const parsed = JSON.parse(data);
    return { type: event as SSEEvent["type"], data: parsed } as SSEEvent;
  } catch {
    return null;
  }
}
