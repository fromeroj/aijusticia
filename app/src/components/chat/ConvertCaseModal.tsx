"use client";

/**
 * Convertir chat abierto → caso guardado.
 * Crea el dossier anónimo, muestra la frase UNA vez con verificación de 3 palabras,
 * y vincula la sesión conservando TODO el historial y expediente del modo abierto.
 */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { FolderPlus, Lock, X } from "lucide-react";
import { useChatStore } from "@/lib/store";
import { canjearTokens, registrarDispositivo } from "@/lib/auth";
import { PhraseVerify } from "./PhraseVerify";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

declare global {
  interface Window {
    __aij_pendiente?: { actorId: string; dossierId: string };
  }
}

export function ConvertCaseModal({ onClose }: { onClose: () => void }) {
  const convertirACaso = useChatStore((s) => s.convertirACaso);
  const nMensajes = useChatStore((s) => s.messages.length);
  const [paso, setPaso] = useState<"info" | "creando" | "frase" | "error">("info");
  const [frase, setFrase] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const crear = async () => {
    setPaso("creando");
    setError(null);
    try {
      const res = await fetch(`${API_URL}/dossiers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const d = await res.json();
      setFrase(d.frase_recuperacion);
      setPaso("frase");
      // Canjear la frase (en memoria, UNA vez) por el par JWT — la sesión
      // queda autenticada; la frase no se guarda en el navegador.
      await canjearTokens("frase", d.frase_recuperacion).catch(() => null);
      // Device token para un-tap: la prueba de posesión es la frase recién
      // emitida (A3). Best-effort.
      try {
        const token =
          crypto.randomUUID().replace(/-/g, "") + crypto.randomUUID().replace(/-/g, "");
        window.localStorage.setItem(
          "aij_device_token",
          JSON.stringify({ token, tipo: "ciudadano" })
        );
        await registrarDispositivo(d.actor_id, token, d.frase_recuperacion);
      } catch {
        /* best-effort */
      }
      window.__aij_pendiente = { actorId: d.actor_id, dossierId: d.dossier_id };
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error de conexión");
      setPaso("error");
    }
  };

  const completar = () => {
    const p = window.__aij_pendiente;
    if (p) {
      convertirACaso({
        tipo: "ciudadano",
        actorId: p.actorId,
        dossierId: p.dossierId,
        creadoEn: Date.now(),
      });
    }
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-6">
      <div className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-t-2xl bg-white p-6 shadow-2xl sm:rounded-2xl">
        <div className="mb-4 flex items-start justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#047857]">
              <FolderPlus className="h-5 w-5 text-white" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-gray-900">Guardar como caso</h3>
              <p className="text-xs text-gray-500">
                {paso === "frase"
                  ? "Casi listo — guarda tu frase"
                  : `${nMensajes} mensajes y todo tu expediente se conservarán`}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="rounded-lg p-1 text-gray-400 hover:bg-gray-100">
            <X className="h-5 w-5" />
          </button>
        </div>

        {paso === "info" && (
          <div className="space-y-4">
            <ul className="space-y-2 text-sm text-gray-600">
              <li className="flex gap-2">
                <Lock className="mt-0.5 h-4 w-4 shrink-0 text-[#047857]" />
                Creamos una cuenta <strong>anónima</strong> — sin correo, sin teléfono, sin nombre.
              </li>
              <li className="flex gap-2">
                <Lock className="mt-0.5 h-4 w-4 shrink-0 text-[#047857]" />
                Recibirás una <strong>frase de recuperación de 12 palabras</strong>: es tu única
                llave para volver a tu caso desde cualquier dispositivo.
              </li>
              <li className="flex gap-2">
                <Lock className="mt-0.5 h-4 w-4 shrink-0 text-[#047857]" />
                Tu conversación de ahora se conserva completa — no pierdes nada.
              </li>
            </ul>
            <Button onClick={crear} className="w-full bg-[#047857] hover:bg-[#036c4c]">
              Crear mi caso anónimo
            </Button>
          </div>
        )}

        {paso === "creando" && (
          <p className="py-8 text-center text-sm text-gray-400">Creando tu caso…</p>
        )}

        {paso === "error" && (
          <div className="space-y-3">
            <p className="text-sm text-red-600">{error}</p>
            <Button onClick={crear} variant="outline" className="w-full">
              Reintentar
            </Button>
          </div>
        )}

        {paso === "frase" && frase && <PhraseVerify frase={frase} onVerificado={completar} />}
      </div>
    </div>
  );
}
