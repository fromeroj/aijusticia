"use client";

import { Fragment, useEffect, useState, useCallback } from "react";
import {
  Scale, RefreshCw, Activity, Database, AlertTriangle, CheckCircle,
  XCircle, HelpCircle, Play, ChevronDown, ChevronUp, MapPin, Clock,
  TrendingDown, TrendingUp, ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface SourceHealth {
  fuente: string;
  entidad: string;
  tipo: string;
  adapter_class: string;
  enabled: boolean;
  cron_expr: string;
  expected_min_results: number;
  last_run_at: string | null;
  last_success_at: string | null;
  consecutive_failures: number;
  consecutive_empty: number;
  health_status: string;
  watermark: string | null;
  total_documentos: number;
  portal_url: string | null;
  portal_verify_tls: boolean;
}

interface RunHistory {
  id: number;
  fuente: string;
  entidad: string;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  trigger: string;
  status: string;
  documentos_fetched: number;
  documentos_new: number;
  documentos_updated: number;
  documentos_errored: number;
  hash_changed: boolean;
  error_message: string | null;
}

interface FuenteStat {
  fuente: string;
  docs: number;
  tokens_m: number;
}

interface Stats {
  total_documentos: number;
  total_chunks: number;
  total_tokens: number;
  fuentes: FuenteStat[];
  sources_healthy: number;
  sources_degraded: number;
  sources_unhealthy: number;
  sources_unknown: number;
}

const healthConfig: Record<string, { color: string; bg: string; icon: typeof CheckCircle; label: string }> = {
  healthy: { color: "text-green-700", bg: "bg-green-100", icon: CheckCircle, label: "OK" },
  degraded: { color: "text-amber-700", bg: "bg-amber-100", icon: AlertTriangle, label: "Degradado" },
  unhealthy: { color: "text-red-700", bg: "bg-red-100", icon: XCircle, label: "Fallando" },
  unknown: { color: "text-gray-500", bg: "bg-gray-100", icon: HelpCircle, label: "Sin datos" },
};

// Umbral de cobertura: <50 es bajo, 50-100 medio, >100 bueno
function coverageLevel(docs: number): { label: string; color: string; bar: string } {
  if (docs >= 150) return { label: "Buena", color: "text-green-700", bar: "bg-green-500" };
  if (docs >= 50) return { label: "Media", color: "text-amber-700", bar: "bg-amber-500" };
  if (docs >= 10) return { label: "Baja", color: "text-orange-700", bar: "bg-orange-500" };
  return { label: "Crítica", color: "text-red-700", bar: "bg-red-500" };
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "nunca";
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "ahora";
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d`;
  return `${Math.floor(days / 30)}mes`;
}

type FilterMode = "all" | "estados" | "federales" | "problemas";

interface Harvester {
  fuente: string;
  nombre: string;
  descripcion: string | null;
  metodo: string | null;
  origen_url: string | null;
  ejecucion: string | null;
  diferencial: string | null;
  frecuencia: string | null;
  completa: boolean;
  estado: Record<string, unknown> | null;
  ultima_ejecucion: string | null;
}

export default function AdminPage() {
  const [sources, setSources] = useState<SourceHealth[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [runs, setRuns] = useState<RunHistory[]>([]);
  const [harvesters, setHarvesters] = useState<Harvester[]>([]);
  const [showHarvesters, setShowHarvesters] = useState(false);
  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  const [selectedEntidad, setSelectedEntidad] = useState<string>("Federal");
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [filter, setFilter] = useState<FilterMode>("all");
  const [search, setSearch] = useState("");

  const fetchSources = useCallback(async () => {
    try {
      const [srcRes, statsRes] = await Promise.all([
        fetch(`${API_URL}/admin/sources`),
        fetch(`${API_URL}/admin/stats`),
      ]);
      const srcData = await srcRes.json();
      const statsData = await statsRes.json();
      setSources(srcData.sources || []);
      setStats(statsData);
    } catch (e) {
      console.error("Error fetching sources:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchHarvesters = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/admin/harvesters`);
      const data = await res.json();
      setHarvesters(data.harvesters || []);
    } catch (e) {
      console.error("Error fetching harvesters:", e);
    }
  }, []);

  const fetchRuns = useCallback(async (fuente: string, entidad: string) => {
    try {
      const res = await fetch(`${API_URL}/admin/sources/${fuente}/runs?entidad=${entidad}&limit=30`);
      const data = await res.json();
      setRuns(data.runs || []);
    } catch (e) {
      console.error("Error fetching runs:", e);
    }
  }, []);

  useEffect(() => {
    fetchSources();
    fetchHarvesters();
    const interval = setInterval(fetchSources, 30000);
    return () => clearInterval(interval);
  }, [fetchSources, fetchHarvesters]);

  const handleSelectSource = (fuente: string, entidad: string) => {
    if (selectedSource === fuente && selectedEntidad === entidad) {
      setSelectedSource(null);
      setRuns([]);
    } else {
      setSelectedSource(fuente);
      setSelectedEntidad(entidad);
      fetchRuns(fuente, entidad);
    }
  };

  const handleTrigger = async (fuente: string, entidad: string) => {
    setTriggering(true);
    try {
      await fetch(`${API_URL}/admin/sources/${fuente}/trigger?entidad=${entidad}`, { method: "POST" });
      setTimeout(() => fetchSources(), 2000);
    } catch (e) {
      console.error("Error triggering:", e);
    } finally {
      setTriggering(false);
    }
  };

  const handleToggle = async (fuente: string, entidad: string, enabled: boolean) => {
    try {
      await fetch(`${API_URL}/admin/sources/${fuente}?entidad=${entidad}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !enabled }),
      });
      fetchSources();
    } catch (e) {
      console.error("Error toggling:", e);
    }
  };

  // Derivados
  const estados = sources.filter((s) => s.fuente === "GacetaEstatal");
  const federales = sources.filter((s) => s.fuente !== "GacetaEstatal");
  const estadosConDatos = estados.filter((s) => s.total_documentos > 0).length;
  const estadosBuenaCobertura = estados.filter((s) => s.total_documentos >= 150).length;
  const estadosCriticos = estados.filter((s) => s.total_documentos < 10);
  const totalDocsEstatales = estados.reduce((sum, s) => sum + s.total_documentos, 0);

  const filtered = sources.filter((s) => {
    if (search && !s.entidad.toLowerCase().includes(search.toLowerCase()) && !s.fuente.toLowerCase().includes(search.toLowerCase())) return false;
    switch (filter) {
      case "estados": return s.fuente === "GacetaEstatal";
      case "federales": return s.fuente !== "GacetaEstatal";
      case "problemas": return s.total_documentos < 50 || s.consecutive_failures > 0 || s.consecutive_empty > 0;
      default: return true;
    }
  });

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <RefreshCw className="h-8 w-8 animate-spin text-[#047857]" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-gray-200 bg-white px-4 py-3 shadow-sm sm:px-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#047857]">
              <Scale className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-gray-900">Panel de Datos</h1>
              <p className="hidden text-xs text-gray-400 sm:block">Captación y salud del corpus jurídico</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <a href="/" className="text-xs text-gray-400 hover:text-gray-600">← Inicio</a>
            <Button variant="outline" size="sm" onClick={fetchSources} className="gap-2">
              <RefreshCw className="h-4 w-4" />
              <span className="hidden sm:inline">Actualizar</span>
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 sm:py-6">
        {/* Stats Cards */}
        {stats && (
          <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <StatCard icon={Database} label="Documentos" value={stats.total_documentos.toLocaleString()} color="text-[#047857]" />
            <StatCard icon={Activity} label="Chunks" value={stats.total_chunks.toLocaleString()} color="text-blue-600" />
            <StatCard icon={TrendingUp} label="Tokens" value={`${(stats.total_tokens / 1e6).toFixed(0)}M`} color="text-purple-600" sub={`${stats.fuentes?.length || 0} fuentes`} />
            <StatCard icon={MapPin} label="Estados" value={`${estadosConDatos}/32`} color="text-indigo-600" sub={`${estadosBuenaCobertura} buena cobertura`} />
            <StatCard icon={AlertTriangle} label="Problemas" value={String(stats.sources_degraded + stats.sources_unhealthy)} color="text-amber-600" sub={`${stats.sources_healthy} OK`} />
          </div>
        )}

        {/* Alertas */}
        {estadosCriticos.length > 0 && (
          <div className="mb-5 rounded-xl border border-red-200 bg-red-50 p-4">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-red-800">
              <TrendingDown className="h-4 w-4" />
              {estadosCriticos.length} estados con cobertura crítica (&lt;10 leyes)
            </div>
            <div className="flex flex-wrap gap-2">
              {estadosCriticos.map((s) => (
                <span key={s.entidad} className="rounded-full bg-white px-3 py-1 text-xs text-red-700 shadow-sm">
                  <strong>{s.entidad}</strong>: {s.total_documentos} leyes · {s.health_status}
                  {s.portal_url && (
                    <a href={s.portal_url} target="_blank" rel="noopener noreferrer" className="ml-1 text-blue-500 hover:underline">
                      <ExternalLink className="inline h-3 w-3" />
                    </a>
                  )}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Filtros */}
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <div className="flex rounded-lg border border-gray-200 bg-white p-0.5">
            {([
              ["all", `Todas (${sources.length})`],
              ["estados", `Estados (${estados.length})`],
              ["federales", `Federales (${federales.length})`],
              ["problemas", "⚠️ Problemas"],
            ] as [FilterMode, string][]).map(([mode, label]) => (
              <button
                key={mode}
                onClick={() => setFilter(mode)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-xs font-medium transition",
                  filter === mode ? "bg-[#047857] text-white" : "text-gray-500 hover:text-gray-700",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <input
            type="text"
            placeholder="Buscar estado..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-700 placeholder:text-gray-300 focus:border-[#047857] focus:outline-none"
          />
          <span className="ml-auto flex items-center gap-1 text-xs text-gray-400">
            <Clock className="h-3.5 w-3.5" />
            Ingesta automática cada 6h
          </span>
        </div>

        {/* Harvesters — registro de cosecha diferencial */}
        <div className="mb-6 rounded-xl border border-gray-100 bg-gray-50/60 p-4">
          <button
            onClick={() => setShowHarvesters(!showHarvesters)}
            className="flex w-full items-center justify-between text-left"
          >
            <span className="text-sm font-semibold text-gray-800">
              Harvesters — {harvesters.length} fuentes registradas{" "}
              <span className="font-normal text-gray-400">
                (scripts + watermarks para recolección diferencial)
              </span>
            </span>
            <span className="text-xs text-[#047857]">{showHarvesters ? "ocultar ▲" : "ver ▼"}</span>
          </button>
          {showHarvesters && (
            <div className="mt-3 max-h-96 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="text-gray-400">
                  <tr>
                    <th className="px-2 py-1 text-left">Fuente</th>
                    <th className="px-2 py-1 text-left">Método</th>
                    <th className="px-2 py-1 text-left">Origen</th>
                    <th className="px-2 py-1 text-left">Corre en</th>
                    <th className="px-2 py-1 text-center">Completa</th>
                    <th className="px-2 py-1 text-left">Estado</th>
                    <th className="px-2 py-1 text-left">Diferencial</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 bg-white">
                  {harvesters.map((h) => (
                    <tr key={h.fuente} className="hover:bg-gray-50">
                      <td className="px-2 py-1.5">
                        <div className="font-medium text-gray-800">{h.fuente}</div>
                        <div className="text-[10px] text-gray-400">{h.nombre}</div>
                      </td>
                      <td className="px-2 py-1.5 text-gray-500">{h.metodo}</td>
                      <td className="max-w-[180px] truncate px-2 py-1.5">
                        <a href={h.origen_url || "#"} target="_blank" rel="noreferrer" className="text-[#047857] hover:underline">
                          {h.origen_url?.replace(/^https?:\/\//, "").slice(0, 34)}
                        </a>
                      </td>
                      <td className="px-2 py-1.5 text-gray-500">{h.ejecucion}</td>
                      <td className="px-2 py-1.5 text-center">
                        {h.completa ? <span className="text-green-600">✓</span> : <span className="text-amber-500">…</span>}
                      </td>
                      <td className="px-2 py-1.5 font-mono text-[10px] text-gray-500">
                        {h.estado && Object.keys(h.estado).length
                          ? Object.entries(h.estado).map(([k, v]) => `${k}=${String(v).slice(0, 12)}`).join(" ")
                          : "—"}
                      </td>
                      <td className="max-w-[220px] px-2 py-1.5 text-[10px] text-gray-400">{h.diferencial}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Sources Table */}
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-3 py-2 text-left">Entidad</th>
                  <th className="px-3 py-2 text-left">Salud</th>
                  <th className="px-3 py-2 text-left">Cobertura</th>
                  <th className="px-3 py-2 text-right">Leyes</th>
                  <th className="px-3 py-2 text-right">Charts</th>
                  <th className="px-3 py-2 text-center hidden md:table-cell">Adapter</th>
                  <th className="px-3 py-2 text-center hidden lg:table-cell">Portal</th>
                  <th className="px-3 py-2 text-center">Última</th>
                  <th className="px-3 py-2 text-center hidden sm:table-cell">Activa</th>
                  <th className="px-3 py-2 text-center">▶</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered
                  .sort((a, b) => {
                    // Federales primero, luego por docs desc
                    if (a.fuente !== "GacetaEstatal" && b.fuente === "GacetaEstatal") return -1;
                    if (a.fuente === "GacetaEstatal" && b.fuente !== "GacetaEstatal") return 1;
                    return b.total_documentos - a.total_documentos;
                  })
                  .map((s) => {
                    const cfg = healthConfig[s.health_status] || healthConfig.unknown;
                    const HealthIcon = cfg.icon;
                    const cov = coverageLevel(s.total_documentos);
                    const isSelected = selectedSource === s.fuente && selectedEntidad === s.entidad;
                    const maxEstatal = Math.max(...estados.map((e) => e.total_documentos), 1);
                    return (
                      <Fragment key={`${s.fuente}-${s.entidad}`}>
                        <tr
                          className={cn(
                            "cursor-pointer transition-colors hover:bg-gray-50",
                            isSelected && "bg-blue-50",
                          )}
                          onClick={() => handleSelectSource(s.fuente, s.entidad)}
                        >
                          <td className="px-3 py-2">
                            <div className="font-medium text-gray-800">{s.entidad}</div>
                            <div className="text-[10px] text-gray-400">{s.fuente}</div>
                          </td>
                          <td className="px-3 py-2">
                            <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium", cfg.bg, cfg.color)}>
                              <HealthIcon className="h-3 w-3" />
                              {cfg.label}
                            </span>
                          </td>
                          <td className="px-3 py-2">
                            <div className="flex items-center gap-2">
                              <div className="h-1.5 w-16 overflow-hidden rounded-full bg-gray-100 sm:w-24">
                                <div
                                  className={cn("h-full rounded-full", cov.bar)}
                                  style={{ width: s.fuente === "GacetaEstatal" ? `${Math.max((s.total_documentos / maxEstatal) * 100, 2)}%` : "100%" }}
                                />
                              </div>
                              <span className={cn("text-[10px] font-medium", cov.color)}>{cov.label}</span>
                            </div>
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-sm text-gray-800">
                            {s.total_documentos.toLocaleString()}
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-xs text-gray-400">
                            {s.watermark?.split("T")[0] || "—"}
                          </td>
                          <td className="px-3 py-2 text-center hidden md:table-cell">
                            <span className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[10px] text-gray-500">
                              {s.adapter_class}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-center hidden lg:table-cell">
                            {s.portal_url ? (
                              <a
                                href={s.portal_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-400 hover:text-blue-600"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <ExternalLink className="h-3.5 w-3.5" />
                              </a>
                            ) : (
                              <span className="text-gray-200">—</span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-center">
                            <span className="text-xs text-gray-500">{timeAgo(s.last_run_at)}</span>
                            {s.consecutive_empty > 0 && (
                              <span className="ml-0.5 text-[10px] text-amber-500"> ({s.consecutive_empty}○)</span>
                            )}
                            {s.consecutive_failures > 0 && (
                              <span className="ml-0.5 text-[10px] text-red-500"> ({s.consecutive_failures}✗)</span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-center hidden sm:table-cell">
                            <button
                              onClick={(e) => { e.stopPropagation(); handleToggle(s.fuente, s.entidad, s.enabled); }}
                              className={cn(
                                "relative h-5 w-9 rounded-full transition-colors",
                                s.enabled ? "bg-green-500" : "bg-gray-300",
                              )}
                            >
                              <span className={cn(
                                "absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform",
                                s.enabled ? "left-4" : "left-0.5",
                              )} />
                            </button>
                          </td>
                          <td className="px-3 py-2 text-center">
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-7 w-7 p-0"
                              disabled={!s.enabled || triggering}
                              onClick={(e) => { e.stopPropagation(); handleTrigger(s.fuente, s.entidad); }}
                            >
                              <Play className="h-3.5 w-3.5" />
                            </Button>
                          </td>
                        </tr>

                        {/* Expanded run history */}
                        {isSelected && (
                          <tr>
                            <td colSpan={10} className="bg-gray-50 px-4 py-3">
                              <div className="mb-2 flex items-center gap-2">
                                {isSelected ? <ChevronUp className="h-4 w-4 text-gray-400" /> : <ChevronDown className="h-4 w-4 text-gray-400" />}
                                <span className="text-xs font-semibold text-gray-500">
                                  Historial — {s.fuente}/{s.entidad}
                                </span>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="ml-auto h-6 gap-1 text-xs"
                                  onClick={() => fetchRuns(s.fuente, s.entidad)}
                                >
                                  <RefreshCw className="h-3 w-3" />
                                  Recargar
                                </Button>
                              </div>
                              {runs.length === 0 ? (
                                <p className="py-4 text-center text-xs text-gray-400">Sin ejecuciones registradas en este server</p>
                              ) : (
                                <div className="max-h-64 overflow-y-auto">
                                  <table className="w-full text-xs">
                                    <thead className="text-gray-400">
                                      <tr>
                                        <th className="px-2 py-1 text-left">#</th>
                                        <th className="px-2 py-1 text-left">Status</th>
                                        <th className="px-2 py-1 text-right">Fetched</th>
                                        <th className="px-2 py-1 text-right">Nuevos</th>
                                        <th className="px-2 py-1 text-right">Errores</th>
                                        <th className="px-2 py-1 text-left">Duración</th>
                                        <th className="px-2 py-1 text-left">Trigger</th>
                                        <th className="px-2 py-1 text-left">Fecha</th>
                                        <th className="px-2 py-1 text-left">Hash</th>
                                      </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-100">
                                      {runs.map((r) => (
                                        <tr key={r.id} className="hover:bg-white">
                                          <td className="px-2 py-1 text-gray-400">#{r.id}</td>
                                          <td className="px-2 py-1"><RunStatusBadge status={r.status} /></td>
                                          <td className="px-2 py-1 text-right font-mono">{r.documentos_fetched}</td>
                                          <td className="px-2 py-1 text-right font-mono text-green-600">{r.documentos_new || ""}</td>
                                          <td className="px-2 py-1 text-right font-mono text-red-500">{r.documentos_errored || ""}</td>
                                          <td className="px-2 py-1 text-gray-400">{r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : "—"}</td>
                                          <td className="px-2 py-1 text-gray-400">{r.trigger}</td>
                                          <td className="px-2 py-1 text-gray-400">{r.started_at?.split("T")[1]?.split(".")[0]}</td>
                                          <td className="px-2 py-1">
                                            {r.hash_changed ? <span className="text-amber-500">⚠️</span> : <span className="text-gray-300">ok</span>}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              )}
                              {runs[0]?.error_message && (
                                <div className="mt-2 rounded-lg bg-red-50 p-2 text-xs text-red-700">
                                  <strong>Error:</strong> {runs[0].error_message}
                                </div>
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Fuentes con tokens */}
        {stats?.fuentes && stats.fuentes.length > 0 && (
          <div className="mt-5 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
            <h2 className="mb-3 text-sm font-semibold text-gray-700">
              Corpus por fuente — {stats.fuentes.reduce((s, f) => s + f.docs, 0).toLocaleString()} docs · ~{stats.fuentes.reduce((s, f) => s + f.tokens_m, 0).toFixed(0)}M tokens
            </h2>
            <div className="space-y-1.5">
              {stats.fuentes.map((f) => {
                const maxTokens = Math.max(...stats.fuentes.map((x) => x.tokens_m), 1);
                const pct = (f.tokens_m / maxTokens) * 100;
                const colors: Record<string, string> = {
                  SJF: "bg-blue-500", GacetaEstatal: "bg-green-500", DOF: "bg-orange-500",
                  LeyesBiblio: "bg-purple-500", "SCJN-Libros": "bg-red-500", "CDMX-Doctrina": "bg-teal-500",
                };
                return (
                  <div key={f.fuente} className="flex items-center gap-3">
                    <span className="w-32 truncate text-xs font-medium text-gray-700">{f.fuente}</span>
                    <div className="h-4 flex-1 overflow-hidden rounded bg-gray-100">
                      <div
                        className={cn("h-full rounded transition-all", colors[f.fuente] || "bg-gray-400")}
                        style={{ width: `${Math.max(pct, 1)}%` }}
                      />
                    </div>
                    <span className="w-16 text-right font-mono text-xs text-gray-600">{f.docs.toLocaleString()} docs</span>
                    <span className="w-16 text-right font-mono text-xs text-purple-600">{f.tokens_m.toFixed(0)}M tok</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Coverage map — barras por estado */}
        <div className="mt-5 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="mb-3 text-sm font-semibold text-gray-700">Cobertura por estado (32 entidades)</h2>
          <div className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
            {estados
              .sort((a, b) => b.total_documentos - a.total_documentos)
              .map((s) => {
                const cov = coverageLevel(s.total_documentos);
                const pct = Math.min((s.total_documentos / 500) * 100, 100);
                return (
                  <div
                    key={s.entidad}
                    className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 transition hover:bg-gray-50"
                    onClick={() => handleSelectSource(s.fuente, s.entidad)}
                  >
                    <span className="w-28 truncate text-xs font-medium text-gray-700">{s.entidad}</span>
                    <div className="h-3 flex-1 overflow-hidden rounded-full bg-gray-100">
                      <div
                        className={cn("h-full rounded-full transition-all", cov.bar)}
                        style={{ width: `${Math.max(pct, 1)}%` }}
                      />
                    </div>
                    <span className="w-12 text-right font-mono text-xs text-gray-600">
                      {s.total_documentos.toLocaleString()}
                    </span>
                    <span className={cn("w-12 text-right text-[10px]", cov.color)}>{cov.label}</span>
                  </div>
                );
              })}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  icon: Icon, label, value, color, sub,
}: {
  icon: typeof Database; label: string; value: string; color: string; sub?: string;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
      <div className="flex items-center gap-2">
        <Icon className={cn("h-4 w-4", color)} />
        <span className="text-xs text-gray-500">{label}</span>
      </div>
      <div className={cn("mt-1 text-xl font-bold", color)}>{value}</div>
      {sub && <div className="mt-0.5 text-[10px] text-gray-400">{sub}</div>}
    </div>
  );
}

function RunStatusBadge({ status }: { status: string }) {
  const config: Record<string, string> = {
    success: "bg-green-100 text-green-700",
    partial: "bg-amber-100 text-amber-700",
    failed: "bg-red-100 text-red-700",
    empty_suspicious: "bg-orange-100 text-orange-700",
    running: "bg-blue-100 text-blue-700",
  };
  return (
    <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium", config[status] || "bg-gray-100 text-gray-500")}>
      {status}
    </span>
  );
}
