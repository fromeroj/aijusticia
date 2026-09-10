"use client";

/**
 * /unirse — un abogado canjea el código de invitación de membresía a una firma.
 * Llega por enlace (?c=CODIGO) o escribiendo el código.
 */
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Scale, KeyRound, Loader2, CheckCircle2, AlertCircle, ArrowRight } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

function leerTokens(): { access: string; refresh: string } | null {
  try {
    const raw = sessionStorage.getItem("aij_tokens");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export default function UnirsePage() {
  return (
    <Suspense fallback={
      <div className="flex min-h-[100dvh] items-center justify-center bg-white">
        <Loader2 className="h-6 w-6 animate-spin text-[#047857]" />
      </div>
    }>
      <Unirse />
    </Suspense>
  );
}

function Unirse() {
  const params = useSearchParams();
  const [codigo, setCodigo] = useState(params.get("c") ?? "");
  const [estado, setEstado] = useState<"form" | "enviando" | "ok" | "error" | "sin_sesion">("form");
  const [mensaje, setMensaje] = useState("");

  const canjear = async (cod: string, token: string) => {
    setEstado("enviando");
    try {
      const r = await fetch(`${API_URL}/bufetes/miembros/unirse`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ codigo: cod }),
      });
      if (r.ok) {
        // el par JWT nuevo lleva el claim bufete de la firma a la que entramos
        const d = await r.json();
        if (d.access_token && d.refresh_token) {
          sessionStorage.setItem("aij_tokens", JSON.stringify(
            { access: d.access_token, refresh: d.refresh_token }));
        }
        setEstado("ok");
      } else {
        const d = await r.json().catch(() => ({}));
        setEstado("error");
        setMensaje(d.detail || "Código no válido");
      }
    } catch {
      setEstado("error");
      setMensaje("Error de conexión");
    }
  };

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    const limpio = codigo.trim().toUpperCase();
    if (limpio.length < 6) {
      setEstado("error");
      setMensaje("Escribe el código completo (8 caracteres)");
      return;
    }
    // sesión de abogado (la de /app, sessionStorage aij_tokens)
    const t = leerTokens();
    if (!t) { setEstado("sin_sesion"); return; }
    try {
      const payload = JSON.parse(atob(t.access.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
      if ((payload.exp ?? 0) < Date.now() / 1000 + 5) {
        const rr = await fetch(`${API_URL}/auth/token`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ via: "refresh", credential: t.refresh }),
        });
        if (!rr.ok) { setEstado("sin_sesion"); return; }
        const d = await rr.json();
        sessionStorage.setItem("aij_tokens", JSON.stringify({ access: d.access_token, refresh: d.refresh_token }));
        await canjear(limpio, d.access_token);
        return;
      }
      await canjear(limpio, t.access);
    } catch {
      setEstado("sin_sesion");
    }
  };

  return (
    <div className="flex min-h-[100dvh] flex-col bg-white">
      <header className="px-5 py-4">
        <div className="mx-auto flex max-w-md items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#047857]">
            <Scale className="h-5 w-5 text-white" />
          </div>
          <span className="text-sm font-semibold text-gray-900">Unirme a un despacho</span>
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-5 pb-10">
        <div className="w-full max-w-md">
          {estado === "ok" ? (
            <div className="rounded-2xl border border-[#047857]/25 bg-[#ecfdf5] p-8 text-center">
              <CheckCircle2 className="mx-auto h-12 w-12 text-[#047857]" />
              <h1 className="mt-3 text-lg font-bold text-gray-900">¡Bienvenido a la firma!</h1>
              <p className="mt-2 text-sm text-gray-600">
                Ya eres miembro. Los casos que te asignen aparecerán en tu app.
              </p>
              <Link href="/app" className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[#047857] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#036c4c]">
                Ir a mis casos <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          ) : estado === "sin_sesion" ? (
            <div className="rounded-2xl border border-gray-200 bg-white p-8 text-center shadow-sm">
              <KeyRound className="mx-auto h-10 w-10 text-[#047857]" />
              <h1 className="mt-3 text-lg font-bold text-gray-900">Entra como abogado</h1>
              <p className="mt-2 text-sm text-gray-500">
                Necesitas tu cuenta profesional para unirte a la firma
                {codigo ? " — el código se conserva en el enlace" : ""}.
              </p>
              <Link href={`/app${codigo ? `?volver=/unirse%3Fc%3D${encodeURIComponent(codigo)}` : ""}`} className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[#047857] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#036c4c]">
                Entrar / registrarme <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          ) : (
            <form onSubmit={enviar} className="rounded-2xl border border-gray-200 bg-white p-8 shadow-sm">
              <h1 className="text-lg font-bold text-gray-900">Código de invitación</h1>
              <p className="mt-1 mb-5 text-sm text-gray-500">
                El socio del despacho te compartió un código de 8 caracteres (o un enlace que te trajo aquí).
              </p>
              <input
                value={codigo}
                onChange={(e) => { setCodigo(e.target.value.toUpperCase()); setEstado("form"); }}
                placeholder="XXXXXXXX"
                autoCapitalize="characters"
                autoCorrect="off"
                className="w-full rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-center font-mono text-lg tracking-[0.3em] text-gray-900 focus:border-[#047857] focus:outline-none"
              />
              {estado === "error" && (
                <p className="mt-3 flex items-center gap-1.5 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">
                  <AlertCircle className="h-3.5 w-3.5 shrink-0" /> {mensaje}
                </p>
              )}
              <button type="submit" disabled={estado === "enviando"} className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-[#047857] py-3 text-sm font-semibold text-white hover:bg-[#036c4c] disabled:opacity-40">
                {estado === "enviando" ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
                {estado === "enviando" ? "Uniéndome…" : "Unirme a la firma"}
              </button>
            </form>
          )}
        </div>
      </main>

      <footer className="px-6 pb-6 text-center">
        <p className="text-[10px] text-gray-400">🇲🇽 AI Justicia — la firma decide qué casos ves; tu acceso es por asignación.</p>
      </footer>
    </div>
  );
}
