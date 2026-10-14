"use client";

/**
 * DocsTab — documentos del caso agrupados por documento raíz.
 * Solo muestra la versión MÁS RECIENTE de cada documento.
 * Las versiones anteriores se expanden con un timeline.
 */

import { useMemo, useRef, useState } from "react";
import {
  Check, ChevronDown, ChevronRight, Clock, Download, Eye,
  FileText, GitBranch, Loader2, Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Upload } from "lucide-react";
import { useT } from "@/lib/i18n";

export interface DocItem {
  id: number;
  nombre: string;
  version: number;
  version_de: number | null;
  metodo_texto: string | null;
  tamano_bytes: number;
  creado_en: string;
  mensaje_cambio: string | null;
  length: number;
}

interface GrupoDoc {
  raiz: DocItem;
  versiones: DocItem[]; // todas, ordenadas por fecha DESC
  actual: DocItem; // la más reciente
}

function agrupar(docs: DocItem[]): GrupoDoc[] {
  const porId = new Map<number, DocItem>();
  docs.forEach((d) => porId.set(d.id, d));

  const grupos: GrupoDoc[] = [];
  const visitados = new Set<number>();

  // encontrar raíces (sin version_de) y agrupar
  for (const d of docs) {
    if (d.version_de === null && !visitados.has(d.id)) {
      visitados.add(d.id);
      const versiones = [d];
      // buscar todas las versiones descendientes (1 nivel)
      for (const v of docs) {
        if (v.version_de === d.id && !visitados.has(v.id)) {
          visitados.add(v.id);
          versiones.push(v);
        }
        // también versiones de versiones (v2 de v2 = v3)
        if (v.version_de !== null && porId.has(v.version_de)) {
          const padre = porId.get(v.version_de)!;
          if (padre.version_de === d.id && !visitados.has(v.id)) {
            visitados.add(v.id);
            versiones.push(v);
          }
        }
      }
      versiones.sort((a, b) => new Date(b.creado_en).getTime() - new Date(a.creado_en).getTime());
      grupos.push({ raiz: d, versiones, actual: versiones[0] });
    }
  }
  // docs huérfanos (version_de apunta a un doc que no existe en la lista)
  for (const d of docs) {
    if (!visitados.has(d.id)) {
      visitados.add(d.id);
      grupos.push({ raiz: d, versiones: [d], actual: d });
    }
  }
  grupos.sort((a, b) =>
    new Date(b.actual.creado_en).getTime() - new Date(a.actual.creado_en).getTime());
  return grupos;
}

