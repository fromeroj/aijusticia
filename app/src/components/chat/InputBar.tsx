"use client";

import { useState, useRef, useEffect, type KeyboardEvent } from "react";
import { Send, Square, Paperclip, Mic, MicOff, Loader2 } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function InputBar({
  onSend,
  onStop,
  isQuerying,
  onAttach,
}: {
  onSend: (text: string) => void;
  onStop: () => void;
  isQuerying: boolean;
  onAttach?: () => void;
}) {
  const [text, setText] = useState("");
  const [escuchando, setEscuchando] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || isQuerying) return;
    onSend(trimmed);
    setText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 160) + "px";
    }
  };

  const micClick = () => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) { setText("[Reconocimiento de voz no disponible en este navegador]"); return; }
    const rec = new SR();
    rec.lang = "es-MX";
    rec.interimResults = true;
    rec.continuous = false;
    setEscuchando(true);
    let finalText = "";
    rec.onresult = (ev: any) => {
      let interim = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        if (ev.results[i].isFinal) finalText += ev.results[i][0].transcript;
        else interim += ev.results[i][0].transcript;
      }
      setText(finalText || interim);
    };
    rec.onend = () => { setEscuchando(false); if (finalText.trim()) setText(finalText.trim()); };
    rec.onerror = () => setEscuchando(false);
    rec.start();
  };

  return (
    <div className="sticky bottom-0 z-10 border-t border-gray-200 bg-white/95 backdrop-blur-sm px-4 py-3"
      style={{ paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" }}
    >
      <div className="mx-auto flex max-w-3xl items-end gap-2">
        {onAttach && (
          <Button
            variant="ghost"
            size="icon"
            className="flex-shrink-0 text-gray-400 hover:text-gray-600"
            onClick={onAttach}
            disabled={isQuerying}
            aria-label="Adjuntar documento"
          >
            <Paperclip className="h-5 w-5" />
          </Button>
        )}
        {escuchando && (
          <div className="flex items-center gap-1 text-[11px] text-red-500 animate-pulse pb-2">
            <span className="size-2 rounded-full bg-red-500 animate-ping" /> Escuchando…
          </div>
        )}
        <Textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          placeholder="Escribe tu pregunta legal o toca el micrófono…"
          rows={1}
          className={cn(
            "min-h-[44px] max-h-40 resize-none rounded-2xl border-gray-200 bg-gray-50",
            "text-sm placeholder:text-gray-400 focus-visible:ring-[#047857]",
          )}
          disabled={isQuerying}
        />
        <button
          onClick={micClick}
          disabled={isQuerying}
          className={cn(
            "flex-shrink-0 rounded-full p-2.5 transition-colors",
            escuchando
              ? "bg-red-500 text-white animate-pulse"
              : "bg-gray-100 text-gray-400 hover:bg-gray-200 hover:text-gray-600"
          )}
          aria-label={escuchando ? "Detener" : "Hablar"}
          title={escuchando ? "Escuchando… click para detener" : "Hablar"}
        >
          {escuchando ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
        </button>
        {isQuerying ? (
          <Button
            variant="destructive"
            size="icon"
            className="flex-shrink-0 rounded-full"
            onClick={onStop}
            aria-label="Detener"
          >
            <Square className="h-4 w-4" />
          </Button>
        ) : (
          <Button
            size="icon"
            className="flex-shrink-0 rounded-full bg-[#047857] hover:bg-[#064e3b]"
            onClick={handleSend}
            disabled={!text.trim()}
            aria-label="Enviar"
          >
            <Send className="h-4 w-4" />
          </Button>
        )}
      </div>
      <p className="mx-auto mt-1.5 max-w-3xl text-center text-[11px] font-medium text-amber-700">
        ⚠️ El contenido generado por IA es exclusivamente informativo. No constituye asesoramiento legal ni sustituye la consulta con un abogado colegiado, quien es el único profesional autorizado para brindar orientación jurídica formal.
      </p>
    </div>
  );
}
