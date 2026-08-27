/**
 * Store global del chat (Zustand).
 *
 * Mantiene: mensajes de la sesión actual, estado del streaming, etapa actual.
 * No incluye historial persistente (eso vendrá con auth + DB).
 */

import { create } from "zustand";
import type { DonePayload, ClarifyPayload, ClarifyQuestion, Expediente } from "./streamQuery";

export interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  done?: DonePayload | null;
  isStreaming?: boolean;
  error?: string;
  // Para burbujas de aclaración
  clarify?: ClarifyPayload | null;
  // Tarjeta ya respondida (multi-ronda: las viejas quedan solo-lectura)
  respondido?: boolean;
  // Para burbujas de análisis (burbuja 1)
  analysisInfo?: { materia: string | null; stageTimings?: Record<string, number> } | null;
}

export type StageId = "analisis" | "clarificacion" | "recuperacion" | "generacion" | "verificacion";

interface ChatState {
  messages: Message[];
  currentStage: StageId | null;
  currentStageLabel: string | null;
  isQuerying: boolean;
  abortController: AbortController | null;
  stageTimings: Record<string, number>;
  pendingClarify: ClarifyPayload | null;
  lastConsulta: string | null;
  // Ciclo de entrevista multi-ronda
  expedienteAcumulado: Expediente | null;
  respuestasAcumuladas: Record<string, string>;
  // Modo de uso: ciudadano (entrevista) vs abogado (directo)
  modo: "ciudadano" | "abogado";

  sendMessage: (text: string) => void;
  appendToken: (token: string) => void;
  setStage: (stage: StageId, label: string) => void;
  setAnalysisInfo: (materia: string | null) => void;
  finishMessage: (done: DonePayload) => void;
  addReferencesMessage: (done: DonePayload) => void;
  addAbstencionMessage: (done: DonePayload) => void;
  addClarifyMessage: (clarify: ClarifyPayload) => void;
  errorMessage: (msg: string) => void;
  stopQuery: () => void;
  setModo: (modo: "ciudadano" | "abogado") => void;
  resetExpediente: () => void;
  clearChat: () => void;
  // Sesión persistida (landing → onboarding → chat). null = modo abierto (anónimo)
  sesion: Sesion | null;
  iniciarSesion: (s: Sesion) => void;
  cerrarSesion: () => void;
  // Modo abierto → caso: conserva mensajes y expediente, vincula sesión
  convertirACaso: (s: Sesion) => void;
  // Nuevo caso: limpia expediente y mensajes, conserva la sesión
  nuevoCaso: () => void;
}

export interface Sesion {
  tipo: "ciudadano" | "abogado";
  actorId: string;
  dossierId?: string;        // ciudadanos: su caso activo
  bufeteId?: string | null;  // abogados: su despacho
  creadoEn: number;
}

// Persistencia ligera de sesión (sin auth aún). La frase NUNCA se guarda
// aquí — solo vive en el dispositivo del usuario, mostrada una vez.
const SESION_KEY = "aij_sesion";

function leerSesion(): Sesion | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(SESION_KEY);
    return raw ? (JSON.parse(raw) as Sesion) : null;
  } catch {
    return null;
  }
}

function guardarSesion(s: Sesion | null) {
  if (typeof window === "undefined") return;
  try {
    if (s) window.localStorage.setItem(SESION_KEY, JSON.stringify(s));
    else window.localStorage.removeItem(SESION_KEY);
  } catch {
    /* storage lleno/bloqueado — sesión en memoria */
  }
}

