"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Scale, FileText, Search, ShieldCheck, ArrowRight, ArrowLeft,
  KeyRound, Copy, Check, Building2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useChatStore } from "@/lib/store";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const ESPECIALIDADES = [
  "Civil", "Mercantil", "Penal", "Laboral", "Familiar",
  "Administrativo", "Fiscal", "Amparo", "Corporativo",
];

export default function OnboardingAbogado() {
  const router = useRouter();
  const iniciarSesion = useChatStore((s) => s.iniciarSesion);
  const [paso, setPaso] = useState(0);
  const [cedula, setCedula] = useState("");
  const [especialidades, setEspecialidades] = useState<string[]>([]);
  const [bufete, setBufete] = useState("");
  const [registrando, setRegistrando] = useState(false);
  const [frase, setFrase] = useState<string | null>(null);
  const [actorId, setActorId] = useState<string | null>(null);
  const [bufeteId, setBufeteId] = useState<string | null>(null);
  const [copiada, setCopiada] = useState(false);
  const [confirmo, setConfirmo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleEsp = (e: string) =>
    setEspecialidades((prev) =>
      prev.includes(e) ? prev.filter((x) => x !== e) : [...prev, e],
    );

  const registrar = async () => {
    if (cedula.trim().length < 5) {
      setError("Ingresa tu cédula profesional (mínimo 5 dígitos)");
      return;
    }
    setRegistrando(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/abogados/registro`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cedula: cedula.trim(),
          especialidades: especialidades.length ? especialidades : null,
          bufete_nombre: bufete.trim() || null,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const d = await res.json();
      setFrase(d.frase_recuperacion);
      setActorId(d.actor_id);
      setBufeteId(d.bufete_id);
      setPaso(2);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error de conexión");
    } finally {
      setRegistrando(false);
    }
  };

  const entrar = () => {
    if (!actorId) return;
    iniciarSesion({
      tipo: "abogado",
      actorId,
      bufeteId,
      creadoEn: Date.now(),
    });
    router.push("/chat");
  };

  return (
    <div className="flex min-h-screen flex-col bg-white">
      {/* Header */}
      <header className="border-b border-gray-100 px-6 py-4">
        <div className="mx-auto flex max-w-3xl items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#c81e1e]">
            <Scale className="h-5 w-5 text-white" />
          </div>
          <span className="text-sm font-semibold text-gray-900">Acceso profesional</span>
          <div className="ml-auto flex gap-1.5">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className={`h-1.5 w-8 rounded-full transition ${
                  i <= paso ? "bg-[#c81e1e]" : "bg-gray-200"
                }`}
              />
            ))}
          </div>
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-6 py-10">
        <div className="w-full max-w-xl">
          {/* PASO 1: Qué incluye */}
          {paso === 0 && (
            <div className="text-center">
              <h1 className="mb-2 text-2xl font-bold text-gray-900">Modo profesional</h1>
              <p className="mb-8 text-sm text-gray-500">
                Sin entrevistas ciudadanas. Directo al fundamento.
              </p>
              <div className="space-y-4 text-left">
                <Info
                  icon={<Search className="h-5 w-5" />}
                  titulo="Consultas técnicas con fundamento"
                  texto="Pregunta como preguntas a un colega: la respuesta llega con artículos, fracciones, épocas y registros del SJF citados."
                />
                <Info
                  icon={<FileText className="h-5 w-5" />}
                  titulo="Generación de documentos"
                  texto='"Genera un contrato de compravena", "redacta una demanda de alimentos" — documentos ejecutables con placeholders y base normativa.'
                />
                <Info
                  icon={<ShieldCheck className="h-5 w-5" />}
                  titulo="Modelo privado de tu bufete"
                  texto="Los casos y documentos de tu despacho entrenan un modelo exclusivo. Tu know-how jamás alimenta el modelo general ni el de otros bufetes."
                />
              </div>
              <Button
                className="mt-8 w-full bg-[#c81e1e] py-6 text-base hover:bg-[#a01717]"
                onClick={() => setPaso(1)}
              >
                Registrarme <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          )}

          {/* PASO 2: Datos profesionales */}
          {paso === 1 && (
            <div>
              <h1 className="mb-1 text-2xl font-bold text-gray-900">Tus datos profesionales</h1>
              <p className="mb-6 text-sm text-gray-500">
                La verificación de cédula está en proceso; registramos tus datos ahora.
              </p>
              <div className="space-y-5">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700">
                    Cédula profesional *
                  </label>
                  <Input
                    value={cedula}
                    onChange={(e) => setCedula(e.target.value)}
                    placeholder="Ej. 12345678"
                    inputMode="numeric"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700">
                    Especialidades
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {ESPECIALIDADES.map((e) => (
                      <button
                        key={e}
                        type="button"
                        onClick={() => toggleEsp(e)}
                        className={`rounded-full border px-3 py-1 text-xs transition ${
                          especialidades.includes(e)
                            ? "border-[#c81e1e] bg-[#c81e1e] text-white"
                            : "border-gray-200 bg-white text-gray-600 hover:border-[#c81e1e]/50"
                        }`}
                      >
                        {e}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="mb-1.5 flex items-center gap-1.5 text-sm font-medium text-gray-700">
                    <Building2 className="h-3.5 w-3.5" />
                    Bufete / despacho (opcional)
                  </label>
                  <Input
                    value={bufete}
                    onChange={(e) => setBufete(e.target.value)}
                    placeholder="Ej. Hernández & Asociados"
                  />
                  <p className="mt-1.5 text-xs text-gray-400">
                    Si registras bufete, tus datos entrenan el modelo privado del despacho.
                  </p>
                </div>
              </div>
              {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
              <div className="mt-7 flex gap-3">
                <Button variant="outline" className="px-4" onClick={() => setPaso(0)}>
                  <ArrowLeft className="h-4 w-4" />
                </Button>
                <Button
                  className="flex-1 bg-[#c81e1e] py-6 text-base hover:bg-[#a01717]"
                  onClick={registrar}
                  disabled={registrando}
                >
                  {registrando ? "Registrando…" : "Crear mi acceso"}
                </Button>
              </div>
            </div>
          )}

          {/* PASO 3: Frase */}
          {paso === 2 && frase && (
            <div className="text-center">
              <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-[#c81e1e]">
                <KeyRound className="h-7 w-7 text-white" />
              </div>
              <h1 className="mb-2 text-2xl font-bold text-gray-900">Tu frase de acceso</h1>
              <p className="mb-6 text-sm font-medium text-red-600">
                ⚠️ Cópiala AHORA — no volverá a mostrarse
              </p>
              <div className="mx-auto mb-6 max-w-lg rounded-xl border-2 border-dashed border-[#c81e1e]/40 bg-[#c81e1e]/5 p-5">
                <p className="font-mono text-base font-semibold leading-loose tracking-wide text-gray-900">
                  {frase}
                </p>
                <button
                  className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-[#c81e1e] hover:underline"
                  onClick={async () => {
                    await navigator.clipboard.writeText(frase);
                    setCopiada(true);
                    setTimeout(() => setCopiada(false), 2000);
                  }}
                >
                  {copiada ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  {copiada ? "¡Copiada!" : "Copiar frase"}
                </button>
              </div>
              <label className="mx-auto mb-6 flex max-w-md cursor-pointer items-start gap-2 text-left text-sm text-gray-600">
                <input
                  type="checkbox"
                  checked={confirmo}
                  onChange={(e) => setConfirmo(e.target.checked)}
                  className="mt-0.5 h-4 w-4 accent-[#c81e1e]"
                />
                Guardé mi frase y entiendo que no puede recuperarse.
              </label>
              <Button
                className="w-full bg-[#c81e1e] py-6 text-base hover:bg-[#a01717] disabled:opacity-40"
                onClick={entrar}
                disabled={!confirmo}
              >
                Entrar al modo profesional <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function Info({ icon, titulo, texto }: { icon: React.ReactNode; titulo: string; texto: string }) {
  return (
    <div className="flex gap-4 rounded-xl border border-gray-100 bg-gray-50 p-4">
      <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-[#c81e1e]/10 text-[#c81e1e]">
        {icon}
      </div>
      <div>
        <div className="font-semibold text-gray-900">{titulo}</div>
        <div className="mt-0.5 text-sm leading-relaxed text-gray-500">{texto}</div>
      </div>
    </div>
  );
}
