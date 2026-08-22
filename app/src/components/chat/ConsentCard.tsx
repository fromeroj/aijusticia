"use client";

import { useState } from "react";
import { ShieldCheck, HeartHandshake, X } from "lucide-react";
import { Button } from "@/components/ui/button";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Tarjeta de consentimiento EXPRESO para entrenamiento (LFPDPPP 2025).
 * Aparece tras una respuesta útil. Opt-in separado del servicio, revocable.
 * Solo alimenta el adapter GENERAL — jamás datos de bufetes.
 */
export function ConsentCard({
  dossierId,
  onDecide,
}: {
  dossierId: string | null;
  onDecide?: (otorgo: boolean) => void;
}) {
  const [estado, setEstado] = useState<"pendiente" | "otorgado" | "rechazado" | "error">("pendiente");

  const decidir = async (otorgar: boolean) => {
    if (!dossierId) {
      // Sin dossier persistente aún: registrar localmente cuando exista sesión
      setEstado(otorgar ? "otorgado" : "rechazado");
      onDecide?.(otorgar);
      return;
    }
    try {
      const res = await fetch(`${API_URL}/dossiers/${dossierId}/consentimiento`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ otorgar }),
      });
      if (!res.ok) throw new Error();
      setEstado(otorgar ? "otorgado" : "rechazado");
      onDecide?.(otorgar);
    } catch {
      setEstado("error");
    }
  };

  if (estado === "otorgado") {
    return (
      <div className="flex gap-3 px-4 py-2">
        <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-green-100">
          <HeartHandshake className="h-4 w-4 text-green-600" />
        </div>
        <div className="max-w-[85%] rounded-2xl border border-green-200 bg-green-50 px-4 py-3">
          <p className="text-sm text-green-900">
            ¡Gracias! Tu experiencia (anónima) ayudará a que la IA oriente mejor a
            otras personas. Puedes revocarlo cuando quieras.
          </p>
        </div>
      </div>
    );
  }

  if (estado === "rechazado") return null;

  return (
    <div className="flex gap-3 px-4 py-2">
      <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-amber-100">
        <ShieldCheck className="h-4 w-4 text-amber-600" />
      </div>
      <div className="max-w-[85%] rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3">
        <p className="mb-1 text-sm font-medium text-amber-900">
          ¿Nos ayudas a mejorar la IA para otras personas?
        </p>
        <p className="mb-3 text-xs text-amber-700">
          Autorizo que esta conversación — <strong>anónimizada</strong> (sin tu nombre ni
          datos que te identifiquen) — sea usada para mejorar el modelo. Es
          completamente voluntario, no afecta tu servicio, y puedes revocarlo cuando
          quieras. Tus archivos siempre permanecen cifrados.
        </p>
        <div className="flex gap-2">
          <Button
            size="sm"
            className="bg-[#047857] hover:bg-[#064e3b]"
            onClick={() => decidir(true)}
          >
            Sí, autorizo
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="border-amber-300 text-amber-700 hover:bg-amber-100"
            onClick={() => decidir(false)}
          >
            No, gracias
          </Button>
        </div>
        {estado === "error" && (
          <p className="mt-2 text-xs text-red-600">
            No se pudo registrar. Puedes intentarlo más tarde.
          </p>
        )}
      </div>
    </div>
  );
}
