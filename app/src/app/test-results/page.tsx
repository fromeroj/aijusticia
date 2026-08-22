"use client";

import { useState, useEffect } from "react";

interface Pasaje {
  fuente: string;
  titulo: string;
  texto: string;
}

interface ResultItem {
  idx: number;
  question_original: string;
  question_es: string;
  language: string;
  source: string;
  respuesta: string;
  abstencion: boolean;
  pasajes: Pasaje[];
  n_pasajes: number;
}

interface ResultsData {
  results: ResultItem[];
  total: number;
  answered: number;
  abstained: number;
  answer_rate: number;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function TestResultsPage() {
  const [data, setData] = useState<ResultsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [filter, setFilter] = useState<"all" | "answered" | "abstained">("all");

  useEffect(() => {
    fetch(`${API_URL}/admin/rag-results`)
      .then((r) => r.json())
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const toggleExpand = (idx: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-500">Cargando resultados...</div>
      </div>
    );
  }

  if (!data || data.total === 0) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="text-gray-500 mb-4">No hay resultados disponibles</div>
          <div className="text-sm text-gray-400">
            Ejecuta: <code className="bg-gray-200 px-2 py-1 rounded">python scripts/batch_rag.py</code>
          </div>
        </div>
      </div>
    );
  }

  const filtered = data.results.filter((r) => {
    if (filter === "answered") return !r.abstencion;
    if (filter === "abstained") return r.abstencion;
    return true;
  });

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-[#047857] text-white px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold">AI Justicia — Resultados de Prueba</h1>
            <p className="text-sm text-green-100">
              Pipeline RAG + LoRA · {data.total} preguntas procesadas
            </p>
          </div>
          <a
            href="/"
            className="text-sm bg-white/20 hover:bg-white/30 px-4 py-2 rounded-lg transition"
          >
            ← Chat
          </a>
        </div>
      </div>

      {/* Stats */}
      <div className="max-w-6xl mx-auto px-6 py-6">
        <div className="grid grid-cols-4 gap-4 mb-6">
          <StatCard label="Total" value={data.total} color="bg-gray-600" />
          <StatCard label="Respondidas" value={data.answered} color="bg-green-600" />
          <StatCard label="Abstenidas" value={data.abstained} color="bg-red-500" />
          <StatCard
            label="Tasa de respuesta"
            value={`${data.answer_rate}%`}
            color={data.answer_rate > 70 ? "bg-green-600" : "bg-amber-500"}
          />
        </div>

        {/* Filter buttons */}
        <div className="flex gap-2 mb-4">
          <FilterButton
            active={filter === "all"}
            onClick={() => setFilter("all")}
            label={`Todas (${data.total})`}
          />
          <FilterButton
            active={filter === "answered"}
            onClick={() => setFilter("answered")}
            label={`Respondidas (${data.answered})`}
          />
          <FilterButton
            active={filter === "abstained"}
            onClick={() => setFilter("abstained")}
            label={`Abstenidas (${data.abstained})`}
          />
        </div>

        {/* Results list */}
        <div className="space-y-3">
          {filtered.map((r) => (
            <div
              key={r.idx}
              className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden"
            >
              {/* Question header */}
              <div
                className="px-5 py-3 cursor-pointer hover:bg-gray-50 transition"
                onClick={() => toggleExpand(r.idx)}
              >
                <div className="flex items-start gap-3">
                  <span
                    className={`text-xs font-bold px-2 py-1 rounded shrink-0 ${
                      r.abstencion
                        ? "bg-red-100 text-red-700"
                        : "bg-green-100 text-green-700"
                    }`}
                  >
                    {r.abstencion ? "ABSTENCIÓN" : "RESPONDIDA"}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-gray-900 text-sm">
                      {r.question_es || r.question_original}
                    </div>
                    <div className="text-xs text-gray-400 mt-1">
                      [{r.source}/{r.language}] · {r.n_pasajes} pasajes ·{" "}
                      {r.pasajes.length > 0 &&
                        r.pasajes.map((p) => p.fuente.substring(0, 10)).join(", ")}
                    </div>
                  </div>
                  <span className="text-gray-300 text-xs shrink-0">
                    {expanded.has(r.idx) ? "▲" : "▼"}
                  </span>
                </div>
              </div>

              {/* Expanded content */}
              {expanded.has(r.idx) && (
                <div className="px-5 py-4 border-t border-gray-100 bg-gray-50">
                  {/* Answer */}
                  <div className="mb-4">
                    <div className="text-xs font-semibold text-gray-500 uppercase mb-1">
                      Respuesta
                    </div>
                    <div className="text-sm text-gray-800 whitespace-pre-wrap">
                      {r.respuesta}
                    </div>
                  </div>

                  {/* References */}
                  {r.pasajes.length > 0 && (
                    <div>
                      <div className="text-xs font-semibold text-gray-500 uppercase mb-2">
                        Pasajes recuperados ({r.pasajes.length})
                      </div>
                      <div className="space-y-2">
                        {r.pasajes.map((p, i) => (
                          <div
                            key={i}
                            className="bg-white border border-gray-200 rounded p-3 text-xs"
                          >
                            <div className="font-medium text-gray-700 mb-1">
                              [{i + 1}] {p.fuente} / {p.titulo}
                            </div>
                            <div className="text-gray-500 line-clamp-3">
                              {p.texto}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number | string;
  color: string;
}) {
  return (
    <div className={`${color} text-white rounded-lg p-4`}>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-xs text-white/80 mt-1">{label}</div>
    </div>
  );
}

function FilterButton({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
        active
          ? "bg-[#047857] text-white"
          : "bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"
      }`}
    >
      {label}
    </button>
  );
}
