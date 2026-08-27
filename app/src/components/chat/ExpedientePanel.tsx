"use client";

/**
 * Panel del expediente: lo que el sistema YA sabe del caso del usuario.
 * Drawer lateral — transparency del estado interno del pipeline.
 */
import { ClipboardList, X } from "lucide-react";
import type { Expediente } from "@/lib/streamQuery";

// Campos legibles del expediente que produce el engine
const ETIQUETAS: Record<string, string> = {
  materia: "Materia",
  jurisdiccion: "Jurisdicción",
  entidad: "Entidad",
  tipo_procedimiento: "Tipo de procedimiento",
  fecha_hechos: "Fecha de los hechos",
  cuantia: "Cuantía",
  partes: "Partes involucradas",
  empleador: "Empleador",
  institucion: "Institución",
  contrato: "Contrato",
  plazo: "Plazo",
  documentos: "Documentos disponibles",
  hechos: "Hechos relevantes",
  // cualquier otra clave se muestra con su nombre humanizado
};

function humanizar(k: string): string {
  if (ETIQUETAS[k]) return ETIQUETAS[k];
  return k.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

function valorLegible(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return v.map(valorLegible).filter(Boolean).join(" · ");
  if (typeof v === "object") {
    return Object.entries(v as Record<string, unknown>)
      .map(([k, vv]) => `${humanizar(k)}: ${valorLegible(vv)}`)
      .join(" · ");
  }
  return "";
}

export function ExpedientePanel({
  expediente,
  abierto,
  onClose,
}: {
  expediente: Expediente | null;
  abierto: boolean;
  onClose: () => void;
}) {
  if (!abierto) return null;

  const entradas = expediente
    ? Object.entries(expediente as unknown as Record<string, unknown>)
        .map(([k, v]) => [k, valorLegible(v)] as const)
        .filter(([, v]) => v && v.length > 1 && v !== "null")
    : [];

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/30" onClick={onClose}>
      <div
        className="h-full w-full max-w-sm overflow-y-auto bg-white p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ClipboardList className="h-5 w-5 text-[#047857]" />
            <h3 className="text-sm font-semibold text-gray-900">Tu expediente</h3>
          </div>
          <button onClick={onClose} className="rounded-lg p-1 text-gray-400 hover:bg-gray-100">
            <X className="h-5 w-5" />
          </button>
        </div>

        <p className="mb-4 text-xs leading-relaxed text-gray-500">
          Esto es lo que el sistema ha entendido de tu caso a partir de tus respuestas. Se acumula
          con cada pregunta — no necesitas repetir nada.
        </p>

        {entradas.length === 0 ? (
          <div className="rounded-xl border border-dashed border-gray-200 p-6 text-center">
            <p className="text-sm text-gray-400">
              Aún no hay datos.
              <br />
              Cuéntanos tu situación y el expediente se irá construyendo.
            </p>
          </div>
        ) : (
          <dl className="space-y-3">
            {entradas.map(([k, v]) => (
              <div key={k} className="rounded-lg bg-gray-50 px-3 py-2.5">
                <dt className="text-[11px] font-medium uppercase tracking-wide text-gray-400">
                  {humanizar(k)}
                </dt>
                <dd className="mt-0.5 text-sm text-gray-800">{v}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </div>
  );
}
