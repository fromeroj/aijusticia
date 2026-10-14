"use client";

/**
 * CasesPage — lista de casos + detalle con 6 tabs.
 * Conectada a la API real (/bufetes/casos, /practica/*).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, Ban, Check, ChevronRight, Circle, Clock3, Download, Loader2,
  Eye, FileText, FolderKanban, GitBranch, Lock, MessageSquarePlus,
  ScrollText, Search, Share2, ShieldAlert, Sparkles, UserPlus,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { DocsTab } from "@/components/studio/DocsTab";
import { useT } from "@/lib/i18n";

// ── types ──────────────────────────────────────────────────────────────────

interface Caso {
  id: string;
  nombre: string | null;
  materia: string | null;
  estado: string;
  confidencial?: boolean;
  origen?: string;
  rol_acceso?: string;
  creado: string;
}

interface DocItem {
  id: number; nombre: string; version: number; version_de: number | null; mensaje_cambio: string | null;
  metodo_texto: string | null; tamano_bytes: number; creado_en: string; length: number;
}
interface NotaItem {
  id: string; texto: string; creado_en: string; autor: string;
}
interface PlazoItem {
  id: string; titulo: string; fecha: string; fatal: boolean; tipo: string; cumplido: boolean;
}
interface TareaItem {
  id: string; titulo: string; vence: string | null; hecha: boolean; asignado: string;
}
interface TimelineItem {
  tipo: string; cuando: string; quien: string | null; detalle: string;
}
interface MiembroItem {
  actor_id: string; rol: string; nc_login: string | null; email: string | null;
}
interface AsignacionItem {
  id: string; actor_id: string; rol_en_caso: string; rol_firma: string;
}

// ── helpers ────────────────────────────────────────────────────────────────

const MATERIA_COLORS: Record<string, string> = {
  Civil: "bg-blue-500/10 text-blue-600",
  Mercantil: "bg-purple-500/10 text-purple-600",
  Laboral: "bg-amber-500/10 text-amber-600",
  Familiar: "bg-pink-500/10 text-pink-600",
  Penal: "bg-red-500/10 text-red-600",
  Amparo: "bg-teal-500/10 text-teal-600",
  Administrativo: "bg-cyan-500/10 text-cyan-600",
  Fiscal: "bg-green-500/10 text-green-600",
};

function MateriaBadge({ materia }: { materia: string | null }) {
  if (!materia) return null;
  return (
    <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold", MATERIA_COLORS[materia] ?? "bg-gray-500/10 text-gray-500")}>
      {materia}
    </span>
  );
}

function EstadoDot({ estado }: { estado: string }) {
  const colors: Record<string, string> = {
    activo: "bg-green-500", compartido: "bg-blue-500",
    concluido: "bg-gray-400", archivado: "bg-gray-300",
  };
  return (
    <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
      <span className={cn("size-1.5 rounded-full", colors[estado] ?? "bg-gray-400")} />
      {estado}
    </span>
  );
}

function fmtFecha(d: string | null | undefined): string {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("es-MX", { day: "numeric", month: "short", year: "2-digit" });
}

function fmtTamano(bytes: number | null | undefined): string {
  if (!bytes) return "0B";
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

// ── API helper ─────────────────────────────────────────────────────────────

function useApi() {
  return useCallback(async (path: string, init?: RequestInit) => {
    const raw = sessionStorage.getItem("aij_tokens");
    const tokens = raw ? JSON.parse(raw) : null;
    let access = tokens?.access;
    if (access) {
      try {
        const payload = JSON.parse(atob(access.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
        if ((payload.exp ?? 0) < Date.now() / 1000 + 5) {
          const rr = await fetch("/auth/token", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ via: "refresh", credential: tokens.refresh }),
          });
          if (rr.ok) {
            const d = await rr.json();
            sessionStorage.setItem("aij_tokens", JSON.stringify({ access: d.access_token, refresh: d.refresh_token }));
            access = d.access_token;
          }
        }
      } catch { /* usar token actual */ }
    }
    return fetch(path, {
      ...init,
      headers: { ...init?.headers, ...(access ? { Authorization: `Bearer ${access}` } : {}) },
    });
  }, []);
}

