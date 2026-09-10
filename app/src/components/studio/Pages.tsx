"use client";

/**
 * Páginas del Studio: Dashboard, Clients, Library, Agenda, Conflicts, Settings.
 */
import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle, CalendarClock, Check, Clock3, FileText, FolderKanban,
  Library, Plus, ShieldCheck, Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n";

function useApi() {
  return useCallback(async (path: string, init?: RequestInit) => {
    const raw = sessionStorage.getItem("aij_tokens");
    const tokens = raw ? JSON.parse(raw) : null;
    return fetch(path, {
      ...init,
      headers: { ...init?.headers, ...(tokens?.access ? { Authorization: `Bearer ${tokens.access}` } : {}) },
    });
  }, []);
}

// ── Dashboard ──────────────────────────────────────────────────────────────

export function DashboardPage({ onNavigate }: { onNavigate?: (p: string) => void } = {}) {
  const t = useT();
  const api = useApi();
  const [stats, setStats] = useState<Record<string, number>>({});
  const [plazos, setPlazos] = useState<{ titulo: string; fecha: string; fatal: boolean; caso_nombre: string | null }[]>([]);

  useEffect(() => {
    api("/practica/dashboard").then((r) => r.ok ? r.json() : {}).then(setStats).catch(() => {});
    api("/practica/plazos?proximos=14").then((r) => r.ok ? r.json() : { plazos: [] })
      .then((d) => setPlazos(d.plazos ?? [])).catch(() => setPlazos([]));
  }, [api]);

  const cards = [
    { label: t("dash.casos_activos"), value: stats.casos ?? 0, icon: FolderKanban },
    { label: t("dash.plazos_semana"), value: stats.plazos_semana ?? 0, icon: CalendarClock },
    { label: t("dash.tareas_pend"), value: stats.tareas_pendientes ?? 0, icon: Check },
    { label: t("dash.clientes"), value: stats.clientes ?? 0, icon: Users },
  ];

  return (
    <div className="space-y-6 p-6">
      <div className="grid grid-cols-4 gap-4">
        {cards.map((c, i) => (
          <button
            key={c.label}
            onClick={() => onNavigate?.(["casos", "agenda", "casos", "clientes"][i])}
            className="rounded-xl border border-border bg-card p-4 text-left transition-colors hover:border-primary/40 hover:bg-primary/[0.03] cursor-pointer"
          >
            <div className="flex items-center gap-2 text-muted-foreground">
              <c.icon className="size-4" />
              <span className="text-[11px] font-medium uppercase tracking-wider">{c.label}</span>
            </div>
            <p className="mt-2 text-2xl font-semibold tracking-tight">{c.value}</p>
          </button>
        ))}
      </div>
      <div>
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          {t("dash.proximos")}
        </p>
        {plazos.length === 0 && <p className="text-sm text-muted-foreground">{t("common.sin_datos")}</p>}
        {plazos.map((p, i) => (
          <div key={i} className={cn("mb-1.5 flex items-center gap-3 rounded-lg border px-4 py-2.5",
            p.fatal ? "border-red-500/30 bg-red-500/5" : "border-border")}>
            {p.fatal && <AlertTriangle className="size-4 text-red-500" />}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px]">{p.titulo}</span>
              <span className="text-[10px] text-muted-foreground">{p.caso_nombre}</span>
            </span>
            <span className="text-[11px] text-muted-foreground">
              {new Date(p.fecha).toLocaleDateString("es-MX", { day: "numeric", month: "short" })}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Clientes ───────────────────────────────────────────────────────────────

export function ClientsPage() {
  const t = useT();
  const api = useApi();
  const [clientes, setClientes] = useState<{ id: string; nombre: string; tipo: string; email: string | null; telefono: string | null }[]>([]);
  const [nuevo, setNuevo] = useState("");

  useEffect(() => {
    api("/practica/clientes").then((r) => r.ok ? r.json() : { clientes: [] })
      .then((d) => setClientes(d.clientes ?? [])).catch(() => setClientes([]));
  }, [api]);

  const crear = async () => {
    if (!nuevo.trim()) return;
    await api("/practica/clientes", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nombre: nuevo.trim() }),
    }).catch(() => null);
    setNuevo("");
    api("/practica/clientes").then((r) => r.json()).then((d) => setClientes(d.clientes ?? []));
  };

  return (
    <div className="max-w-4xl space-y-4 p-6">
      <div className="flex gap-2">
        <input value={nuevo} onChange={(e) => setNuevo(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") crear(); }}
          placeholder="Nombre del cliente…"
          className="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-[13px]" />
        <button onClick={crear} disabled={!nuevo.trim()}
          className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-[12px] font-semibold text-primary-foreground disabled:opacity-40">
          <Plus className="size-3.5" /> {t("common.crear")}
        </button>
      </div>
      {clientes.map((c) => (
        <div key={c.id} className="flex items-center gap-3 rounded-lg border border-border px-4 py-3">
          <Users className="size-4 text-muted-foreground" />
          <span className="min-w-0 flex-1">
            <span className="block text-[13px]">{c.nombre}</span>
            <span className="text-[10px] text-muted-foreground">{c.tipo} {c.email ? `· ${c.email}` : ""}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

// ── Biblioteca ─────────────────────────────────────────────────────────────

export function LibraryPage() {
  const t = useT();
  const api = useApi();
  const [plantillas, setPlantillas] = useState<{ nombre: string; categoria: string }[]>([]);

  useEffect(() => {
    api("/bufetes/plantillas").then((r) => r.ok ? r.json() : { plantillas: [] })
      .then((d) => setPlantillas(d.plantillas ?? [])).catch(() => setPlantillas([]));
  }, [api]);

  return (
    <div className="max-w-4xl space-y-2 p-6">
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Plantillas</p>
      {plantillas.map((p) => (
        <div key={p.nombre} className="flex items-center gap-3 rounded-lg border border-border px-4 py-2.5">
          <FileText className="size-4 text-muted-foreground" />
          <span className="min-w-0 flex-1 truncate text-[13px]">{p.nombre}</span>
          <span className="text-[10px] text-muted-foreground">{p.categoria}</span>
        </div>
      ))}
      {plantillas.length === 0 && <p className="text-sm text-muted-foreground">{t("common.sin_datos")}</p>}
    </div>
  );
}

// ── Agenda ─────────────────────────────────────────────────────────────────

export function AgendaPage() {
  const t = useT();
  const api = useApi();
  const [plazos, setPlazos] = useState<{ id: string; titulo: string; fecha: string; fatal: boolean; tipo: string; caso_nombre: string | null }[]>([]);
  const [nuevoOpen, setNuevoOpen] = useState(false);

  const cargar = useCallback(() => {
    api("/practica/plazos?proximos=30").then((r) => r.ok ? r.json() : { plazos: [] })
      .then((d) => setPlazos(d.plazos ?? [])).catch(() => setPlazos([]));
  }, [api]);

  useEffect(() => { cargar(); }, [cargar]);

  return (
    <div className="max-w-3xl space-y-2 p-6">
      <div className="mb-3 flex justify-end">
        <button onClick={() => setNuevoOpen(true)}
          className="flex items-center gap-1.5 rounded-lg bg-primary/10 px-3 py-2 text-[12px] font-semibold text-primary hover:bg-primary/20">
          <Plus className="size-3.5" /> Nuevo plazo
        </button>
      </div>
      {plazos.length === 0 && <p className="text-sm text-muted-foreground">{t("common.sin_datos")}</p>}
      {plazos.map((p) => (
        <div key={p.id} className={cn("flex items-center gap-3 rounded-lg border px-4 py-3",
          p.fatal ? "border-red-500/30 bg-red-500/5" : "border-border")}>
          <CalendarClock className={cn("size-4", p.fatal ? "text-red-500" : "text-muted-foreground")} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13px]">{p.titulo}</span>
            <span className="text-[10px] text-muted-foreground">{p.caso_nombre} · {p.tipo}</span>
          </span>
          <span className="text-[11px] text-muted-foreground">
            {new Date(p.fecha).toLocaleDateString("es-MX", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
          </span>
        </div>
      ))}
      {nuevoOpen && <NuevoPlazoDialog onClose={() => { setNuevoOpen(false); cargar(); }} api={api} />}
    </div>
  );
}

// ── Conflictos ─────────────────────────────────────────────────────────────

export function ConflictsPage() {
  const t = useT();
  return (
    <div className="max-w-3xl p-6">
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-2">
          <ShieldCheck className="size-5 text-primary" />
          <h3 className="text-[15px] font-semibold">{t("nav.conflictos")}</h3>
        </div>
        <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">
          El muro ético bloquea a un miembro de ver o ser asignado a un caso específico cuando
          existe conflicto de interés. El veto prevalece sobre cualquier asignación o acceso.
          Se gestiona desde el tab "Equipo" de cada caso.
        </p>
      </div>
    </div>
  );
}

// ── Settings (placeholder) ────────────────────────────────────────────────

export function SettingsPage() {
  const t = useT();
  return (
    <div className="max-w-3xl p-6">
      <div className="rounded-xl border border-border bg-card p-6">
        <h3 className="text-[15px] font-semibold">{t("nav.ajustes")}</h3>
        <p className="mt-2 text-[13px] text-muted-foreground">Próximamente.</p>
      </div>
    </div>
  );
}

function NuevoPlazoDialog({ onClose, api }: {
  onClose: () => void; api: (p: string, i?: RequestInit) => Promise<Response>;
}) {
  const t = useT();
  const [casos, setCasos] = useState<{ id: string; nombre: string | null }[]>([]);
  const [selCaso, setSelCaso] = useState("");
  const [titulo, setTitulo] = useState("");
  const [fecha, setFecha] = useState("");
  const [fatal, setFatal] = useState(false);

  useEffect(() => {
    api("/bufetes/casos").then((r) => r.ok ? r.json() : { casos: [] })
      .then((d) => setCasos(d.casos ?? [])).catch(() => setCasos([]));
  }, [api]);

  const crear = async () => {
    if (!selCaso || !titulo.trim() || !fecha) return;
    await api("/practica/plazos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dossier_id: selCaso, titulo: titulo.trim(), fecha, fatal }),
    }).catch(() => null);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-full max-w-sm rounded-2xl bg-background p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-4 text-[15px] font-semibold">{t("casos.nuevo")} plazo</h3>
        <select value={selCaso} onChange={(e) => setSelCaso(e.target.value)}
          className="mb-3 w-full rounded-lg border border-input bg-background px-3 py-2 text-[13px]">
          <option value="">Caso…</option>
          {casos.map((c) => <option key={c.id} value={c.id}>{c.nombre ?? c.id.slice(0, 8)}</option>)}
        </select>
        <input value={titulo} onChange={(e) => setTitulo(e.target.value)}
          placeholder="Título del plazo"
          className="mb-3 w-full rounded-lg border border-input bg-background px-3 py-2 text-[13px]" />
        <input type="datetime-local" value={fecha} onChange={(e) => setFecha(e.target.value)}
          className="mb-3 w-full rounded-lg border border-input bg-background px-3 py-2 text-[13px]" />
        <label className="mb-4 flex items-center gap-2 text-[12px]">
          <input type="checkbox" checked={fatal} onChange={(e) => setFatal(e.target.checked)} />
          Plazo fatal
        </label>
        <button onClick={crear} disabled={!selCaso || !titulo.trim() || !fecha}
          className="w-full rounded-xl bg-primary py-2.5 text-[13px] font-semibold text-primary-foreground disabled:opacity-40">
          {t("common.crear")}
        </button>
      </div>
    </div>
  );
}
