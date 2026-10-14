"use client";

/**
 * /estado — Estado real del corpus jurídico, en vivo desde el engine.
 * Tarjetas por fuente + mapa SVG de México coloreado por cobertura estatal.
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import { Activity, CircleAlert, CircleCheck, Clock, Database, MapPin } from "lucide-react";
import { MEXICO_PATHS } from "@/lib/mexicoPaths";
import { SiteFooter } from "@/components/layout/SiteFooter";

interface FuenteStatus {
  fuente: string;
  documentos: number;
  inicio: string | null;
  ultimo_doc: string | null;
  ultima_ingesta: string | null;
  dias_sin_nuevos: number | null;
  estado: "vivo" | "tibio" | "detenido" | "estatico";
  meta?: { meta: number; nota: string };
}

interface StatusData {
  generado: string;
  totales: { documentos: number; chunks: number; tokens_estimados: number; fuentes: number };
  fuentes: FuenteStatus[];
  entidades: Array<{ entidad: string; iso: string | null; documentos: number; ultima: string | null }>;
  proyectos: Array<{ nombre: string; fase: string; ids_recolectados: number; meta: number | null; unidad: string }>;
}

const NOMBRES: Record<string, string> = {
  DOF: "Diario Oficial de la Federación",
  LeyesBiblio: "Leyes y códigos federales",
  SJF: "Jurisprudencia (SJF)",
  SentenciasEdomex: "Sentencias — Estado de México",
  SentenciasCDMX: "Sentencias — CDMX (SIVEPJ)",
  SentenciasQro: "Sentencias — Querétaro",
  GacetaEstatal: "Gacetas estatales",
  GacetaCDMX: "Gaceta CDMX",
  "SCJN-Libros": "SCJN — Libros",
  JustiaEstatal: "Justia estatal",
  OrdenJuridico: "Orden Jurídico Nacional",
};

const ISO_NOMBRE: Record<string, string> = {
  MXAGU: "Aguascalientes", MXBCN: "Baja California", MXBCS: "Baja California Sur",
  MXCAM: "Campeche", MXCHP: "Chiapas", MXCHH: "Chihuahua", MXCMX: "Ciudad de México",
  MXCOA: "Coahuila", MXCOL: "Colima", MXDUR: "Durango", MXGUA: "Guanajuato",
  MXGRO: "Guerrero", MXHID: "Hidalgo", MXJAL: "Jalisco", MXMEX: "Estado de México",
  MXMIC: "Michoacán", MXMOR: "Morelos", MXNAY: "Nayarit", MXNLE: "Nuevo León",
  MXOAX: "Oaxaca", MXPUE: "Puebla", MXQUE: "Querétaro", MXROO: "Quintana Roo",
  MXSLP: "San Luis Potosí", MXSIN: "Sinaloa", MXSON: "Sonora", MXTAB: "Tabasco",
  MXTAM: "Tamaulipas", MXTLA: "Tlaxcala", MXVER: "Veracruz", MXYUC: "Yucatán",
  MXZAC: "Zacatecas",
};

function fmt(n: number): string {
  return n.toLocaleString("es-MX");
}

function fmtTokens(n: number): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)} mil millones`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} millones`;
  return fmt(n);
}

function fmtFecha(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("es-MX", { year: "numeric", month: "short", day: "numeric" });
}

function EstadoBadge({ estado, dias }: { estado: string; dias: number | null }) {
  if (estado === "vivo")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
        <CircleCheck className="h-3 w-3" /> al día{dias !== null ? ` · hace ${dias}d` : ""}
      </span>
    );
  if (estado === "tibio")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700">
        <Clock className="h-3 w-3" /> hace {dias ?? "?"}d
      </span>
    );
  if (estado === "detenido")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-medium text-red-700">
        <CircleAlert className="h-3 w-3" /> detenido · hace {dias ?? "?"}d
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-500">
      estático
    </span>
  );
}

// escala de color del mapa: docs por entidad → de gris claro a esmeralda
function colorPorDocs(docs: number, max: number): string {
  if (!docs) return "#e9edec";
  const t = Math.min(1, Math.sqrt(docs) / Math.sqrt(max));
  const r = Math.round(231 - t * 227);   // 231 → 4
  const g = Math.round(244 - t * 124);   // 244 → 120
  const b = Math.round(238 - t * 151);   // 238 → 87
  return `rgb(${r},${g},${b})`;
}

export default function EstadoPage() {
  const [data, setData] = useState<StatusData | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const cargar = () =>
      fetch("/corpus/status")
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then(setData)
        .catch(() => setError(true));
    cargar();
    const iv = setInterval(cargar, 300000);
    return () => clearInterval(iv);
  }, []);

  const entidadesPorIso: Record<string, number> = {};
  if (data) {
    for (const e of data.entidades) {
      if (e.iso) entidadesPorIso[e.iso] = e.documentos;
    }
  }
  const maxEnt = Math.max(1, ...Object.values(entidadesPorIso));

  return (
    <div className="flex min-h-screen flex-col bg-[#fafaf6] text-gray-900">
      {/* header */}
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link href="/" className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-[#047857] to-[#0d9488] text-white">⚖</span>
            <span className="text-sm font-bold">AI Justicia</span>
          </Link>
          <span className="text-xs text-gray-400">
            {data ? `actualizado ${fmtFecha(data.generado)}` : "cargando…"}
          </span>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <h1 className="font-serif text-3xl font-semibold tracking-tight">Estado del corpus jurídico</h1>
        <p className="mt-1 max-w-2xl text-sm text-gray-500">
          Lo que el motor sabe, fuente por fuente: cuánto tiene, desde cuándo, y cuándo fue la
          última actualización. Sin maquillaje — el semáforo se calcula contra la cadencia esperada de cada fuente.
        </p>

        {error && (
          <p className="mt-6 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
            No se pudieron cargar las estadísticas.
          </p>
        )}

        {/* totales */}
        {data && (
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { icon: <Database className="h-4 w-4" />, valor: fmt(data.totales.documentos), etiqueta: "documentos" },
              { icon: <Database className="h-4 w-4" />, valor: fmt(data.totales.chunks), etiqueta: "fragmentos indexados" },
              { icon: <Activity className="h-4 w-4" />, valor: fmtTokens(data.totales.tokens_estimados), etiqueta: "tokens" },
              { icon: <MapPin className="h-4 w-4" />, valor: fmt(data.totales.fuentes), etiqueta: "fuentes" },
            ].map((t, i) => (
              <div key={i} className="rounded-xl border border-gray-200 bg-white p-4">
                <div className="flex items-center gap-2 text-[#047857]">{t.icon}</div>
                <p className="mt-2 text-xl font-bold tracking-tight">{t.valor}</p>
                <p className="text-xs text-gray-400">{t.etiqueta}</p>
              </div>
            ))}
          </div>
        )}

        {/* mapa + leyenda */}
        {data && (
          <div className="mt-8 grid gap-6 lg:grid-cols-[1.2fr_1fr]">
            <div className="rounded-xl border border-gray-200 bg-white p-4">
              <h2 className="text-sm font-semibold text-gray-700">Cobertura por entidad federativa</h2>
              <svg viewBox="0 0 1000 640" className="mt-2 w-full">
                {MEXICO_PATHS.map((p) => {
                  const docs = entidadesPorIso[p.id] || 0;
                  const nombre = ISO_NOMBRE[p.id] || p.id;
                  return (
                    <path key={p.id} d={p.d} fill={colorPorDocs(docs, maxEnt)} stroke="#ffffff" strokeWidth={0.6}>
                      <title>{`${nombre}: ${fmt(docs)} documentos`}</title>
                    </path>
                  );
                })}
              </svg>
              <div className="mt-2 flex items-center gap-2 text-[11px] text-gray-400">
                <span>menos</span>
                {[0.1, 0.3, 0.55, 0.8, 1].map((t) => (
                  <span key={t} className="h-3 w-6 rounded-sm" style={{ background: colorPorDocs(t * maxEnt, maxEnt) }} />
                ))}
                <span>más documentos</span>
              </div>
            </div>

            {/* top entidades */}
            <div className="rounded-xl border border-gray-200 bg-white p-4">
              <h2 className="text-sm font-semibold text-gray-700">Sentencias y gacetas por entidad</h2>
              <div className="mt-3 space-y-2">
                {data.entidades.slice(0, 10).map((e) => (
                  <div key={e.entidad} className="flex items-center gap-3">
                    <span className="w-36 truncate text-xs text-gray-600">{e.entidad}</span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-gray-100">
                      <div
                        className="h-full rounded-full bg-[#047857]"
                        style={{ width: `${Math.max(3, (e.documentos / maxEnt) * 100)}%` }}
                      />
                    </div>
                    <span className="w-14 text-right text-xs tabular-nums text-gray-500">{fmt(e.documentos)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* fuentes */}
        {data && (
          <div className="mt-8">
            <h2 className="text-sm font-semibold text-gray-700">Fuentes, una por una</h2>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {data.fuentes.map((f) => {
                const maxDocs = Math.max(...data.fuentes.map((x) => x.documentos));
                return (
                  <div key={f.fuente} className="rounded-xl border border-gray-200 bg-white p-4">
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="text-sm font-semibold leading-tight">{NOMBRES[f.fuente] || f.fuente}</h3>
                      <EstadoBadge estado={f.estado} dias={f.dias_sin_nuevos} />
                    </div>
                    <p className="mt-2 text-2xl font-bold tabular-nums tracking-tight text-[#047857]">{fmt(f.documentos)}</p>
                    <p className="text-[11px] text-gray-400">documentos</p>
                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-gray-100">
                      <div className="h-full rounded-full bg-[#047857]" style={{ width: `${Math.max(2, (f.documentos / maxDocs) * 100)}%` }} />
                    </div>
                    <dl className="mt-3 space-y-1 text-[11px] text-gray-500">
                      <div className="flex justify-between"><dt>Cobertura desde</dt><dd>{fmtFecha(f.inicio)}</dd></div>
                      <div className="flex justify-between"><dt>Último documento</dt><dd>{fmtFecha(f.ultimo_doc)}</dd></div>
                      <div className="flex justify-between"><dt>Última ingesta</dt><dd>{fmtFecha(f.ultima_ingesta)}</dd></div>
                    </dl>
                    {f.meta && (
                      <p className="mt-2 rounded-md bg-emerald-50 px-2 py-1 text-[11px] text-emerald-700">
                        ✓ {f.meta.nota}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* proyectos activos */}
        {data && data.proyectos.length > 0 && (
          <div className="mt-8">
            <h2 className="text-sm font-semibold text-gray-700">En proceso</h2>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {data.proyectos.map((p) => (
                <div key={p.nombre} className="rounded-xl border border-blue-200 bg-blue-50/60 p-4">
                  <h3 className="text-sm font-semibold text-blue-900">{p.nombre}</h3>
                  <p className="mt-0.5 text-xs text-blue-700">{p.fase}</p>
                  {p.meta && (
                    <>
                      <div className="mt-2 h-2 overflow-hidden rounded-full bg-blue-100">
                        <div className="h-full rounded-full bg-blue-600" style={{ width: `${(p.ids_recolectados / p.meta) * 100}%` }} />
                      </div>
                      <p className="mt-1 text-[11px] text-blue-800">
                        {fmt(p.ids_recolectados)} / {fmt(p.meta)} {p.unidad} ({((p.ids_recolectados / p.meta) * 100).toFixed(1)}%)
                      </p>
                    </>
                  )}
                  {!p.meta && (
                    <p className="mt-1 text-[11px] text-blue-800">{fmt(p.ids_recolectados)} {p.unidad}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        <p className="mt-10 text-[11px] leading-relaxed text-gray-400">
          Los totales de tokens son estimados (≈280 tokens por fragmento indexado). El semáforo compara la
          última ingesta contra la cadencia esperada de cada fuente (DOF y leyes: diario · SJF: semanal ·
          estatales: según su publicación). Mapa: simplemaps.com — licencia libre con atribución.
        </p>
      </main>

      <SiteFooter />
    </div>
  );
}
