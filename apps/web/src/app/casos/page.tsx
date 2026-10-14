"use client";

/**
 * /casos — mis casos: propios + compartidos conmigo (parte o asesor).
 * La entrada del ciudadano B a un caso que A le compartió.
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Scale, FolderOpen, Share2, LogOut, Loader2, ArrowLeft } from "lucide-react";
import { useChatStore } from "@/lib/store";
import { authFetch } from "@/lib/auth";
import { SiteFooter } from "@/components/layout/SiteFooter";

interface CasoRow {
  id: string;
  materia: string | null;
  estado: string;
  nombre: string | null;
  created_at: string;
  propio: boolean;
  relacion?: string;
  rol?: string;
  etiqueta?: string | null;
  acceso_id?: number;
}

export default function CasosPage() {
  const router = useRouter();
  const sesion = useChatStore((s) => s.sesion);
  const iniciarSesion = useChatStore((s) => s.iniciarSesion);
  const [casos, setCasos] = useState<CasoRow[] | null>(null);

  useEffect(() => {
    if (!sesion) return;
    authFetch("/dossiers/mios")
      .then((r) => (r.ok ? r.json() : { casos: [] }))
      .then((d) => setCasos(d.casos ?? []))
      .catch(() => setCasos([]));
  }, [sesion]);

  const abrirCaso = (c: CasoRow) => {
    if (!sesion) return;
    // ver este dossier en el chat (propio o compartido conmigo)
    iniciarSesion({ ...sesion, dossierId: c.id, creadoEn: Date.now() });
    router.push("/chat");
  };

  const salirDelCaso = async (c: CasoRow) => {
    if (!confirm("¿Salir de este caso compartido? Tus aportes permanecen visibles a los participantes.")) return;
    await authFetch(`/dossiers/${c.id}/salir`, { method: "POST" }).catch(() => null);
    setCasos((prev) => prev?.filter((x) => x.id !== c.id) ?? null);
  };

  if (!sesion) {
    return (
      <div className="flex min-h-[100dvh] flex-col bg-white">
        <main className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[#047857]">
            <Scale className="h-6 w-6 text-white" />
          </div>
          <h1 className="text-lg font-bold text-gray-900">Entra para ver tus casos</h1>
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
          <div>
            <h1 className="text-sm font-bold text-gray-900">Mis casos</h1>
            <p className="text-[11px] text-gray-400">Propios y compartidos contigo</p>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-2xl flex-1 space-y-3 px-5 py-8">
        {casos === null ? (
          <p className="flex items-center justify-center gap-2 py-10 text-sm text-gray-400">
            <Loader2 className="h-4 w-4 animate-spin" /> Cargando…
          </p>
        ) : casos.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-gray-200 bg-white px-4 py-10 text-center text-sm text-gray-400">
            Aún no tienes casos. Inicia uno en el chat o acepta una invitación.
          </p>
        ) : (
          casos.map((c) => (
            <div key={c.id} className={`rounded-2xl border bg-white p-4 ${c.propio ? "border-gray-100" : "border-[#047857]/25"}`}>
              <div className="flex items-center gap-3">
                {c.propio
                  ? <FolderOpen className="h-5 w-5 shrink-0 text-gray-400" />
                  : <Share2 className="h-5 w-5 shrink-0 text-[#047857]" />}
                <button onClick={() => abrirCaso(c)} className="min-w-0 flex-1 text-left">
                  <span className="block truncate text-sm font-semibold text-gray-900">
                    {c.nombre || `Caso ${c.id.slice(0, 8)}`}
                  </span>
                  <span className="block text-[11px] text-gray-400">
                    {c.propio ? "Tu caso" : `Compartido contigo · ${c.relacion === "parte" ? "parte" : "asesor"} · ${c.rol}`}
                    {c.materia ? ` · ${c.materia}` : ""}
                  </span>
                </button>
                {!c.propio && (
                  <button
                    onClick={() => salirDelCaso(c)}
                    className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-[11px] text-gray-400 hover:bg-red-50 hover:text-red-600"
                    title="Salir de este caso compartido"
                  >
                    <LogOut className="h-3.5 w-3.5" /> salir
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </main>

      <SiteFooter />
    </div>
  );
}
