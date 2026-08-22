"use client";

import { Fragment, useEffect, useState, useCallback } from "react";
import { Scale, RefreshCw, Activity, Database, AlertTriangle, CheckCircle, XCircle, HelpCircle, Play, ChevronDown, ChevronUp } from "lucide-react";
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

interface Stats {
  total_documentos: number;
  total_chunks: number;
  sources_healthy: number;
  sources_degraded: number;
  sources_unhealthy: number;
  sources_unknown: number;
}

const healthConfig: Record<string, { color: string; bg: string; icon: typeof CheckCircle; label: string }> = {
  healthy: { color: "text-green-700", bg: "bg-green-100", icon: CheckCircle, label: "Saludable" },
  degraded: { color: "text-amber-700", bg: "bg-amber-100", icon: AlertTriangle, label: "Degradado" },
  unhealthy: { color: "text-red-700", bg: "bg-red-100", icon: XCircle, label: "Fallando" },
  unknown: { color: "text-gray-500", bg: "bg-gray-100", icon: HelpCircle, label: "Desconocido" },
};

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "nunca";
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "ahora";
  if (mins < 60) return `${mins}min`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}

export default function AdminPage() {
  const [sources, setSources] = useState<SourceHealth[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [runs, setRuns] = useState<RunHistory[]>([]);
  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  const [selectedEntidad, setSelectedEntidad] = useState<string>("Federal");
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);

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
    const interval = setInterval(fetchSources, 30000); // refresh every 30s
    return () => clearInterval(interval);
  }, [fetchSources]);

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
      <header className="sticky top-0 z-10 border-b border-gray-200 bg-white px-6 py-3 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#047857]">
              <Scale className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-gray-900">AI Justicia — Panel de Administración</h1>
              <p className="text-xs text-gray-400">Subsistema de Adquisición de Datos</p>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={fetchSources} className="gap-2">
            <RefreshCw className="h-4 w-4" />
            Actualizar
          </Button>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-6 py-6">
        {/* Stats Cards */}
        {stats && (
          <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4 lg:grid-cols-6">
            <StatCard icon={Database} label="Documentos" value={stats.total_documentos.toLocaleString()} color="text-[#047857]" />
            <StatCard icon={Activity} label="Chunks" value={stats.total_chunks.toLocaleString()} color="text-blue-600" />
            <StatCard icon={CheckCircle} label="Saludables" value={stats.sources_healthy} color="text-green-600" />
            <StatCard icon={AlertTriangle} label="Degradados" value={stats.sources_degraded} color="text-amber-600" />
            <StatCard icon={XCircle} label="Fallando" value={stats.sources_unhealthy} color="text-red-600" />
            <StatCard icon={HelpCircle} label="Sin datos" value={stats.sources_unknown} color="text-gray-400" />
          </div>
        )}

        {/* Sources Table */}
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-200 px-4 py-3">
            <h2 className="text-sm font-semibold text-gray-700">
              Fuentes del Corpus ({sources.length})
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-4 py-2 text-left">Estado</th>
                  <th className="px-4 py-2 text-left">Fuente</th>
                  <th className="px-4 py-2 text-left">Entidad</th>
                  <th className="px-4 py-2 text-left">Portal URL</th>
                  <th className="px-4 py-2 text-right">Docs</th>
                  <th className="px-4 py-2 text-left">Watermark</th>
                  <th className="px-4 py-2 text-left">Última ejecución</th>
                  <th className="px-4 py-2 text-center">Habilitada</th>
                  <th className="px-4 py-2 text-center">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {sources.map((s) => {
                  const cfg = healthConfig[s.health_status] || healthConfig.unknown;
                  const HealthIcon = cfg.icon;
                  const isSelected = selectedSource === s.fuente && selectedEntidad === s.entidad;
                  return (
                    <Fragment key={`${s.fuente}-${s.entidad}`}>
                      <tr
                        className={cn(
                          "cursor-pointer transition-colors hover:bg-gray-50",
                          isSelected && "bg-blue-50",
                        )}
                        onClick={() => handleSelectSource(s.fuente, s.entidad)}
                      >
                        <td className="px-4 py-2">
                          <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", cfg.bg, cfg.color)}>
                            <HealthIcon className="h-3 w-3" />
                            {cfg.label}
                          </span>
                        </td>
                        <td className="px-4 py-2 font-medium text-gray-700">{s.fuente}</td>
                        <td className="px-4 py-2 text-gray-600">{s.entidad}</td>
                        <td className="px-4 py-2 text-xs">
                          {s.portal_url ? (
                            <a
                              href={s.portal_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-blue-500 hover:underline"
                              onClick={(e) => e.stopPropagation()}
                              title={s.portal_url}
                            >
                              {s.portal_url.replace(/^https?:\/\//, "").split("/")[0]}
                            </a>
                          ) : (
                            <span className="text-gray-300">—</span>
                          )}
                        </td>
                        <td className="px-4 py-2 text-right font-mono text-gray-700">{s.total_documentos.toLocaleString()}</td>
                        <td className="px-4 py-2 text-xs text-gray-500">{s.watermark?.split("T")[0] || "—"}</td>
                        <td className="px-4 py-2 text-xs text-gray-500">
                          {timeAgo(s.last_run_at)}
                          {s.consecutive_empty > 0 && (
                            <span className="ml-1 text-red-500">({s.consecutive_empty}×empty)</span>
                          )}
                          {s.consecutive_failures > 0 && (
                            <span className="ml-1 text-red-500">({s.consecutive_failures}×fail)</span>
                          )}
                        </td>
                        <td className="px-4 py-2 text-center">
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
                        <td className="px-4 py-2 text-center">
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
                          <td colSpan={9} className="bg-gray-50 px-4 py-3">
                            <div className="mb-2 flex items-center gap-2">
                              {isSelected ? <ChevronUp className="h-4 w-4 text-gray-400" /> : <ChevronDown className="h-4 w-4 text-gray-400" />}
                              <span className="text-xs font-semibold text-gray-500">
                                Historial de ejecuciones — {s.fuente}/{s.entidad}
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
                              <p className="py-4 text-center text-xs text-gray-400">Sin ejecuciones registradas</p>
                            ) : (
                              <div className="max-h-64 overflow-y-auto">
                                <table className="w-full text-xs">
                                  <thead className="text-gray-400">
                                    <tr>
                                      <th className="px-2 py-1 text-left">#</th>
                                      <th className="px-2 py-1 text-left">Status</th>
                                      <th className="px-2 py-1 text-right">Fetched</th>
                                      <th className="px-2 py-1 text-right">Nuevos</th>
                                      <th className="px-2 py-1 text-right">Errors</th>
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
                                        <td className="px-2 py-1">
                                          <RunStatusBadge status={r.status} />
                                        </td>
                                        <td className="px-2 py-1 text-right font-mono">{r.documentos_fetched}</td>
                                        <td className="px-2 py-1 text-right font-mono text-green-600">{r.documentos_new || ""}</td>
                                        <td className="px-2 py-1 text-right font-mono text-red-500">{r.documentos_errored || ""}</td>
                                        <td className="px-2 py-1 text-gray-400">{r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : "—"}</td>
                                        <td className="px-2 py-1 text-gray-400">{r.trigger}</td>
                                        <td className="px-2 py-1 text-gray-400">{r.started_at?.split("T")[1]?.split(".")[0]}</td>
                                        <td className="px-2 py-1">
                                          {r.hash_changed ? <span className="text-amber-500">⚠️ cambió</span> : <span className="text-gray-300">ok</span>}
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

        {/* Bar chart: documentos por fuente */}
        <div className="mt-6 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="mb-3 text-sm font-semibold text-gray-700">Documentos por fuente</h2>
          <div className="space-y-2">
            {sources
              .filter((s) => s.total_documentos > 0)
              .sort((a, b) => b.total_documentos - a.total_documentos)
              .map((s) => {
                const max = Math.max(...sources.map((x) => x.total_documentos));
                const pct = (s.total_documentos / max) * 100;
                return (
                  <div key={`${s.fuente}-${s.entidad}`} className="flex items-center gap-3">
                    <span className="w-40 truncate text-xs text-gray-600">
                      {s.fuente}/{s.entidad}
                    </span>
                    <div className="h-5 flex-1 overflow-hidden rounded bg-gray-100">
                      <div
                        className="flex h-full items-center justify-end rounded bg-[#047857] px-2 text-[10px] font-medium text-white"
                        style={{ width: `${Math.max(pct, 2)}%` }}
                      >
                        {s.total_documentos.toLocaleString()}
                      </div>
                    </div>
                  </div>
                );
              })}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, color }: { icon: typeof Scale; label: string; value: string | number; color: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
      <div className="flex items-center gap-2">
        <Icon className={cn("h-4 w-4", color)} />
        <span className="text-xs text-gray-500">{label}</span>
      </div>
      <p className="mt-1 text-xl font-bold text-gray-900">{value}</p>
    </div>
  );
}

function RunStatusBadge({ status }: { status: string }) {
  const cfg: Record<string, string> = {
    success: "bg-green-100 text-green-700",
    partial: "bg-amber-100 text-amber-700",
    failed: "bg-red-100 text-red-700",
    empty_suspicious: "bg-orange-100 text-orange-700",
    running: "bg-blue-100 text-blue-700",
  };
  return (
    <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-medium", cfg[status] || "bg-gray-100 text-gray-500")}>
      {status}
    </span>
  );
}
