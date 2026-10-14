"use client";

/**
 * Mi cuenta — sesión, consentimiento LFPDPPP revocable y preferencias.
 *
 * S3: el consentimiento se lee/escribe con JWT (el engine verifica ownership).
 * Las preferencias de archivo (M4) aplican cuando la bóveda llegue (F3):
 * qué hacer al hacer click en un archivo.
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Scale, ShieldCheck, FileDown, LogOut, MessageSquareText, Loader2, ArrowLeft,
} from "lucide-react";
import { useChatStore } from "@/lib/store";
import { authFetch, SinSesionError } from "@/lib/auth";
import { SiteFooter } from "@/components/layout/SiteFooter";

const PREF_KEY = "aij_pref_archivo";
type PrefArchivo = "editor" | "descargar" | "descargar_y_abrir";

const OPCIONES: { valor: PrefArchivo; titulo: string; desc: string }[] = [
  { valor: "editor", titulo: "Abrir en el editor", desc: "Se abre directamente en el editor de documentos (requiere despacho con Nextcloud)" },
  { valor: "descargar", titulo: "Solo descargar", desc: "El archivo se descarga y tú decides cuándo abrirlo" },
  { valor: "descargar_y_abrir", titulo: "Descargar y abrir", desc: "Se descarga y se abre con la aplicación que tengas asociada (Word, LibreOffice…)" },
];

export default function CuentaPage() {
  const router = useRouter();
  const sesion = useChatStore((s) => s.sesion);
  const cerrarSesion = useChatStore((s) => s.cerrarSesion);

  const [consentimiento, setConsentimiento] = useState<boolean | null>(null);
  const [cambiandoConsent, setCambiandoConsent] = useState(false);
  const [pref, setPref] = useState<PrefArchivo>("descargar_y_abrir");
  const [errorSesion, setErrorSesion] = useState(false);

  useEffect(() => {
    if (!sesion) return;
    const guardado = window.localStorage.getItem(PREF_KEY) as PrefArchivo | null;
    if (guardado && OPCIONES.some((o) => o.valor === guardado)) setPref(guardado);
    if (sesion.dossierId) {
      authFetch(`/dossiers/${sesion.dossierId}`)
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then((d) => setConsentimiento(Boolean(d.consentimiento_entrenamiento)))
        .catch((e) => { if (e instanceof SinSesionError) setErrorSesion(true); });
    }
  }, [sesion]);

  const toggleConsentimiento = async () => {
    if (!sesion?.dossierId || consentimiento === null) return;
    setCambiandoConsent(true);
    try {
      const r = await authFetch(`/dossiers/${sesion.dossierId}/consentimiento`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ otorgar: !consentimiento }),
      });
      if (r.ok) setConsentimiento(!consentimiento);
    } catch (e) {
      if (e instanceof SinSesionError) setErrorSesion(true);
    } finally {
      setCambiandoConsent(false);
    }
  };

  const guardarPref = (valor: PrefArchivo) => {
    setPref(valor);
    window.localStorage.setItem(PREF_KEY, valor);
  };

  const salir = () => {
    cerrarSesion();
    router.push("/");
  };

  if (!sesion) {
    return (
      <div className="flex min-h-[100dvh] flex-col bg-white">
        <main className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[#047857]">
            <Scale className="h-6 w-6 text-white" />
          </div>
          <h1 className="text-lg font-bold text-gray-900">No hay sesión activa</h1>
          <p className="max-w-sm text-sm text-gray-500">
            Entra con tu frase de recuperación o tu dispositivo para ver tu cuenta.
          </p>
          <Link href="/entrar" className="rounded-xl bg-[#047857] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#036c4c]">
            Entrar
          </Link>
        </main>
        <SiteFooter />
      </div>
    );
  }

  return (
    <div className="flex min-h-[100dvh] flex-col bg-gray-50">
      <header className="border-b border-gray-200 bg-white px-5 py-4">
        <div className="mx-auto flex max-w-2xl items-center gap-3">
          <Link href="/chat" className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#047857]" title="Volver a Izel">
            <ArrowLeft className="h-4 w-4 text-white" />
          </Link>
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-gray-200">
            <Scale className="h-4 w-4 text-[#047857]" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-gray-900">Mi cuenta</h1>
            <p className="text-[11px] text-gray-400">
              {sesion.tipo === "abogado" ? "Cuenta profesional" : "Cuenta ciudadana"} · {sesion.actorId.slice(0, 8)}…
            </p>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-2xl flex-1 space-y-5 px-5 py-8">
        {errorSesion && (
          <div className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">
            Tu sesión expiró.{" "}
            <Link href="/entrar" className="font-semibold underline">Entra de nuevo</Link> con tu frase.
          </div>
        )}

        {/* Izel */}
        <section className="rounded-2xl border border-gray-100 bg-white p-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-[#047857] to-[#0d9488] text-sm font-bold text-white">
              I
            </div>
            <div className="flex-1">
              <h2 className="text-sm font-semibold text-gray-900">Izel, tu asistente</h2>
              <p className="text-xs text-gray-500">Siempre disponible, con el contexto de tus casos</p>
            </div>
            <Link href="/chat" className="flex items-center gap-1.5 rounded-xl bg-[#047857]/10 px-3 py-2 text-xs font-semibold text-[#047857] hover:bg-[#047857]/20">
              <MessageSquareText className="h-3.5 w-3.5" /> Abrir chat
            </Link>
          </div>
        </section>

        {/* Consentimiento LFPDPPP */}
        {sesion.dossierId && (
          <section className="rounded-2xl border border-gray-100 bg-white p-6">
            <div className="mb-1 flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-[#047857]" />
              <h2 className="text-sm font-semibold text-gray-900">Consentimiento de entrenamiento</h2>
            </div>
            <p className="mb-4 text-xs leading-relaxed text-gray-500">
              Si lo otorgas, tus conversaciones (anónimas y sin datos personales) pueden ayudar a
              entrenar al modelo general. Tu expediente estructurado nunca entra. Puedes revocarlo
              cuando quieras; la revocación aplica a futuros entrenamientos.
            </p>
            {consentimiento === null ? (
              <p className="flex items-center gap-2 text-xs text-gray-400">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando estado…
              </p>
            ) : (
              <button
                onClick={toggleConsentimiento}
                disabled={cambiandoConsent}
                className={`flex w-full items-center justify-between rounded-xl border px-4 py-3 text-sm font-medium transition disabled:opacity-50 ${
                  consentimiento
                    ? "border-[#047857]/30 bg-[#ecfdf5] text-[#047857]"
                    : "border-gray-200 bg-gray-50 text-gray-600"
                }`}
              >
                <span>{consentimiento ? "Otorgado — tocar para revocar" : "No otorgado — tocar para otorgar"}</span>
                <span className={`flex h-6 w-11 items-center rounded-full p-1 transition ${consentimiento ? "bg-[#047857]" : "bg-gray-300"}`}>
                  <span className={`h-4 w-4 rounded-full bg-white transition ${consentimiento ? "translate-x-5" : ""}`} />
                </span>
              </button>
            )}
          </section>
        )}

        {/* Preferencias de archivo (M4) */}
        <section className="rounded-2xl border border-gray-100 bg-white p-6">
          <div className="mb-1 flex items-center gap-2">
            <FileDown className="h-5 w-5 text-[#047857]" />
            <h2 className="text-sm font-semibold text-gray-900">Al hacer click en un archivo</h2>
          </div>
          <p className="mb-4 text-xs text-gray-500">
            Qué debe pasar por defecto cuando abras un documento de tus casos.
          </p>
          <div className="space-y-2">
            {OPCIONES.map((o) => (
              <button
                key={o.valor}
                onClick={() => guardarPref(o.valor)}
                className={`flex w-full items-start gap-3 rounded-xl border px-4 py-3 text-left transition ${
                  pref === o.valor
                    ? "border-[#047857]/40 bg-[#ecfdf5]"
                    : "border-gray-200 bg-white hover:border-gray-300"
                }`}
              >
                <span className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 ${pref === o.valor ? "border-[#047857]" : "border-gray-300"}`}>
                  {pref === o.valor && <span className="h-2 w-2 rounded-full bg-[#047857]" />}
                </span>
                <span>
                  <span className="block text-sm font-medium text-gray-900">{o.titulo}</span>
                  <span className="block text-xs text-gray-500">{o.desc}</span>
                </span>
              </button>
            ))}
          </div>
        </section>

        {/* Cerrar sesión */}
        <button
          onClick={salir}
          className="flex w-full items-center justify-center gap-2 rounded-2xl border border-red-200 bg-white px-4 py-3 text-sm font-semibold text-red-600 transition hover:bg-red-50"
        >
          <LogOut className="h-4 w-4" /> Cerrar sesión
        </button>
      </main>

      <SiteFooter />
    </div>
  );
}
