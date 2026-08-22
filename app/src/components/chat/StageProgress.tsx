"use client";

import { Check, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { StageId } from "@/lib/store";

const STAGES: { id: StageId; label: string }[] = [
  { id: "analisis", label: "Analizando" },
  { id: "recuperacion", label: "Buscando fuentes" },
  { id: "generacion", label: "Generando" },
  { id: "verificacion", label: "Verificando citas" },
];

export function StageProgress({ current }: { current: StageId | null }) {
  if (!current) return null;

  const currentIdx = STAGES.findIndex((s) => s.id === current);

  return (
    <div className="flex flex-wrap gap-2 py-2">
      {STAGES.map((stage, idx) => {
        const isDone = idx < currentIdx;
        const isActive = idx === currentIdx;
        return (
          <div
            key={stage.id}
            className={cn(
              "flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-colors",
              isDone && "bg-green-100 text-green-700",
              isActive && "bg-blue-100 text-blue-700",
              !isDone && !isActive && "bg-gray-100 text-gray-400",
            )}
          >
            {isDone && <Check className="h-3 w-3" />}
            {isActive && <Loader2 className="h-3 w-3 animate-spin" />}
            <span>{stage.label}</span>
          </div>
        );
      })}
    </div>
  );
}
