"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Scale, KeyRound, Smartphone, ArrowRight, Fingerprint } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChatStore } from "@/lib/store";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEVICE_KEY = "aij_device_token";
const GOOGLE_ENABLED = Boolean(process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID);

interface SesionResp {
  actor_id: string;
  tipo: "ciudadano" | "abogado";
  dossier_id: string | null;
  bufete_id: string | null;
  email: string | null;
}

export default function Entrar() {
  const router = useRouter();
  const iniciarSesion = useChatStore((s) => s.iniciarSesion);

  const [tieneDispositivo, setTieneDispositivo] = useState(false);
  const [tipoDispositivo, setTipoDispositivo] = useState<"ciudadano" | "abogado" | null>(null);
  const [frase, setFrase] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  useEffect(() => {
    // Retorno de Google OAuth: el callback ya verificó con Google y trae la sesión
    const q = new URLSearchParams(window.location.search);
    if (q.get("g") === "ok") {
      const s: SesionResp = {
        actor_id: q.get("actor") || "",
        tipo: (q.get("tipo") as "ciudadano" | "abogado") || "ciudadano",
        dossier_id: q.get("dossier") || null,
        bufete_id: q.get("bufete") || null,
        email: q.get("email") || null,
      };
      if (s.actor_id) {
        aplicarSesion(s);
        return;
      }
    } else if (q.get("g") === "error") {
      const motivo = q.get("motivo");
      setError(
        motivo === "config"
          ? "Google aún no está configurado en este despliegue. Usa tu frase."
          : "No se pudo entrar con Google. Intenta de nuevo o usa tu frase.",
      );
    }

    try {
      const raw = window.localStorage.getItem(DEVICE_KEY);
      if (raw) {
        const d = JSON.parse(raw) as { token: string; tipo: string };
        setTieneDispositivo(true);
        setTipoDispositivo(d.tipo as "ciudadano" | "abogado");
      }
    } catch { /* sin token */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const aplicarSesion = async (s: SesionResp) => {
    iniciarSesion({
      tipo: s.tipo,
      actorId: s.actor_id,
      dossierId: s.dossier_id ?? undefined,
      bufeteId: s.bufete_id,
      creadoEn: Date.now(),
    });
    // Vincular este dispositivo para one-tap la próxima vez
    try {
      const token = crypto.randomUUID().replace(/-/g, "") + crypto.randomUUID().replace(/-/g, "");
      window.localStorage.setItem(DEVICE_KEY, JSON.stringify({ token, tipo: s.tipo }));
      await fetch(`${API_URL}/auth/dispositivo/registrar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ actor_id: s.actor_id, token }),
      });
    } catch { /* la vinculación es best-effort */ }
    router.push("/chat");
  };

  const entrarDispositivo = async () => {
    setCargando(true);
    setError(null);
    try {
      const raw = window.localStorage.getItem(DEVICE_KEY);
      if (!raw) throw new Error("sin token");
      const { token } = JSON.parse(raw);
      const res = await fetch(`${API_URL}/auth/dispositivo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Dispositivo no vinculado");
      await aplicarSesion(await res.json());
    } catch (e) {
      window.localStorage.removeItem(DEVICE_KEY);
      setTieneDispositivo(false);
      setError(e instanceof Error ? e.message : "Error de conexión");
    } finally {
      setCargando(false);
    }
  };

  const entrarFrase = async () => {
    if (frase.trim().split(/\s+/).length < 8) {
      setError("Escribe tu frase completa (12 palabras).");
      return;
    }
    setCargando(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/auth/frase`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ frase: frase.trim() }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Frase incorrecta");
      await aplicarSesion(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error de conexión");
    } finally {
      setCargando(false);
    }
  };

  return (
    <div className="flex min-h-[100dvh] flex-col bg-white">
      {/* Header */}
      <header className="px-5 py-4">
        <div className="mx-auto flex max-w-md items-center gap-2">
          <Link href="/" className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#047857]">
            <Scale className="h-5 w-5 text-white" />
          </Link>
          <span className="text-sm font-semibold text-gray-900">Entrar a AI Justicia</span>
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-5 pb-10">
        <div className="w-full max-w-md space-y-4">

          {/* 1. Este dispositivo (one-tap) */}
          {tieneDispositivo && (
            <button
              onClick={entrarDispositivo}
              disabled={cargando}
              className="flex w-full items-center gap-4 rounded-2xl border-2 border-[#047857] bg-[#047857]/5 p-5 text-left transition active:scale-[0.99] disabled:opacity-50"
            >
              <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-xl bg-[#047857]">
                <Smartphone className="h-6 w-6 text-white" />
              </div>
              <div className="flex-1">
                <div className="font-semibold text-gray-900">
                  Continuar en este dispositivo
                </div>
                <div className="text-xs text-gray-500">
                  {tipoDispositivo === "abogado" ? "Tu cuenta profesional" : "Tu caso"} — un toque y entras
                </div>
              </div>
              <ArrowRight className="h-5 w-5 text-[#047857]" />
            </button>
          )}

          {/* 2. Google (si configurado) */}
          {GOOGLE_ENABLED ? (
            <a
              href={`https://accounts.google.com/o/oauth2/v2/auth?client_id=${process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID}&redirect_uri=${encodeURIComponent(typeof window !== "undefined" ? window.location.origin + "/api/auth/google/callback" : "")}&response_type=code&scope=openid%20email&prompt=select_account`}
              className="flex w-full items-center justify-center gap-3 rounded-2xl border-2 border-gray-200 bg-white p-4 font-medium text-gray-700 transition hover:border-gray-300 active:scale-[0.99]"
            >
              <svg className="h-5 w-5" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.1c-.22-.66-.35-1.36-.35-2.1s.13-1.44.35-2.1V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l3.66-2.84z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
              </svg>
              Continuar con Google
            </a>
          ) : (
            <div className="rounded-2xl border border-dashed border-gray-200 bg-gray-50 p-4 text-center">
              <div className="flex items-center justify-center gap-2 text-sm text-gray-400">
                <Fingerprint className="h-4 w-4" />
                Google y biometría llegarán pronto
              </div>
              <div className="mt-1 text-[10px] text-gray-400">
                (requiere configurar GOOGLE_CLIENT_ID en el despliegue)
              </div>
            </div>
          )}

          {/* Divisor */}
          <div className="flex items-center gap-3 py-1">
            <div className="h-px flex-1 bg-gray-200" />
            <span className="text-xs text-gray-400">o con tu frase</span>
            <div className="h-px flex-1 bg-gray-200" />
          </div>

          {/* 3. Frase de recuperación */}
          <div className="rounded-2xl border border-gray-200 p-5">
            <div className="mb-1 flex items-center gap-2 font-semibold text-gray-900">
              <KeyRound className="h-4 w-4 text-[#047857]" />
              Tengo mi frase de recuperación
            </div>
            <p className="mb-4 text-xs text-gray-500">
              Las 12 palabras que guardaste al crear tu cuenta.
            </p>
            <textarea
              value={frase}
              onChange={(e) => setFrase(e.target.value)}
              placeholder="ej. tribunal mango paseo resta laser oveja cita…"
              rows={2}
              autoCapitalize="none"
              autoCorrect="off"
              className="w-full resize-none rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-900 placeholder:text-gray-300 focus:border-[#047857] focus:outline-none focus:ring-2 focus:ring-[#047857]/10"
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); entrarFrase(); } }}
            />
            <Button
              className="mt-3 w-full bg-[#047857] py-5 text-base hover:bg-[#064e3b] disabled:opacity-40"
              onClick={entrarFrase}
              disabled={cargando}
            >
              {cargando ? "Entrando…" : "Entrar a mi caso"}
            </Button>
          </div>

          {error && (
            <p className="rounded-xl bg-red-50 px-4 py-3 text-center text-sm text-red-600">{error}</p>
          )}

          {/* Nuevo por aquí */}
          <p className="pt-2 text-center text-sm text-gray-500">
            ¿Primera vez?{" "}
            <Link href="/para-ti" className="font-semibold text-[#047857] hover:underline">
              Inicia tu consulta gratis
            </Link>
          </p>
        </div>
      </main>

      <footer className="px-6 pb-6 text-center">
        <p className="text-[10px] text-gray-400">
          🇲🇽 AI Justicia — Tu frase es tu llave: nosotros nunca la vemos ni podemos recuperarla.
        </p>
      </footer>
    </div>
  );
}
