"use client";

/**
 * Test de verificación de frase de recuperación: pedir 3 palabras al azar.
 * No deja avanzar hasta acertar — garantiza que el usuario REALMENTE la guardó.
 */
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Check, Copy, Eye, X } from "lucide-react";

export function PhraseVerify({
  frase,
  onVerificado,
  onCancelar,
  compacto = false,
}: {
  frase: string;
  onVerificado: () => void;
  onCancelar?: () => void;
  compacto?: boolean;
}) {
  const palabras = useMemo(() => frase.split(/\s+/).filter(Boolean), [frase]);
  // 3 posiciones aleatorias estables por montaje
  const posiciones = useMemo(() => {
    const idx = palabras.map((_, i) => i);
    const elegidas: number[] = [];
    while (elegidas.length < Math.min(3, palabras.length)) {
      const p = idx.splice(Math.floor(Math.random() * idx.length), 1)[0];
      elegidas.push(p);
    }
    return elegidas.sort((a, b) => a - b);
  }, [palabras]);

  const [respuestas, setRespuestas] = useState<Record<number, string>>({});
  const [revelada, setRevelada] = useState(!compacto); // en modal ya viene revelada
  const [errores, setErrores] = useState(0);
  const [copiada, setCopiada] = useState(false);
  const [falla, setFalla] = useState(false);

  const normalizar = (s: string) =>
    s.trim().toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");

  const verificar = () => {
    const ok = posiciones.every(
      (p) => normalizar(respuestas[p] || "") === normalizar(palabras[p])
    );
    if (ok) onVerificado();
    else {
      setFalla(true);
      setErrores((e) => e + 1);
    }
  };

  return (
    <div className="space-y-4">
      {/* Frase */}
      <div className="rounded-xl border-2 border-dashed border-[#047857]/40 bg-[#ecfdf5] p-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wide text-[#047857]">
            Tu frase de recuperación — {compacto ? "cópiala y guárdala" : "escríbela en papel"}
          </span>
          <button
            onClick={() => {
              navigator.clipboard?.writeText(frase);
              setCopiada(true);
              setTimeout(() => setCopiada(false), 1500);
            }}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-[#047857] hover:bg-white"
          >
            {copiada ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            {copiada ? "Copiada" : "Copiar"}
          </button>
        </div>
        <p className="select-all font-mono text-[15px] leading-relaxed text-gray-900">{frase}</p>
        <p className="mt-2 text-[11px] text-[#047857]/80">
          Es la única forma de recuperar tu caso desde otro dispositivo. No la compartas con nadie.
        </p>
        {!revelada && (
          <button
            onClick={() => setRevelada(true)}
            className="mt-2 flex items-center gap-1 text-xs text-gray-500 underline"
          >
            <Eye className="h-3.5 w-3.5" /> Ver de nuevo
          </button>
        )}
      </div>

      {/* Verificación */}
      <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
        <p className="mb-3 text-sm font-medium text-gray-700">
          Comprobemos que la guardaste — escribe{" "}
          <span className="text-[#047857]">
            la palabra {posiciones.map((p) => `#${p + 1}`).join(", ")}
          </span>{" "}
          de tu frase:
        </p>
        <div className="space-y-2">
          {posiciones.map((p) => (
            <div key={p} className="flex items-center gap-2">
              <span className="w-20 shrink-0 text-xs text-gray-500">Palabra {p + 1}</span>
              <input
                type="text"
                value={respuestas[p] || ""}
                onChange={(e) => {
                  setRespuestas((r) => ({ ...r, [p]: e.target.value }));
                  setFalla(false);
                }}
                className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-[#047857] focus:outline-none"
                placeholder={`Palabra ${p + 1}…`}
                autoComplete="off"
              />
            </div>
          ))}
        </div>
        {falla && (
          <p className="mt-2 flex items-center gap-1 text-xs text-red-600">
            <X className="h-3.5 w-3.5" /> Alguna palabra no coincide. Revísala — sin esta frase no
            podrás recuperar tu caso. {errores >= 2 && "Puedes ver la frase de nuevo arriba."}
          </p>
        )}
        {errores >= 2 && (
          <button onClick={() => setRevelada(true)} className="mt-1 text-xs text-[#047857] underline">
            Ver la frase de nuevo
          </button>
        )}
      </div>

      <div className="flex gap-2">
        <Button
          onClick={verificar}
          className="flex-1 bg-[#047857] hover:bg-[#036c4c]"
          disabled={posiciones.some((p) => !(respuestas[p] || "").trim())}
        >
          Ya la guardé, continuar
        </Button>
        {onCancelar && (
          <Button variant="outline" onClick={onCancelar}>
            Cancelar
          </Button>
        )}
      </div>
    </div>
  );
}
