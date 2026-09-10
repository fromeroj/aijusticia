"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Scale, MessageCircleQuestion, FileSearch, BookOpenCheck,
  KeyRound, Copy, Check, ArrowRight, ArrowLeft, Lock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { PhraseVerify } from "@/components/chat/PhraseVerify";
import { useChatStore } from "@/lib/store";
import { canjearTokens, registrarDispositivo } from "@/lib/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const PASOS = 3;

export default function OnboardingCiudadano() {
  const router = useRouter();
  const iniciarSesion = useChatStore((s) => s.iniciarSesion);
  const [paso, setPaso] = useState(0);
  const [creando, setCreando] = useState(false);
  const [frase, setFrase] = useState<string | null>(null);
  const [dossierId, setDossierId] = useState<string | null>(null);
  const [actorId, setActorId] = useState<string | null>(null);
  const [copiada, setCopiada] = useState(false);
  const [confirmo, setConfirmo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const crearDossier = async () => {
    setCreando(true);
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
      setDossierId(d.dossier_id);
      setActorId(d.actor_id);
      setPaso(2);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error de conexión");
    } finally {
      setCreando(false);
    }
  };

  const entrar = async () => {
    if (!actorId || !dossierId) return;
    iniciarSesion({
      tipo: "ciudadano",
      actorId,
      dossierId,
      creadoEn: Date.now(),
    });
    // Canjear la frase (en memoria) por el par JWT — sesión autenticada.
    if (frase) await canjearTokens("frase", frase).catch(() => null);
    // Vincular este dispositivo para one-tap (prueba de posesión: la frase).
    try {
      const token = crypto.randomUUID().replace(/-/g, "") + crypto.randomUUID().replace(/-/g, "");
      window.localStorage.setItem("aij_device_token", JSON.stringify({ token, tipo: "ciudadano" }));
      await registrarDispositivo(actorId, token, frase ?? undefined);
    } catch { /* best-effort */ }
    router.push("/chat");
  };

  return (
    <div className="flex min-h-screen flex-col bg-white">
      {/* Header */}
      <header className="border-b border-gray-100 px-6 py-4">
        <div className="mx-auto flex max-w-3xl items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#047857]">
            <Scale className="h-5 w-5 text-white" />
          </div>
          <span className="text-sm font-semibold text-gray-900">Tu consulta legal</span>
          <div className="ml-auto flex gap-1.5">
            {Array.from({ length: PASOS }).map((_, i) => (
              <div
                key={i}
                className={`h-1.5 w-8 rounded-full transition ${
                  i <= paso ? "bg-[#047857]" : "bg-gray-200"
                }`}
              />
            ))}
          </div>
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-6 py-10">
        <div className="w-full max-w-xl">
          {/* PASO 1: Cómo funciona */}
          {paso === 0 && (
            <div className="text-center">
              <h1 className="mb-2 text-2xl font-bold text-gray-900">Así trabajaremos</h1>
              <p className="mb-8 text-sm text-gray-500">Tres pasos, como con un abogado de verdad.</p>
              <div className="space-y-4 text-left">
                <Info
                  icon={<MessageCircleQuestion className="h-5 w-5" />}
                  titulo="Te haré unas preguntas"
                  texto="Solo las que la ley necesita para tu caso: dónde pasa, quién está involucrado, fechas clave. Nada de formularios interminables."
                />
                <Info
                  icon={<FileSearch className="h-5 w-5" />}
                  titulo="Buscaré la ley que aplica"
                  texto="Leyes federales y de tu estado, más jurisprudencia del SJF. Si la ley necesita otro dato, te lo pregunto antes de responder."
                />
                <Info
                  icon={<BookOpenCheck className="h-5 w-5" />}
                  titulo="Te doy la respuesta con citas"
                  texto="Cada afirmación con su artículo o tesis. Gratis. Y si tu caso lo amerita, te conecto con un abogado verificado."
                />
              </div>
              <Button
                className="mt-8 w-full bg-[#047857] py-6 text-base hover:bg-[#064e3b]"
                onClick={() => setPaso(1)}
              >
                Continuar <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          )}

          {/* PASO 2: Privacidad + crear dossier */}
          {paso === 1 && (
            <div className="text-center">
              <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-100">
                <Lock className="h-7 w-7 text-amber-600" />
              </div>
              <h1 className="mb-2 text-2xl font-bold text-gray-900">Tu caso es privado</h1>
              <p className="mx-auto mb-6 max-w-md text-sm leading-relaxed text-gray-600">
                Tu caso se guarda cifrado en un <strong>expediente digital</strong> que solo
                tú controlas. Para protegerlo, generamos una{" "}
                <strong>frase de recuperación</strong> que verás una sola vez.
              </p>
              <div className="mx-auto mb-6 max-w-md rounded-xl border border-amber-200 bg-amber-50 p-4 text-left text-xs leading-relaxed text-amber-800">
                <strong>Guárdala bien:</strong> es la única forma de volver a entrar a tu
                expediente. No la compartas con nadie — ni con nosotros podremos
                recuperarla. Si la pierdes, el expediente se pierde.
              </div>
              {error && <p className="mb-4 text-sm text-red-600">{error}</p>}
              <div className="flex gap-3">
                <Button variant="outline" className="px-4" onClick={() => setPaso(0)}>
                  <ArrowLeft className="h-4 w-4" />
                </Button>
                <Button
                  className="flex-1 bg-[#047857] py-6 text-base hover:bg-[#064e3b]"
                  onClick={crearDossier}
                  disabled={creando}
                >
                  {creando ? "Creando tu expediente…" : "Crear mi expediente privado"}
                </Button>
              </div>
            </div>
          )}

          {/* PASO 3: La frase (UNA vez) + verificación de 3 palabras */}
          {paso === 2 && frase && (
            <div>
              <div className="mb-6 text-center">
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-[#047857]">
                  <KeyRound className="h-7 w-7 text-white" />
                </div>
                <h1 className="mb-1 text-2xl font-bold text-gray-900">Tu frase de recuperación</h1>
                <p className="text-sm text-red-600 font-medium">
                  ⚠️ Guárdala AHORA — comprobaremos que la tienes
                </p>
              </div>
              <PhraseVerify frase={frase} onVerificado={entrar} />
            </div>
          )}
        </div>
      </main>

      <footer className="px-6 py-4 text-center">
        <p className="text-[10px] text-gray-400">
          El contenido generado por IA es exclusivamente informativo y no sustituye la
          asesoría de un abogado colegiado.
        </p>
      </footer>
    </div>
  );
}

function Info({ icon, titulo, texto }: { icon: React.ReactNode; titulo: string; texto: string }) {
  return (
    <div className="flex gap-4 rounded-xl border border-gray-100 bg-gray-50 p-4">
      <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-[#047857]/10 text-[#047857]">
        {icon}
      </div>
      <div>
        <div className="font-semibold text-gray-900">{titulo}</div>
        <div className="mt-0.5 text-sm leading-relaxed text-gray-500">{texto}</div>
      </div>
    </div>
  );
}