// ── main component ─────────────────────────────────────────────────────────

const TABS = ["timeline", "documentos", "notas", "plazos", "resumen", "equipo"] as const;
type Tab = (typeof TABS)[number];

export function CasesPage({ onCasoNombre, onCasoId }: { onCasoNombre?: (n: string | null) => void; onCasoId?: (id: string | null) => void }) {
  const t = useT();
  const api = useApi();
  const [casos, setCasos] = useState<Caso[]>([]);
  const [selId, setSelId] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [filtro, setFiltro] = useState<"todos" | "activos" | "confidenciales" | "compartidos">("todos");
  const [tab, setTab] = useState<Tab>("timeline");

  // datos del caso seleccionado
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [notas, setNotas] = useState<NotaItem[]>([]);
  const [plazos, setPlazos] = useState<PlazoItem[]>([]);
  const [tareas, setTareas] = useState<TareaItem[]>([]);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [miembros, setMiembros] = useState<MiembroItem[]>([]);
  const [asignaciones, setAsignaciones] = useState<AsignacionItem[]>([]);
  const [nuevaNota, setNuevaNota] = useState("");

  const sel = useMemo(() => casos.find((c) => c.id === selId) ?? null, [casos, selId]);

  const lista = useMemo(() => {
    const s = q.toLowerCase();
    return casos.filter((c) => {
      if (filtro === "activos" && c.estado !== "activo") return false;
      if (filtro === "confidenciales" && !c.confidencial) return false;
      if (filtro === "compartidos" && c.origen !== "compartido") return false;
      return !s || (c.nombre ?? "").toLowerCase().includes(s) || c.id.slice(0, 8).includes(s);
    });
  }, [casos, q, filtro]);

  const cargarCasos = useCallback(async () => {
    const r = await api("/bufetes/casos").catch(() => null);
    if (r?.ok) {
      const d = await r.json();
      setCasos(d.casos ?? []);
      if (d.casos?.length > 0 && !selId) setSelId(d.casos[0].id);
    }
  }, [api, selId]);

  useEffect(() => { cargarCasos(); }, [cargarCasos]);

  // cargar datos del caso seleccionado según el tab activo
  useEffect(() => {
    if (!selId) return;
    onCasoNombre?.(sel?.nombre ?? null);
    onCasoId?.(selId);
    const carga: Record<Tab, () => void> = {
      resumen: () => {},
      documentos: () => {
        api(`/bufetes/casos/${selId}/documentos`)
          .then((r) => r.ok ? r.json() : { documentos: [] })
          .then((d) => setDocs(d.documentos ?? [])).catch(() => setDocs([]));
      },
      notas: () => {
        api(`/bufetes/casos/${selId}/notas`)
          .then((r) => r.ok ? r.json() : { notas: [] })
          .then((d) => setNotas(d.notas ?? [])).catch(() => setNotas([]));
      },
      plazos: () => {
        api(`/practica/plazos?dossier_id=${selId}`)
          .then((r) => r.ok ? r.json() : { plazos: [] })
          .then((d) => setPlazos(d.plazos ?? [])).catch(() => setPlazos([]));
        api(`/practica/tareas?dossier_id=${selId}`)
          .then((r) => r.ok ? r.json() : { tareas: [] })
          .then((d) => setTareas(d.tareas ?? [])).catch(() => setTareas([]));
      },
      timeline: () => {
        api(`/bufetes/casos/${selId}/timeline`)
          .then((r) => r.ok ? r.json() : { eventos: [] })
          .then((d) => setTimeline(d.eventos ?? [])).catch(() => setTimeline([]));
      },
      equipo: () => {
        api("/bufetes/miembros")
          .then((r) => r.ok ? r.json() : { miembros: [] })
          .then((d) => setMiembros(d.miembros ?? [])).catch(() => setMiembros([]));
        api(`/dossiers/${selId}/equipo`)
          .then((r) => r.ok ? r.json() : { asignaciones: [] })
          .then((d) => setAsignaciones(d.asignaciones ?? [])).catch(() => setAsignaciones([]));
      },
    };
    carga[tab]();
  }, [selId, tab, api, sel, onCasoNombre]);

  const agregarNota = async () => {
    if (!selId || !nuevaNota.trim()) return;
    await api(`/bufetes/casos/${selId}/notas`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texto: nuevaNota.trim() }),
    }).catch(() => null);
    setNuevaNota("");
    api(`/bufetes/casos/${selId}/notas`)
      .then((r) => r.json()).then((d) => setNotas(d.notas ?? [])).catch(() => {});
  };

  return (
    <div className="flex h-full min-h-0">
      {/* ── lista ── */}
      <div className="flex w-[300px] shrink-0 flex-col border-r border-border bg-card/40">
        <div className="space-y-2 border-b border-border p-3">
          <div className="flex items-center gap-2 rounded-md border border-input bg-background px-2.5">
            <Search className="size-3.5 text-muted-foreground" />
            <input
              value={q} onChange={(e) => setQ(e.target.value)}
              placeholder={t("casos.buscar")}
              className="h-8 flex-1 bg-transparent text-[13px] outline-none placeholder:text-muted-foreground"
            />
          </div>
          <div className="flex flex-wrap gap-1">
            {(["todos", "activos", "confidenciales", "compartidos"] as const).map((f) => (
              <button key={f} onClick={() => setFiltro(f)}
                className={cn("rounded-full border px-2.5 py-1 text-[10px] uppercase tracking-wider transition-colors",
                  filtro === f ? "border-primary/40 bg-primary/10 text-primary" : "border-border text-muted-foreground hover:text-foreground")}>
                {t(`casos.${f}`)}
              </button>
            ))}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          {lista.map((c) => (
            <button key={c.id}
              onClick={() => setSelId(c.id)}
              className={cn("w-full border-b border-border px-4 py-3 text-left transition-colors",
                selId === c.id ? "bg-primary/[0.06]" : "hover:bg-accent/50")}>
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] tracking-wider text-muted-foreground">{c.id.slice(0, 8)}</span>
                {c.confidencial && <Lock className="size-3 text-amber-500" />}
                {c.origen === "compartido" && <Share2 className="size-3 text-teal-500" />}
                <span className="ml-auto"><EstadoDot estado={c.estado} /></span>
              </div>
              <p className={cn("mt-1 text-[13.5px] leading-snug", selId === c.id ? "font-semibold" : "font-medium")}>
                {c.nombre ?? `Caso ${c.id.slice(0, 8)}`}
              </p>
              <div className="mt-1.5 flex items-center gap-2">
                <MateriaBadge materia={c.materia} />
              </div>
            </button>
          ))}
          {lista.length === 0 && (
            <p className="px-4 py-10 text-center text-sm text-muted-foreground">{t("casos.sin_resultados")}</p>
          )}
        </div>
      </div>

      {/* ── detalle ── */}
      {sel ? (
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="border-b border-border px-6 py-4">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
              {sel.id.slice(0, 8)} · {fmtFecha(sel.creado)}
              {sel.confidencial && (
                <span className="flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-amber-600">
                  <Lock className="size-2.5" /> {t("casos.confidencial")}
                </span>
              )}
              {sel.origen === "compartido" && (
                <span className="flex items-center gap-1 rounded-full border border-teal-500/30 bg-teal-500/10 px-2 py-0.5 text-teal-600">
                  <Share2 className="size-2.5" /> compartido
                </span>
              )}
            </div>
            <div className="mt-1.5 flex items-start justify-between gap-4">
              <h2 className="text-[22px] font-semibold leading-tight tracking-tight">
                {sel.nombre ?? `Caso ${sel.id.slice(0, 8)}`}
              </h2>
              <div className="flex shrink-0 items-center gap-2">
                <MateriaBadge materia={sel.materia} />
              </div>
            </div>

            <div className="mt-3 flex gap-1">
              {TABS.map((tb) => (
                <button key={tb}
                  onClick={() => setTab(tb)}
                  className={cn("rounded-md px-3 py-1.5 text-[13px] transition-colors",
                    tab === tb ? "bg-primary/10 font-medium text-primary" : "text-muted-foreground hover:bg-accent hover:text-foreground")}>
                  {t(`tab.${tb}`)}
                  {tb === "documentos" && docs.length > 0 && <span className="ml-1 text-[10px] text-muted-foreground">{docs.length}</span>}
                  {tb === "notas" && notas.length > 0 && <span className="ml-1 text-[10px] text-muted-foreground">{notas.length}</span>}
                </button>
              ))}
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
            {tab === "resumen" && <TabResumen caso={sel} api={api} />}
            {tab === "documentos" && selId && <DocsTab docs={docs} api={api} selId={selId} />}
            {tab === "notas" && <TabNotas notas={notas} nuevaNota={nuevaNota} setNuevaNota={setNuevaNota} agregarNota={agregarNota} />}
            {tab === "plazos" && selId && <TabPlazos plazos={plazos} tareas={tareas} api={api} selId={selId} />}
            {tab === "timeline" && selId && <TabTimeline timeline={timeline} api={api} selId={selId} onNavigate={setTab} />}
            {tab === "equipo" && selId && <TabEquipo miembros={miembros} asignaciones={asignaciones} api={api} selId={selId} />}
          </div>
        </div>
      ) : (
        <div className="flex flex-1 items-center justify-center">
          <div className="text-center">
            <FolderKanban className="mx-auto size-8 text-muted-foreground/40" />
            <p className="mt-3 text-lg font-semibold">{t("casos.selecciona")}</p>
            <p className="mt-1 text-sm text-muted-foreground">{t("casos.expediente_vive")}</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Tab: Resumen ───────────────────────────────────────────────────────────

function TabResumen({ caso, api }: { caso: Caso; api: (p: string, i?: RequestInit) => Promise<Response> }) {
  const t = useT();
  const [genOpen, setGenOpen] = useState(false);
  return (
    <div className="max-w-4xl space-y-5">
      <div>
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t("resumen.etapa")}</p>
        <p className="text-lg font-medium tracking-tight">{caso.estado}</p>
      </div>
      <button
        onClick={() => setGenOpen(true)}
        className="flex items-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-3.5 py-2 text-[13px] font-medium text-primary hover:bg-primary/10"
      >
        <ScrollText className="size-4" /> {t("resumen.generar_doc")}
      </button>
      <GenerarDocDialog open={genOpen} onClose={() => setGenOpen(false)} caso={caso} api={api} />
    </div>
  );
}

function GenerarDocDialog({ open, onClose, caso, api }: {
  open: boolean; onClose: () => void; caso: Caso;
  api: (p: string, i?: RequestInit) => Promise<Response>;
}) {
  const t = useT();
  const [plantillas, setPlantillas] = useState<{ nombre: string; categoria: string }[]>([]);
  const [sel, setSel] = useState("");
  const [vars, setVars] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      api("/bufetes/plantillas")
        .then((r) => r.ok ? r.json() : { plantillas: [] })
        .then((d) => setPlantillas(d.plantillas ?? [])).catch(() => setPlantillas([]));
    }
  }, [open, api]);

  const detectarVars = async (ruta: string) => {
    setSel(ruta); setVars({}); setMsg(null);
    const r = await api(`/bufetes/plantillas/variables?nombre=${encodeURIComponent(ruta)}`).catch(() => null);
    if (r?.ok) {
      const d = await r.json();
      const ini: Record<string, string> = {};
      (d.variables ?? []).forEach((v: string) => (ini[v] = ""));
      setVars(ini);
    }
  };

  const generar = async () => {
    if (!sel) return;
    setMsg("Generando…");
    const r = await api("/bufetes/documentos/generar", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plantilla: sel, caso_id: caso.id, variables: vars }),
    }).catch(() => null);
    if (!r?.ok) { setMsg("Error al encolar"); return; }
    const { job_id } = await r.json();
    for (let i = 0; i < 40; i++) {
      await new Promise((res) => setTimeout(res, 1500));
      const jr = await api(`/bufetes/jobs/${job_id}`).catch(() => null);
      if (!jr?.ok) continue;
      const j = await jr.json();
      if (j.estado === "completado") {
        setMsg(`✓ ${j.resultado?.archivo} generado`);
        return;
      }
      if (j.estado === "fallido") { setMsg(`✗ ${j.error}`); return; }
    }
    setMsg("En proceso…");
  };

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl bg-background p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-4 text-[15px] font-semibold">{t("resumen.generar_doc")}</h3>
        <select value={sel} onChange={(e) => detectarVars(e.target.value)}
          className="mb-3 w-full rounded-lg border border-input bg-background px-3 py-2 text-[13px]">
          <option value="">Seleccionar plantilla…</option>
          {plantillas.map((p) => (
            <option key={p.nombre} value={p.categoria ? `${p.categoria}/${p.nombre}` : p.nombre}>
              {p.categoria ? `${p.categoria} · ${p.nombre}` : p.nombre}
            </option>
          ))}
        </select>
        {Object.keys(vars).length > 0 && (
          <div className="mb-3 max-h-40 space-y-1.5 overflow-y-auto rounded-lg bg-muted p-3">
            {Object.entries(vars).map(([k, v]) => (
              <div key={k} className="flex items-center gap-2">
                <span className="w-28 shrink-0 truncate font-mono text-[10px] text-muted-foreground">{k}</span>
                <input value={v} onChange={(e) => setVars({ ...vars, [k]: e.target.value })}
                  placeholder={k} className="flex-1 rounded border border-border bg-background px-2 py-1 text-xs" />
              </div>
            ))}
          </div>
        )}
        <button onClick={generar} disabled={!sel}
          className="w-full rounded-xl bg-primary py-2 text-[13px] font-semibold text-primary-foreground disabled:opacity-40">
          Generar
        </button>
        {msg && <p className="mt-2 rounded-lg bg-muted px-3 py-2 text-[12px] text-foreground">{msg}</p>}
      </div>
    </div>
  );
}