// Hidratar modo desde la sesión persistida al cargar el store
const sesionInicial = typeof window !== "undefined" ? leerSesion() : null;

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  currentStage: null,
  currentStageLabel: null,
  isQuerying: false,
  abortController: null,
  stageTimings: {},
  pendingClarify: null,
  lastConsulta: null,
  expedienteAcumulado: null,
  respuestasAcumuladas: {},
  modo: sesionInicial?.tipo ?? "ciudadano",
  sesion: sesionInicial,

  iniciarSesion: (s) => {
    guardarSesion(s);
    set({ sesion: s, modo: s.tipo, expedienteAcumulado: null, respuestasAcumuladas: {} });
  },

  cerrarSesion: () => {
    guardarSesion(null);
    set({
      sesion: null, modo: "ciudadano", messages: [], currentStage: null,
      isQuerying: false, expedienteAcumulado: null, respuestasAcumuladas: {},
    });
  },

  convertirACaso: (s) => {
    // Conserva mensajes y expediente acumulados del modo abierto;
    // solo vincula la sesión nueva.
    guardarSesion(s);
    set({ sesion: s, modo: s.tipo });
  },

  nuevoCaso: () => {
    set({
      messages: [], currentStage: null, currentStageLabel: null,
      pendingClarify: null, lastConsulta: null,
      expedienteAcumulado: null, respuestasAcumuladas: {},
      stageTimings: {},
    });
  },

  sendMessage: (text: string) => {
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      text,
    };
    // Burbuja 1: AnalysisCard (persistente — siempre visible con las etapas)
    const analysisMsg: Message = {
      id: crypto.randomUUID(),
      role: "assistant",
      text: "",
      isStreaming: true,
      analysisInfo: { materia: null },
    };
    // Burbuja 3: Respuesta (empieza vacía, se llena con tokens)
    const responseMsg: Message = {
      id: crypto.randomUUID(),
      role: "assistant",
      text: "",
      isStreaming: true,
    };
    set((state) => ({
      messages: [...state.messages, userMsg, analysisMsg, responseMsg],
      isQuerying: true,
      currentStage: null,
      currentStageLabel: null,
      lastConsulta: text,
      stageTimings: {},
    }));
  },

  appendToken: (token: string) => {
    set((state) => {
      const messages = [...state.messages];
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant") {
        let newText = last.text + token;
        // Fix de espaciado del streaming: puntuación pegada a la palabra siguiente
        // ej: "retención.Guarda" → "retención. Guarda"
        newText = newText.replace(/\.([A-ZÁÉÍÓÚÑ])/g, ". $1");
        newText = newText.replace(/\?([A-ZÁÉÍÓÚÑ¿])/g, "? $1");
        // Citas: corchete cerrado pegado a palabra → espacio
        // ej: "menor[2]El" → "menor[2] El" ; "[2].tu ex" ya cubierto arriba si mayúscula
        newText = newText.replace(/\]([A-ZÁÉÍÓÚÑa-záéíóúñ])/g, "] $1");
        messages[messages.length - 1] = { ...last, text: newText };
      }
      return { messages };
    });
  },

  setStage: (stage, label) => {
    // Actualizar también la burbuja de análisis (segunda desde el final)
    set((state) => {
      const messages = [...state.messages];
      // La burbuja de análisis es la que tiene analysisInfo
      for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].analysisInfo) {
          messages[i] = { ...messages[i], isStreaming: true };
          break;
        }
      }
      return { messages, currentStage: stage, currentStageLabel: label };
    });
  },

  setAnalysisInfo: (materia: string | null) => {
    set((state) => {
      const messages = [...state.messages];
      for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].analysisInfo) {
          messages[i] = {
            ...messages[i],
            analysisInfo: { materia, stageTimings: {} },
          };
          break;
        }
      }
      return { messages };
    });
  },

  addClarifyMessage: (clarify: ClarifyPayload) => {
    set((state) => {
      const messages = [...state.messages];
      // Encontrar la burbuja de análisis y marcarla como no-streaming temporalmente
      for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].analysisInfo) {
          messages[i] = { ...messages[i], isStreaming: false };
          break;
        }
      }
      // Marcar TODAS las tarjetas de clarify anteriores como respondidas
      // (multi-ronda: solo la tarjeta nueva queda interactiva)
      for (let i = 0; i < messages.length; i++) {
        if (messages[i].clarify) {
          messages[i] = { ...messages[i], respondido: true };
        }
      }
      // Insertar la burbuja de clarify ANTES de la burbuja de respuesta vacía
      const clarifyMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        text: "",
        clarify,
        isStreaming: false,
      };
      // Encontrar la burbuja de respuesta (última, sin analysisInfo ni clarify)
      const lastIndex = messages.length - 1;
      const newMessages = [...messages.slice(0, lastIndex), clarifyMsg, ...messages.slice(lastIndex)];
      return {
        messages: newMessages,
        isQuerying: false,
        pendingClarify: clarify,
        currentStage: "clarificacion" as StageId,
      };
    });
  },

  finishMessage: (done: DonePayload) => {
    set((state) => {
      const messages = [...state.messages];
      // Marcar la burbuja de análisis como completada
      for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].analysisInfo) {
          messages[i] = { ...messages[i], isStreaming: false };
          break;
        }
      }
      // Marcar la burbuja de respuesta como completada
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant") {
        messages[messages.length - 1] = {
          ...last,
          text: last.text,
          done,
          isStreaming: false,
        };
      }
      return {
        messages,
        isQuerying: false,
        currentStage: null,
      };
    });
  },

  addReferencesMessage: (done: DonePayload) => {
    set((state) => {
      // Añadir una segunda burbuja compacta con las referencias legales verificadas
      const refMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        text: "", // sin texto principal — se renderiza como card de referencias
        done,
        isStreaming: false,
      };
      return { messages: [...state.messages, refMsg] };
    });
  },

  addAbstencionMessage: (done: DonePayload) => {
    set((state) => {
      // Burbuja de advertencia: NO sobreescribe la respuesta anterior.
      // done.respuesta contiene el mensaje de abstención del backend.
      const abstMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        text: done.respuesta, // el mensaje de abstención/deferido
        done,
        isStreaming: false,
      };
      return { messages: [...state.messages, abstMsg] };
    });
  },

  errorMessage: (msg: string) => {
    set((state) => {
      const messages = [...state.messages];
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant") {
        messages[messages.length - 1] = {
          ...last,
          text: `⚠️ ${msg}`,
          isStreaming: false,
          error: msg,
        };
      }
      return { messages, isQuerying: false, currentStage: null };
    });
  },

  stopQuery: () => {
    const { abortController } = get();
    if (abortController) {
      abortController.abort();
    }
    set((state) => {
      const messages = [...state.messages];
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant" && last.isStreaming) {
        messages[messages.length - 1] = {
          ...last,
          isStreaming: false,
          text: last.text + "\n\n(interrumpido)",
        };
      }
      return { messages, isQuerying: false, currentStage: null, abortController: null };
    });
  },

  setModo: (modo) => {
    // Cambiar de modo reinicia el ciclo de entrevista del caso
    set({ modo, expedienteAcumulado: null, respuestasAcumuladas: {} });
  },

  resetExpediente: () => {
    set({ expedienteAcumulado: null, respuestasAcumuladas: {} });
  },

  clearChat: () => {
    set({
      messages: [],
      currentStage: null,
      isQuerying: false,
      expedienteAcumulado: null,
      respuestasAcumuladas: {},
    });
  },
}));
