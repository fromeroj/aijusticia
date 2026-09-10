"use client";

/**
 * /reclamar — el abogado canjea el código de invitación que le pasó el ciudadano.
 *
 * Llega por QR (?c=CODIGO), enlace de WhatsApp, o escribiendo el código a mano.
 * Requiere sesión de abogado (la de /app, sessionStorage aij_tokens); si no la
 * hay, se le manda a /app conservando el código en la URL de retorno.
 */
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Scale, KeyRound, Loader2, CheckCircle2, AlertCircle, ArrowRight } from "lucide-react";
import { canjearInvitacion } from "@/lib/invitaciones";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

interface TokensDespacho {
  access: string;
  refresh: string;
  tipo?: string;
}

function leerTokens(): TokensDespacho | null {
  try {
    const raw = sessionStorage.getItem("aij_tokens");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

async function getAccess(): Promise<string | null> {
  const t = leerTokens();
  if (!t) return null;
  try {
    const payload = JSON.parse(atob(t.access.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    if ((payload.exp ?? 0) > Date.now() / 1000 + 5) return t.access;
    const r = await fetch(`${API_URL}/auth/token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ via: "refresh", credential: t.refresh }),
    });
    if (!r.ok) return null;
    const d = await r.json();
    sessionStorage.setItem("aij_tokens", JSON.stringify(
      { access: d.access_token, refresh: d.refresh_token }));
    return d.access_token;
  } catch {
    return null;
  }
}

export default function ReclamarPage() {
  return (
    <Suspense fallback={
      <div className="flex min-h-[100dvh] items-center justify-center bg-white">
        <Loader2 className="h-6 w-6 animate-spin text-[#047857]" />
      </div>
    }>
      <Reclamar />
    </Suspense>
  );
}

function Reclamar() {
  const params = useSearchParams();
  const [etiqueta, setEtiqueta] = useState("");
  const [codigo, setCodigo] = useState(params.get("c") ?? "");
  const [estado, setEstado] = useState<"form" | "enviando" | "ok" | "error" | "sin_sesion">("form");
  const [mensaje, setMensaje] = useState("");

  useEffect(() => {
    // si trae código por URL y hay sesión, intentar directo
    const c = params.get("c");
    if (c) {
      setCodigo(c);
      getAccess().then((tok) => {
        if (tok) canjear(c, tok);
        else setEstado("sin_sesion");
      });
    } else {
      getAccess().then((tok) => { if (!tok) setEstado("sin_sesion"); });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const canjear = async (cod: string, token: string) => {
    setEstado("enviando");
    const r = await canjearInvitacion(cod, token, etiqueta.trim() || undefined);
    if (r.ok) {
      setEstado("ok");
    } else {
      setEstado("error");
      setMensaje(r.error || "Código no válido");
    }
  };

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    const limpio = codigo.trim().toUpperCase().replace(/[\s-]/g, "");
    if (limpio.length < 8) {
      setEstado("error");
      setMensaje("Escribe el código completo (10 caracteres)");
      return;
    }
    const token = await getAccess();
    if (!token) {
      setEstado("sin_sesion");
      return;
    }
    canjear(limpio, token);
  };

  return (
    <div className="flex min-h-[100dvh] flex-col bg-white">
      <header className="px-5 py-4">
        <div className="mx-auto flex max-w-md items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#047857]">
            <Scale className="h-5 w-5 text-white" />
          </div>
          <span className="text-sm font-semibold text-gray-900">Acceso a un caso compartido</span>
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-5 pb-10">
        <div className="w-full max-w-md">
          {estado === "ok" ? (
            <div className="rounded-2xl border border-[#047857]/25 bg-[#ecfdf5] p-8 text-center">
              <CheckCircle2 className="mx-auto h-12 w-12 text-[#047857]" />
              <h1 className="mt-3 text-lg font-bold text-gray-900">Solicitud enviada</h1>
              <p className="mt-2 text-sm text-gray-600">
                El ciudadano recibió tu solicitud. Cuando la acepte, el caso aparece
                en tu app con su expediente y documentos.
              </p>
              <Link
                href="/app"
                className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[#047857] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#036c4c]"
              >
                Ir a mis casos <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          ) : estado === "sin_sesion" ? (
            <div className="rounded-2xl border border-gray-200 bg-white p-8 text-center shadow-sm">
              <KeyRound className="mx-auto h-10 w-10 text-[#047857]" />
              <h1 className="mt-3 text-lg font-bold text-gray-900">Entra como abogado</h1>
              <p className="mt-2 text-sm text-gray-500">
                Para canjear el código necesitas tu cuenta profesional
                {codigo ? " — el código se conserva en el enlace" : ""}.
              </p>
              <Link
                href={`/app${codigo ? `?volver=/reclamar%3Fc%3D${encodeURIComponent(codigo)}` : ""}`}
                className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[#047857] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#036c4c]"
              >
                Entrar / registrarme <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          ) : (
            <form onSubmit={enviar} className="rounded-2xl border border-gray-200 bg-white p-8 shadow-sm">
              <h1 className="text-lg font-bold text-gray-900">Canjear código de invitación</h1>
              <p className="mt-1 mb-5 text-sm text-gray-500">
                Tu cliente te compartió un código de 10 caracteres (o un QR que te trajo aquí).
              </p>
              <input
                value={codigo}
                onChange={(e) => { setCodigo(e.target.value.toUpperCase()); setEstado("form"); }}
                placeholder="XXXXX-XXXXX"
                autoCapitalize="characters"
                autoCorrect="off"
                className="w-full rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-center font-mono text-lg tracking-[0.25em] text-gray-900 focus:border-[#047857] focus:outline-none"
              />
              <input
                value={etiqueta}
                onChange={(e) => setEtiqueta(e.target.value)}
                placeholder="¿Cómo te conocen en este caso? (opcional, p. ej. 'Berto — comprador')"
                maxLength={60}
                className="mt-3 w-full rounded-xl border border-gray-200 bg-gray-50 px-4 py-2.5 text-xs text-gray-900 placeholder:text-gray-300 focus:border-[#047857] focus:outline-none"
              />
              {estado === "error" && (
                <p className="mt-3 flex items-center gap-1.5 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">
                  <AlertCircle className="h-3.5 w-3.5 shrink-0" /> {mensaje}
                </p>
              )}
              <button
                type="submit"
                disabled={estado === "enviando"}
                className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-[#047857] py-3 text-sm font-semibold text-white hover:bg-[#036c4c] disabled:opacity-40"
              >
                {estado === "enviando" ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
                {estado === "enviando" ? "Enviando…" : "Solicitar acceso al caso"}
              </button>
            </form>
          )}
        </div>
      </main>

      <footer className="px-6 pb-6 text-center">
        <p className="text-[10px] text-gray-400">
          🇲🇽 AI Justicia — el caso pertenece al ciudadano; tu acceso es revocable por él.
        </p>
      </footer>
    </div>
  );
}
