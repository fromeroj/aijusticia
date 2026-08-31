"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { Scale, Search, ArrowLeft, Globe, CheckCircle2, Clock } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

interface Pregunta {
  id: number;
  texto: string;
  idioma: string;
  fuente: string;
  texto_es: string | null;
  traducido: boolean;
}

export default function PreguntasAdmin() {
  const [preguntas, setPreguntas] = useState<Pregunta[]>([]);
  const [total, setTotal] = useState(0);
  const [fuentes, setFuentes] = useState<Record<string, number>>({});
  const [fuente, setFuente] = useState("");
  const [idioma, setIdioma] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const LIMIT = 50;

  const fetchPreguntas = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
    if (fuente) params.set("fuente", fuente);
    if (idioma) params.set("idioma", idioma);
    if (q) params.set("q", q);
    try {
      const res = await fetch(`${API_URL}/admin/preguntas?${params}`);
      const d = await res.json();
      setPreguntas(d.preguntas || []);
      setTotal(d.total || 0);
      setFuentes(d.fuentes || {});
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [fuente, idioma, q, offset]);

  useEffect(() => {
    fetchPreguntas();
  }, [fetchPreguntas]);

  const paginas = Math.ceil(total / LIMIT);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-100 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center gap-3">
          <Link href="/admin" className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#047857]">
            <Scale className="h-5 w-5 text-white" />
          </Link>
          <div>
            <h1 className="text-sm font-bold text-gray-900">Preguntas legales — corpus</h1>
            <p className="text-[10px] text-gray-400">{total.toLocaleString("es-MX")} preguntas · SFT + evaluación</p>
          </div>
          <Link href="/admin" className="ml-auto flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600">
            <ArrowLeft className="h-3.5 w-3.5" /> Admin
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-6">
        {/* filtros */}
        <div className="mb-4 flex flex-wrap gap-2">
          <select value={fuente} onChange={(e) => { setFuente(e.target.value); setOffset(0); }}
            className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs">
            <option value="">Todas las fuentes</option>
            {Object.entries(fuentes).map(([f, c]) => (
              <option key={f} value={f}>{f} ({c.toLocaleString()})</option>
            ))}
          </select>
          <select value={idioma} onChange={(e) => { setIdioma(e.target.value); setOffset(0); }}
            className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs">
            <option value="">Ambos idiomas</option>
            <option value="es">Español</option>
            <option value="en">Inglés</option>
          </select>
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-300" />
            <input
              value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }}
              placeholder="Buscar en preguntas..."
              className="w-full rounded-lg border border-gray-200 bg-white py-2 pl-9 pr-3 text-xs focus:border-[#047857] focus:outline-none"
            />
          </div>
        </div>

        {/* lista */}
        {loading ? (
          <p className="py-10 text-center text-sm text-gray-400">Cargando…</p>
        ) : (
          <div className="space-y-2">
            {preguntas.map((p) => (
              <div key={p.id} className="rounded-xl border border-gray-100 bg-white p-4">
                <div className="mb-1.5 flex items-center gap-2 text-[10px]">
                  <span className="rounded-full bg-gray-100 px-2 py-0.5 font-medium text-gray-500">{p.fuente}</span>
                  <span className={`rounded-full px-2 py-0.5 font-medium ${p.idioma === "es" ? "bg-[#ecfdf5] text-[#047857]" : "bg-blue-50 text-blue-600"}`}>
                    {p.idioma === "es" ? "ES" : "EN"}
                  </span>
                  {p.idioma === "en" && (
                    p.traducido ? (
                      <span className="flex items-center gap-0.5 text-[#047857]"><CheckCircle2 className="h-3 w-3" /> traducida</span>
                    ) : (
                      <span className="flex items-center gap-0.5 text-gray-300"><Clock className="h-3 w-3" /> pendiente</span>
                    )
                  )}
                </div>
                <p className="text-sm leading-relaxed text-gray-800">{p.texto}</p>
                {p.texto_es && (
                  <p className="mt-2 border-l-2 border-[#047857]/30 pl-3 text-sm italic text-gray-500">{p.texto_es}</p>
                )}
              </div>
            ))}
          </div>
        )}

        {/* paginación */}
        {paginas > 1 && (
          <div className="mt-6 flex items-center justify-center gap-3 text-xs">
            <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))}
              className="rounded-lg border border-gray-200 px-3 py-1.5 disabled:opacity-30">← Anterior</button>
            <span className="text-gray-400">Página {offset / LIMIT + 1} de {paginas}</span>
            <button disabled={offset + LIMIT >= total} onClick={() => setOffset(offset + LIMIT)}
              className="rounded-lg border border-gray-200 px-3 py-1.5 disabled:opacity-30">Siguiente →</button>
          </div>
        )}
      </main>
    </div>
  );
}
