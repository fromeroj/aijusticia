"use client";

import { useState } from "react";
import { HelpCircle, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { ClarifyPayload, ClarifyQuestion } from "@/lib/streamQuery";

export function ClarifyCard({
  clarify,
  respondido = false,
  onSubmit,
}: {
  clarify: ClarifyPayload;
  respondido?: boolean;
  onSubmit: (respuestas: Record<string, string>) => void;
}) {
  const [respuestas, setRespuestas] = useState<Record<string, string>>({});

  const handleSubmit = () => {
    if (respondido) return;
    onSubmit(respuestas);
  };

  return (
    <div className={`flex gap-3 px-4 py-2 ${respondido ? "opacity-60" : ""}`}>
      <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-blue-100">
        <HelpCircle className="h-4 w-4 text-blue-600" />
      </div>
      <div className={`max-w-[85%] rounded-2xl border px-4 py-3 ${respondido ? "border-gray-200 bg-gray-50" : "border-blue-200 bg-blue-50"}`}>
        <p className={`mb-1 text-sm font-medium ${respondido ? "text-gray-500" : "text-blue-900"}`}>
          {respondido
            ? "✓ Respondido"
            : clarify.fase === "post_rag"
              ? "Revisé la ley aplicable a tu caso y necesito precisar:"
              : "Para orientarte mejor necesito saber:"}
        </p>
        {!respondido && clarify.ronda != null && clarify.rondas_max != null && (
          <p className="mb-3 text-[11px] text-blue-500">
            {clarify.fase === "post_rag"
              ? "Pregunta final antes de tu respuesta"
              : `Ronda ${clarify.ronda} de ${clarify.rondas_max}`}
          </p>
        )}

        <div className={`space-y-3 ${clarify.ronda != null ? "" : "mt-3"}`}>
          {clarify.questions.map((q) => (
            <QuestionInput
              key={q.id}
              question={q}
              value={respuestas[q.id] || ""}
              disabled={respondido}
              onChange={(val) => setRespuestas((prev) => ({ ...prev, [q.id]: val }))}
            />
          ))}
        </div>

        {!respondido && (
          <Button
            size="sm"
            className="mt-3 gap-1.5 bg-[#047857] hover:bg-[#064e3b]"
            onClick={handleSubmit}
          >
            Continuar
            <ArrowRight className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    </div>
  );
}

function QuestionInput({
  question,
  value,
  disabled = false,
  onChange,
}: {
  question: ClarifyQuestion;
  value: string;
  disabled?: boolean;
  onChange: (val: string) => void;
}) {
  if (question.tipo === "opcion" && question.opciones) {
    return (
      <div>
        <p className="text-xs text-blue-800">{question.texto}</p>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {question.opciones.map((op) => (
            <button
              key={op}
              disabled={disabled}
              onClick={() => onChange(op)}
              className={cn(
                "rounded-full border px-3 py-1 text-xs transition-colors",
                value === op
                  ? "border-[#047857] bg-[#047857] text-white"
                  : "border-blue-200 bg-white text-blue-700 hover:border-blue-400",
                disabled && "cursor-not-allowed opacity-70 hover:border-blue-200",
              )}
            >
              {op}
            </button>
          ))}
        </div>
      </div>
    );
  }

  // tipo texto o numero
  return (
    <div>
      <p className="text-xs text-blue-800">{question.texto}</p>
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Escribe tu respuesta..."
        className="mt-1 h-8 border-blue-200 bg-white text-sm"
      />
    </div>
  );
}