function fmtFecha(d: string): string {
  return new Date(d).toLocaleDateString("es-MX", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function fmtTamano(bytes: number): string {
  if (!bytes) return "0B";
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

const ORIGEN_LABEL: Record<string, string> = {
  izel: "Izel",
  _izel: "Izel",
};

function etiquetaOrigen(nombre: string): string | null {
  if (nombre.includes("_izel")) return "Izel";
  return null;
}

export function DocsTab({ docs, api, selId }: {
  docs: DocItem[];
  api: (p: string, i?: RequestInit) => Promise<Response>;
  selId: string;
}) {
  const t = useT();
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [abriendo, setAbriendo] = useState<number | null>(null);
  const [revisar, setRevisar] = useState<{ docId: number; nombre: string; consulta: string } | null>(null);
  const [revisando, setRevisando] = useState(false);
  const [revisionResultado, setRevisionResultado] = useState<{ archivo: string; cambios: string } | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [versionDe, setVersionDe] = useState<number | null>(null);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const subirArchivo = async (file: File) => {
    if (!selId) return;
    setSubiendo(true);
    setUploadMsg(null);
    try {
      const form = new FormData();
      form.append("archivo", file);
      if (versionDe) form.append("version_de", String(versionDe));
      const r = await api(`/dossiers/${selId}/documentos`, { method: "POST", body: form });
      if (r.ok) {
        const d = await r.json();
        setUploadMsg(`✓ ${d.nombre} subido${versionDe ? ` como v${d.version}` : ""}`);
        window.location.reload();
      } else {
        const err = await r.json().catch(() => ({}));
        setUploadMsg(`✗ ${err.detail || "Error al subir"}`);
      }
    } catch {
      setUploadMsg("✗ Error de conexión");
    } finally {
      setSubiendo(false);
      setVersionDe(null);
    }
  };

  const grupos = useMemo(() => agrupar(docs), [docs]);

  const descargar = async (d: DocItem) => {
    const r = await api(`/documentos/${d.id}/descargar`).catch(() => null);
    if (!r?.ok) return;
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = d.nombre; a.click();
    URL.revokeObjectURL(url);
  };

  const abrirEditor = async (d: DocItem) => {
    setAbriendo(d.id);
    try {
      const r = await api(`/bufetes/casos/${selId}/documentos/${d.id}/abrir`, { method: "POST" });
      if (r.ok) {
        const data = await r.json();
        const a = document.createElement("a");
        a.href = data.editor_url || data.nc_url;
        a.target = "_blank";
        a.rel = "noopener";
        document.body.appendChild(a);
        a.click();
        a.remove();
      }
    } finally { setAbriendo(null); }
  };

  const verInline = async (d: DocItem) => {
    const r = await api(`/documentos/${d.id}/descargar`).catch(() => null);
    if (!r?.ok) return;
    const blob = await r.blob();
    window.open(URL.createObjectURL(blob), "_blank");
  };

  const enviarRevision = async () => {
    if (!revisar || !revisar.consulta.trim()) return;
    setRevisando(true); setRevisionResultado(null);
    try {
      const r = await api(`/bufetes/casos/${selId}/documentos/${revisar.docId}/revisar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ caso_id: selId, documento_id: revisar.docId, consulta: revisar.consulta.trim() }),
      });
      if (r.ok) {
        const d = await r.json();
        setRevisionResultado({ archivo: d.archivo, cambios: d.cambios || "(sin cambios)" });
      } else {
        const d = await r.json().catch(() => ({}));
        setRevisionResultado({ archivo: "ERROR", cambios: d.detail || "Error" });
      }
    } catch {
      setRevisionResultado({ archivo: "ERROR", cambios: "Error de conexión" });
    } finally { setRevisando(false); }
  };

  const toggleExpand = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  if (docs.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("resumen.sin_docs")}</p>;
  }

  return (
    <div className="max-w-3xl space-y-3">
      {/* barra de subida */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => { setVersionDe(null); fileRef.current?.click(); }}
          disabled={subiendo}
          className="flex items-center gap-1.5 rounded-lg bg-primary/10 px-3 py-2 text-[12px] font-semibold text-primary hover:bg-primary/20 disabled:opacity-40"
        >
          {subiendo ? <Loader2 className="size-3.5 animate-spin" /> : <Upload className="size-3.5" />}
          Subir documento
        </button>
        <input ref={fileRef} type="file" className="hidden" accept=".pdf,.docx,.jpg,.jpeg,.png,.tif,.tiff,.webp"
          onChange={(e) => { if (e.target.files?.[0]) subirArchivo(e.target.files[0]); }} />
        {uploadMsg && <span className={cn("text-[11px]", uploadMsg.startsWith("✓") ? "text-teal-600" : "text-red-500")}>{uploadMsg}</span>}
      </div>
      {grupos.map((g) => {
        const estaExpandido = expanded.has(g.raiz.id);
        const tieneHistorial = g.versiones.length > 1;
        return (
          <div key={g.raiz.id} className="rounded-xl border border-border">
            {/* versión ACTUAL */}
            <div className="flex items-center gap-3 px-4 py-3">
              <FileText className="size-5 shrink-0 text-primary" />
              <button onClick={() => verInline(g.actual)} className="min-w-0 flex-1 text-left" title="Ver">
                <span className="block truncate text-[14px] font-medium text-foreground hover:text-primary">
                  {g.actual.nombre.replace(/_izel\.docx$/, ".docx")}
                </span>
                <span className="flex items-center gap-2 text-[10px] text-muted-foreground">
                  <span className="rounded-full bg-primary/10 px-1.5 py-0.5 font-semibold text-primary">actual</span>
                  {tieneHistorial && <span>v{g.actual.version}</span>}
                  <span>{fmtTamano(g.actual.tamano_bytes)}</span>
                  {g.actual.metodo_texto === "docx_comentarios" && <span className="text-teal-500">con comentarios</span>}
                  <span>{fmtFecha(g.actual.creado_en)}</span>
                  {etiquetaOrigen(g.actual.nombre) && (
                    <span className="flex items-center gap-0.5 text-teal-500">
                      <Sparkles className="size-2.5" /> {etiquetaOrigen(g.actual.nombre)}
                    </span>
                  )}
                </span>
              </button>
              {g.actual.nombre.toLowerCase().endsWith(".docx") && (
                <>
                  <button onClick={() => abrirEditor(g.actual)} disabled={abriendo === g.actual.id}
                    className="flex items-center gap-1 rounded-md bg-primary/10 px-2.5 py-1.5 text-[10px] font-semibold text-primary hover:bg-primary/20 disabled:opacity-40">
                    {abriendo === g.actual.id ? <Loader2 className="size-3 animate-spin" /> : <Eye className="size-3" />} editar
                  </button>
                  <button onClick={() => setRevisar({ docId: g.actual.id, nombre: g.actual.nombre, consulta: "" })}
                    className="flex items-center gap-1 rounded-md bg-teal-500/10 px-2.5 py-1.5 text-[10px] font-semibold text-teal-600 hover:bg-teal-500/20 dark:text-teal-400">
                    <Sparkles className="size-3" /> Izel
                  </button>
                </>
              )}
              <button onClick={() => descargar(g.actual)}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground" title="Descargar">
                <Download className="size-3.5" />
              </button>
              <button
                onClick={() => { setVersionDe(g.actual.id); fileRef.current?.click(); }}
                disabled={subiendo}
                className="flex items-center gap-1 rounded-md bg-amber-500/10 px-2 py-1 text-[9px] font-semibold text-amber-600 hover:bg-amber-500/20 disabled:opacity-40"
                title="Subir una versión nueva de este documento"
              >
                <GitBranch className="size-3" /> versión
              </button>
            </div>

            {/* ── historial de versiones (expandible) ── */}
            {tieneHistorial && (
              <>
                <button
                  onClick={() => toggleExpand(g.raiz.id)}
                  className="flex w-full items-center gap-2 border-t border-border px-4 py-2 text-[11px] text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                >
                  {estaExpandido ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
                  <GitBranch className="size-3" />
                  {g.versiones.length} versiones
                  <span className="ml-auto text-[9px]">ver historial</span>
                </button>

                {estaExpandido && (
                  <div className="space-y-0 border-t border-border bg-muted/30 px-4 py-2">
                    {g.versiones.map((v, i) => (
                      <div key={v.id} className="flex gap-3 py-1.5">
                        {/* timeline rail */}
                        <div className="flex flex-col items-center pt-1">
                          {i > 0 && <div className="h-2 w-px bg-border" />}
                          <div className={cn("size-2 rounded-full",
                            i === 0 ? "bg-primary" : "bg-muted-foreground/40")} />
                          {i < g.versiones.length - 1 && <div className="flex-1 w-px bg-border" />}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className={cn("text-[12px]", i === 0 ? "font-medium text-foreground" : "text-muted-foreground")}>
                              {v.nombre.replace(/_izel\.docx$/, ".docx").slice(0, 45)}
                            </span>
                            <span className="ml-auto flex items-center gap-2 text-[10px] text-muted-foreground">
                              <span>v{v.version}</span>
                              {etiquetaOrigen(v.nombre) && (
                                <span className="flex items-center gap-0.5 text-teal-500">
                                  <Sparkles className="size-2.5" /> {etiquetaOrigen(v.nombre)}
                                </span>
                              )}
                              <span>{fmtFecha(v.creado_en)}</span>
                              <button onClick={() => descargar(v)} className="hover:text-foreground" title="Descargar">
                                <Download className="size-3" />
                              </button>
                            </span>
                          </div>
                          {/* commit message */}
                          {v.mensaje_cambio && (
                            <p className="mt-0.5 rounded bg-muted px-2 py-1 text-[11px] italic text-muted-foreground">
                              {v.mensaje_cambio}
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        );
      })}

      {/* ── diálogo Izel ── */}
      {revisar && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => { setRevisar(null); setRevisionResultado(null); }}>
          <div className="w-full max-w-lg rounded-2xl bg-background p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center gap-2">
              <Sparkles className="size-4 text-teal-500" />
              <h3 className="text-[15px] font-semibold">Izel revisa: {revisar.nombre.slice(0, 40)}</h3>
            </div>
            {!revisionResultado ? (
              <>
                <p className="mb-2 text-[12px] text-muted-foreground">
                  Describe qué corregir. Izel leerá el documento, los comentarios y las notas del caso.
                </p>
                <textarea
                  value={revisar.consulta}
                  onChange={(e) => setRevisar({ ...revisar, consulta: e.target.value })}
                  placeholder="Ej: corrige segun los comentarios — SAPI no bursatil, art. 182 sobre 213"
                  rows={4}
                  className="mb-3 w-full resize-none rounded-lg border border-input bg-background px-3 py-2 text-[13px]"
                />
                <button onClick={enviarRevision} disabled={!revisar.consulta.trim() || revisando}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-teal-600 py-2.5 text-[13px] font-semibold text-white disabled:opacity-40">
                  {revisando ? <><Loader2 className="size-4 animate-spin" /> Revisando... (1-3 min)</> : <><Sparkles className="size-4" /> Revisar y generar versión</>}
                </button>
              </>
            ) : (
              <div className="space-y-3">
                {revisionResultado.archivo === "ERROR" ? (
                  <p className="rounded-lg bg-red-50 dark:bg-red-950/30 px-3 py-2 text-[12px] text-red-600">{revisionResultado.cambios}</p>
                ) : (
                  <>
                    <p className="rounded-lg bg-teal-50 dark:bg-teal-950/30 px-3 py-2 text-[12px] text-teal-700">
                      OK: {revisionResultado.archivo} — nueva versión guardada
                    </p>
                    <div>
                      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Cambios:</p>
                      <div className="max-h-40 overflow-y-auto whitespace-pre-wrap rounded-lg bg-muted px-3 py-2 text-[12px]">
                        {revisionResultado.cambios}
                      </div>
                    </div>
                  </>
                )}
                <button onClick={() => { setRevisar(null); setRevisionResultado(null); window.location.reload(); }}
                  className="w-full rounded-xl bg-primary py-2 text-[13px] font-semibold text-primary-foreground">
                  Cerrar y refrescar
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
