"use client";

import { Check, Loader2, Scale, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import type { StageId } from "@/lib/store";

const STAGES: { id: StageId; label: string }[] = [
  { id: "analisis", label: "Analizando" },
  { id: "clarificacion", label: "Preguntas de contexto" },
  { id: "recuperacion", label: "Buscando fuentes" },
  { id: "generacion", label: "Generando respuesta" },
  { id: "verificacion", label: "Verificando citas" },
];

export function AnalysisCard({
  materia,
  currentStage,
  isQuerying,
}: {
  materia: string | null;
  currentStage: StageId | null;
  isQuerying: boolean;
}) {
  // Solo mostrar el card de análisis durante la fase activa (antes de que llegue texto)
  const currentIdx = currentStage ? STAGES.findIndex((s) => s.id === currentStage) : -1;

  return (
    <div className="flex gap-3 px-4 py-3">
      <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-[#047857]">
        <Scale className="h-4 w-4 text-white" />
      </div>
      <div className="max-w-[85%] rounded-2xl bg-gray-100 px-4 py-3">
        {/* Materia + tiempo estimado */}
        <div className="mb-2 flex items-center gap-2">
          {materia && (
            <span className="rounded-full bg-[#d1fae5] px-2.5 py-0.5 text-xs font-medium text-[#047857]">
              {materia}
            </span>
          )}
          <span className="flex items-center gap-1 text-[11px] text-gray-400">
            <Clock className="h-3 w-3" />
            ~3 min
          </span>
        </div>

        {/* Etapas */}
        <div className="space-y-1">
          {STAGES.map((stage) => {
            const idx = STAGES.indexOf(stage);
            const isDone = currentIdx > idx;
            const isActive = currentStage === stage.id;
            const isPending = currentIdx >= 0 && idx > currentIdx;

            // Solo mostrar etapas relevantes (si no hay clarificacion, saltarla)
            if (stage.id === "clarificacion" && currentStage !== "clarificacion" && currentIdx > 1) {
              return null;
            }

            return (
              <div
                key={stage.id}
                className={cn(
                  "flex items-center gap-2 text-xs transition-colors",
                  isDone && "text-green-600",
                  isActive && "text-blue-600",
                  isPending && "text-gray-300",
                  !isDone && !isActive && !isPending && "text-gray-400",
                )}
              >
                {isDone && <Check className="h-3 w-3 flex-shrink-0" />}
                {isActive && <Loader2 className="h-3 w-3 flex-shrink-0 animate-spin" />}
                {isPending && <div className="h-3 w-3 flex-shrink-0 rounded-full border border-gray-300" />}
                {!isDone && !isActive && !isPending && <div className="h-3 w-3 flex-shrink-0" />}
                <span>{stage.label}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