// ── Tab: Notas ────────────────────────────────────────────────────────────

function TabNotas({ notas, nuevaNota, setNuevaNota, agregarNota }: {
  notas: NotaItem[]; nuevaNota: string;
  setNuevaNota: (v: string) => void; agregarNota: () => void;
}) {
  const t = useT();
  return (
    <div className="max-w-3xl space-y-3">
      <div className="flex gap-2">
        <input value={nuevaNota} onChange={(e) => setNuevaNota(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") agregarNota(); }}
          placeholder={t("notas.placeholder")}
          className="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-[13px]" />
        <button onClick={agregarNota} disabled={!nuevaNota.trim()}
          className="rounded-lg bg-primary px-4 py-2 text-[12px] font-semibold text-primary-foreground disabled:opacity-40">
          {t("notas.anotar")}
        </button>
      </div>
      {notas.map((n) => (
        <div key={n.id} className="rounded-lg bg-amber-50/60 px-4 py-3 dark:bg-amber-950/20">
          <p className="whitespace-pre-wrap text-[13px] text-foreground">{n.texto}</p>
          <p className="mt-1 text-[10px] text-muted-foreground">{n.autor} · {fmtFecha(n.creado_en)}</p>
        </div>
      ))}
    </div>
  );
}

// ── Tab: Plazos y tareas ──────────────────────────────────────────────────

function TabPlazos({ plazos, tareas, api, selId }: {
  plazos: PlazoItem[]; tareas: TareaItem[];
  api: (p: string, i?: RequestInit) => Promise<Response>; selId: string;
}) {
  const t = useT();
  const toggleTarea = async (id: string) => {
    await api(`/practica/tareas/${id}/toggle`, { method: "POST" }).catch(() => null);
    window.location.reload();
  };
  return (
    <div className="max-w-3xl grid grid-cols-2 gap-6">
      <div>
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Plazos</p>
        {plazos.length === 0 && <p className="text-sm text-muted-foreground">{t("common.sin_datos")}</p>}
        {plazos.map((p) => (
          <div key={p.id} className={cn("mb-1.5 flex items-center gap-2 rounded-lg border px-3 py-2",
            p.fatal ? "border-red-500/30 bg-red-500/5" : "border-border")}>
            {p.fatal && <AlertTriangle className="size-3.5 text-red-500" />}
            <span className="min-w-0 flex-1 truncate text-[12.5px]">{p.titulo}</span>
            <span className="text-[10px] text-muted-foreground">{fmtFecha(p.fecha)}</span>
          </div>
        ))}
      </div>
      <div>
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Tareas</p>
        {tareas.length === 0 && <p className="text-sm text-muted-foreground">{t("common.sin_datos")}</p>}
        {tareas.map((t2) => (
          <button key={t2.id} onClick={() => toggleTarea(t2.id)}
            className="mb-1.5 flex w-full items-center gap-2 rounded-lg border border-border px-3 py-2 text-left hover:bg-accent/50">
            <span className={cn("size-3.5 shrink-0 rounded border", t2.hecha ? "border-primary bg-primary" : "border-input")} />
            <span className={cn("min-w-0 flex-1 truncate text-[12.5px]", t2.hecha && "line-through text-muted-foreground")}>{t2.titulo}</span>
            <span className="text-[10px] text-muted-foreground">{t2.asignado}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Tab: Timeline ─────────────────────────────────────────────────────────

const TIMELINE_ICONS: Record<string, any> = {
  caso_creado: FolderKanban, documento: FileText, nota: MessageSquarePlus,
  acceso_otorgado: Share2, acceso_revocado: Ban, asignacion: UserPlus,
};

function TabTimeline({ timeline, api, selId, onNavigate }: {
  timeline: TimelineItem[];
  api: (p: string, i?: RequestInit) => Promise<Response>;
  selId: string;
  onNavigate: (tab: Tab) => void;
}) {
  const [verDoc, setVerDoc] = useState<string | null>(null);

  const handleClick = async (e: TimelineItem) => {
    if (e.tipo === "documento") {
      // abrir el documento inline
      const docs = await api(`/bufetes/casos/${selId}/documentos`)
        .then((r) => r.ok ? r.json() : { documentos: [] })
        .then((d) => d.documentos ?? []).catch(() => []);
      const match = docs.find((d: any) => e.detalle.includes(d.nombre));
      if (match) {
        const r = await api(`/documentos/${match.id}/descargar`).catch(() => null);
        if (r?.ok) {
          const blob = await r.blob();
          window.open(URL.createObjectURL(blob), "_blank");
        }
      }
    } else if (e.tipo === "nota") {
      onNavigate("notas");
    } else if (e.tipo.startsWith("acceso") || e.tipo.startsWith("asignacion")) {
      onNavigate("equipo");
    } else if (e.tipo === "caso_creado") {
      onNavigate("resumen");
    }
  };

  const clickable = (e: TimelineItem) =>
    ["documento", "nota", "acceso_otorgado", "acceso_revocado", "asignacion", "caso_creado"].includes(e.tipo);

  return (
    <div className="max-w-3xl space-y-1">
      {timeline.map((e, i) => {
        const Icon = TIMELINE_ICONS[e.tipo] ?? Circle;
        const clic = clickable(e);
        return (
          <button
            key={i}
            onClick={() => clic && handleClick(e)}
            className={cn(
              "flex w-full gap-3 rounded-lg border border-border px-4 py-2.5 text-left",
              clic ? "cursor-pointer transition-colors hover:border-primary/40 hover:bg-primary/[0.04]" : "cursor-default"
            )}
            title={clic ? "Click para abrir" : ""}
          >
            <Icon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[12.5px] text-foreground">{e.detalle}</p>
              <p className="text-[10px] text-muted-foreground">
                {fmtFecha(e.cuando)}{e.quien ? ` · ${e.quien}` : ""} · {e.tipo.replace("_", " ")}
              </p>
            </div>
            {clic && <ChevronRight className="mt-0.5 size-3.5 shrink-0 text-muted-foreground/50" />}
          </button>
        );
      })}
      {timeline.length === 0 && <p className="text-sm text-muted-foreground">—</p>}
    </div>
  );
}

// ── Tab: Equipo ───────────────────────────────────────────────────────────

function TabEquipo({ miembros, asignaciones, api, selId }: {
  miembros: MiembroItem[]; asignaciones: AsignacionItem[];
  api: (p: string, i?: RequestInit) => Promise<Response>; selId: string;
}) {
  const t = useT();
  const [asignarA, setAsignarA] = useState("");
  const [asignarRol, setAsignarRol] = useState("abogado");

  const asignar = async () => {
    if (!asignarA) return;
    await api(`/bufetes/casos/${selId}/asignaciones`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor_id: asignarA, rol_en_caso: asignarRol }),
    }).catch(() => null);
    setAsignarA("");
    window.location.reload();
  };

  return (
    <div className="max-w-3xl space-y-3">
      {asignaciones.length === 0 && <p className="text-sm text-muted-foreground">{t("common.sin_datos")}</p>}
      {asignaciones.map((a) => {
        const m = miembros.find((x) => x.actor_id === a.actor_id);
        return (
          <div key={a.id} className="flex items-center gap-3 rounded-lg border border-border px-4 py-2.5">
            <span className="min-w-0 flex-1">
              <span className="block text-[13px] text-foreground">{m?.nc_login || m?.email || a.actor_id.slice(0, 8)}</span>
              <span className="text-[10px] text-muted-foreground">{a.rol_en_caso} · {a.rol_firma}</span>
            </span>
          </div>
        );
      })}
      <div className="flex gap-2 border-t border-border pt-3">
        <select value={asignarA} onChange={(e) => setAsignarA(e.target.value)}
          className="min-w-0 flex-1 rounded-lg border border-border px-2 py-1.5 text-[12px]">
          <option value="">{t("equipo.asignar")}</option>
          {miembros.map((m) => (
            <option key={m.actor_id} value={m.actor_id}>
              {m.nc_login || m.email || m.actor_id.slice(0, 8)} ({m.rol})
            </option>
          ))}
        </select>
        <select value={asignarRol} onChange={(e) => setAsignarRol(e.target.value)}
          className="w-28 rounded-lg border border-border px-2 py-1.5 text-[12px]">
          <option value="responsable">responsable</option>
          <option value="abogado">abogado</option>
          <option value="pasante">pasante</option>
        </select>
        <button onClick={asignar} disabled={!asignarA}
          className="rounded-lg bg-primary/10 px-3 py-1.5 text-[12px] font-semibold text-primary disabled:opacity-40">
          <UserPlus className="size-3.5" />
        </button>
      </div>
    </div>
  );
}
