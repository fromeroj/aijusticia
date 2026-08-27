"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import Link from "next/link";
import { Scale, FolderPlus, ClipboardList } from "lucide-react";
import { useChatStore, type StageId } from "@/lib/store";
import { streamQuery, type TurnoHistorial } from "@/lib/streamQuery";
import { ConsentCard } from "./ConsentCard";
import { MessageBubble } from "./MessageBubble";
import { InputBar } from "./InputBar";
import { ConsentNotice } from "./ConsentNotice";
import { ConvertCaseModal } from "./ConvertCaseModal";
import { ExpedientePanel } from "./ExpedientePanel";

export function ChatWindow() {
  const messages = useChatStore((s) => s.messages);
  const currentStage = useChatStore((s) => s.currentStage);
  const isQuerying = useChatStore((s) => s.isQuerying);
  const lastConsulta = useChatStore((s) => s.lastConsulta);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const appendToken = useChatStore((s) => s.appendToken);
  const setStage = useChatStore((s) => s.setStage);
  const setAnalysisInfo = useChatStore((s) => s.setAnalysisInfo);
  const finishMessage = useChatStore((s) => s.finishMessage);
  const addReferencesMessage = useChatStore((s) => s.addReferencesMessage);
  const addAbstencionMessage = useChatStore((s) => s.addAbstencionMessage);
  const addClarifyMessage = useChatStore((s) => s.addClarifyMessage);
  const errorMessage = useChatStore((s) => s.errorMessage);
  const stopQuery = useChatStore((s) => s.stopQuery);

  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  /**
   * Deriva el historial de la conversación desde el store para enviarlo al backend.
   * Solo turnos completos (sin streaming), últimos 6, con texto truncado.
   * El backend lo usa para contextualizar preguntas de seguimiento.
   */
  const buildHistorial = useCallback((): TurnoHistorial[] => {
    const { messages: msgs } = useChatStore.getState();
    return msgs
      .filter((m) => m.role === "user" || (m.role === "assistant" && !m.isStreaming && m.done))
      .filter((m) => !m.clarify) // las tarjetas de clarificación no son turnos reales
      .slice(-6)
      .map((m) => ({
        role: m.role,
        text: (m.role === "assistant" ? m.text.slice(0, 300) : m.text),
      }));
  }, []);

  const runPipeline = useCallback(
    async (consulta: string, respuestasAclaratorias?: Record<string, string>) => {
      const abortController = new AbortController();
      const historial = buildHistorial();
      const { modo, expedienteAcumulado, respuestasAcumuladas } = useChatStore.getState();
      const nivel = modo === "abogado" ? "Nivel1" : "Nivel0";

      try {
        for await (const event of streamQuery(
          consulta, nivel, abortController.signal, respuestasAclaratorias, historial,
          respuestasAcumuladas, expedienteAcumulado,
        )) {
          switch (event.type) {
            case "stage":
              setStage(event.data.stage as StageId, event.data.label);
              break;
            case "clarify":
              setAnalysisInfo(event.data.materia);
              // El backend devuelve el expediente actualizado en cada clarify
              if (event.data.expediente) {
                useChatStore.setState({ expedienteAcumulado: event.data.expediente });
              }
              addClarifyMessage(event.data);
              break;
            case "token":
              appendToken(event.data);
              break;
            case "done":
              finishMessage(event.data);
              // Guardar expediente final del caso
              if (event.data.expediente) {
                useChatStore.setState({ expedienteAcumulado: event.data.expediente });
              }
              // Mostrar referencias SIEMPRE que haya una respuesta generada.
              // Solo mostrar abstención si NO se generó texto útil (la generación falló).
              if (event.data.abstenido && !event.data.respuesta) {
                addAbstencionMessage(event.data);
              } else {
                addReferencesMessage(event.data);
              }
              break;
            case "error":
              errorMessage(event.data.mensaje);
              break;
          }
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          // cancelado por el usuario
        } else {
          errorMessage(err instanceof Error ? err.message : "Error de conexión");
        }
      }
    },
    [sendMessage, appendToken, setStage, setAnalysisInfo, finishMessage, addReferencesMessage, addAbstencionMessage, addClarifyMessage, errorMessage, buildHistorial],
  );

  const handleSend = useCallback(
    (text: string) => {
      sendMessage(text);
      runPipeline(text);
    },
    [sendMessage, runPipeline],
  );

  const handleClarifySubmit = useCallback(
    (respuestas: Record<string, string>) => {
      // Multi-ronda: ACUMULAR respuestas de todas las rondas y re-enviar.
      // El backend fusiona respuestas_acumuladas al expediente y decide
      // si hace falta otra ronda o ya procede a responder.
      const respuestasFusionadas = {
        ...useChatStore.getState().respuestasAcumuladas,
        ...respuestas,
      };
      useChatStore.setState((state) => ({
        messages: [
          ...state.messages,
          {
            id: crypto.randomUUID(),
            role: "assistant" as const,
            text: "",
            isStreaming: true,
            analysisInfo: { materia: state.pendingClarify?.materia || null },
          },
        ],
        isQuerying: true,
        pendingClarify: null,
        currentStage: "recuperacion" as const,
        respuestasAcumuladas: respuestasFusionadas,
      }));
      if (lastConsulta) {
        runPipeline(lastConsulta, respuestas);
      }
    },
    [lastConsulta, runPipeline],
  );

  const isEmpty = messages.length === 0;
  const modo = useChatStore((s) => s.modo);
  const setModo = useChatStore((s) => s.setModo);
  const sesion = useChatStore((s) => s.sesion);
  const cerrarSesion = useChatStore((s) => s.cerrarSesion);
  const nuevoCaso = useChatStore((s) => s.nuevoCaso);
  const expedienteAcumulado = useChatStore((s) => s.expedienteAcumulado);
  const [consentDecidido, setConsentDecidido] = useState(false);
  const [convertOpen, setConvertOpen] = useState(false);
  const [expOpen, setExpOpen] = useState(false);
  const [confirmNuevo, setConfirmNuevo] = useState(false);

  const enModoAbierto = !sesion;

  const confirmarNuevoCaso = () => {
    if (messages.length > 4 && !confirmNuevo) {
      setConfirmNuevo(true);
      setTimeout(() => setConfirmNuevo(false), 4000);
      return;
    }
    nuevoCaso();
    setConfirmNuevo(false);
  };

  return (
    <div className="flex h-[100dvh] flex-col bg-white">
      {/* Header */}
      <header className="flex items-center gap-2 border-b border-gray-200 px-4 py-3">
        <Link href="/" className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#047857]">
          <Scale className="h-4 w-4 text-white" />
        </Link>
        <div>
          <h1 className="text-sm font-bold text-gray-900">AI Justicia</h1>
          <p className="text-[10px] text-gray-400">
            {modo === "abogado" ? "Modo profesional" : "Consulta ciudadana"}
          </p>
        </div>

        {/* Estado de sesión: modo abierto vs caso guardado */}
        {modo === "ciudadano" && enModoAbierto ? (
          <button
            onClick={() => setConvertOpen(true)}
            className="ml-3 flex items-center gap-1.5 rounded-full border border-[#047857]/30 bg-[#ecfdf5] px-3 py-1 text-[11px] font-medium text-[#047857] transition hover:bg-[#d1fae5]"
            title="Conserva esta conversación con una cuenta anónima"
          >
            <FolderPlus className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Guardar como caso</span>
            <span className="sm:hidden">Caso</span>
          </button>
        ) : modo === "ciudadano" && sesion?.dossierId ? (
          <span className="ml-3 hidden rounded-full bg-[#047857]/10 px-2.5 py-0.5 text-[10px] font-medium text-[#047857] sm:inline">
            Expediente {sesion.dossierId.slice(0, 8)}…
          </span>
        ) : null}

        {/* Acciones de caso (ciudadano) */}
        <div className="ml-auto flex items-center gap-1">
          {modo === "ciudadano" && (
            <>
              {/* Panel expediente */}
              <button
                onClick={() => setExpOpen(true)}
                title="Ver mi expediente — lo que ya sabemos de tu caso"
                className="relative rounded-lg px-2 py-1.5 text-xs text-gray-500 transition hover:bg-gray-100 hover:text-gray-700"
              >
                <ClipboardList className="h-4 w-4" />
                {expedienteAcumulado && (
                  <span className="absolute right-0.5 top-0.5 h-1.5 w-1.5 rounded-full bg-[#047857]" />
                )}
              </button>
              {/* Nuevo caso */}
              <button
                onClick={confirmarNuevoCaso}
                title="Empezar un caso nuevo"
                className={`rounded-lg px-2.5 py-1.5 text-xs transition ${
                  confirmNuevo
                    ? "bg-red-50 font-medium text-red-600"
                    : "text-gray-500 hover:bg-gray-100 hover:text-gray-700"
                }`}
              >
                {confirmNuevo ? "¿Seguro? Se limpia el expediente" : "Nuevo caso"}
              </button>
            </>
          )}

          {/* Selector de modo */}
          <div className="hidden rounded-lg border border-gray-200 bg-gray-50 p-0.5 sm:flex">
            <button
              onClick={() => setModo("ciudadano")}
              className={`rounded-md px-3 py-1 text-xs font-medium transition ${
                modo === "ciudadano"
                  ? "bg-[#047857] text-white"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              Ciudadano
            </button>
            <button
              onClick={() => setModo("abogado")}
              className={`rounded-md px-3 py-1 text-xs font-medium transition ${
                modo === "abogado"
                  ? "bg-[#c81e1e] text-white"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              Abogado
            </button>
          </div>

          {/* Salir (solo con sesión) */}
          {sesion ? (
            <button
              onClick={() => {
                cerrarSesion();
                window.location.href = "/";
              }}
              title="Cerrar sesión y volver al inicio"
              className="ml-1 rounded-lg px-2 py-1.5 text-xs text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
            >
              Salir
            </button>
          ) : (
            <Link
              href="/"
              className="ml-1 rounded-lg px-2 py-1.5 text-xs text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
            >
              Inicio
            </Link>
          )}
        </div>
      </header>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {isEmpty ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[#047857]">
              <Scale className="h-8 w-8 text-white" />
            </div>
            <div className="max-w-sm">
              <h2 className="mb-1 font-serif text-xl font-semibold text-gray-900">
                Justicia precisa, verificable
              </h2>
              <p className="text-sm text-gray-500">
                Pregunta sobre derecho mexicano. Cada respuesta viene con citas verificadas
                contra fuentes oficiales.
              </p>
            </div>
            <div className="flex flex-wrap justify-center gap-2">
              {[
                "Mi casero quiere subir la renta al doble, ¿es legal?",
                "¿Qué hago si me cobran un cargo no autorizado?",
                "Me despidieron sin motivo, ¿qué tengo derecho?",
              ].map((s) => (
                <button
                  key={s}
                  onClick={() => handleSend(s)}
                  className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs text-gray-600 transition-colors hover:border-[#047857] hover:text-[#047857]"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl py-4">
            {messages.map((msg) => (
              <MessageBubble
                key={msg.id}
                msg={msg}
                stage={currentStage}
                isQuerying={isQuerying}
                onClarifySubmit={handleClarifySubmit}
              />
            ))}

            {/* Consentimiento expreso LFPDPPP: tras la 1a respuesta completa,
                solo con caso guardado (en modo abierto la nota bajo el input cubre) */}
            {modo === "ciudadano" &&
              !isQuerying &&
              sesion?.dossierId &&
              messages.some((m) => m.done?.respuesta) &&
              !consentDecidido && (
                <ConsentCard
                  dossierId={sesion.dossierId}
                  onDecide={() => setConsentDecidido(true)}
                />
              )}
          </div>
        )}
      </div>

      {/* Nota de consentimiento (modo abierto) — bajo los mensajes, sobre el input */}
      {modo === "ciudadano" && enModoAbierto && <ConsentNotice />}

      {/* Input */}
      <InputBar onSend={handleSend} onStop={stopQuery} isQuerying={isQuerying} />

      {/* Modales / drawers */}
      {convertOpen && <ConvertCaseModal onClose={() => setConvertOpen(false)} />}
      <ExpedientePanel
        expediente={expedienteAcumulado}
        abierto={expOpen}
        onClose={() => setExpOpen(false)}
      />
    </div>
  );
}
