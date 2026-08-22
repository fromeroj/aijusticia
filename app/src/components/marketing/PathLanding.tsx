"use client";

import Link from "next/link";
import { Scale, ArrowRight, ArrowLeft, Check } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface Feature {
  icon: React.ReactNode;
  titulo: string;
  texto: string;
}

export interface PasoProc {
  titulo: string;
  texto: string;
}

export function PathLanding({
  color,
  colorHover,
  colorSoft,
  emoji,
  publico,
  titular,
  promesa,
  features,
  proceso,
  accesoTitulo,
  accesoItems,
  ctaTexto,
  ctaHref,
  notaLegal,
}: {
  color: string;            // ej. "bg-[#047857]"
  colorHover: string;
  colorSoft: string;        // ej. "bg-[#047857]/10 text-[#047857]"
  emoji: string;
  publico: string;
  titular: string;
  promesa: string;
  features: Feature[];
  proceso: PasoProc[];
  accesoTitulo: string;
  accesoItems: string[];
  ctaTexto: string;
  ctaHref: string;
  notaLegal?: string;
}) {
  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <header className="border-b border-gray-100 px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center gap-2">
          <Link href="/" className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#047857]">
            <Scale className="h-5 w-5 text-white" />
          </Link>
          <span className="text-sm font-semibold text-gray-900">AI Justicia</span>
          <Link
            href="/"
            className="ml-auto flex items-center gap-1 text-xs text-gray-400 transition hover:text-gray-600"
          >
            <ArrowLeft className="h-3 w-3" /> Inicio
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section className="px-6 pb-10 pt-14 text-center">
        <div className="mx-auto max-w-2xl">
          <span className={`mb-4 inline-block rounded-full px-4 py-1 text-xs font-semibold ${colorSoft}`}>
            {emoji} {publico}
          </span>
          <h1 className="mb-4 font-serif text-3xl font-bold leading-tight text-gray-900 sm:text-4xl">{titular}</h1>
          <p className="text-lg leading-relaxed text-gray-600">{promesa}</p>
        </div>
      </section>

      {/* Features */}
      <section className="bg-gray-50 px-6 py-12">
        <div className="mx-auto max-w-4xl">
          <h2 className="mb-8 text-center text-xl font-semibold text-gray-900">Qué obtienes</h2>
          <div className="grid gap-5 md:grid-cols-2">
            {features.map((f) => (
              <div key={f.titulo} className="flex gap-4 rounded-2xl border border-gray-200 bg-white p-5">
                <div className={`flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl ${colorSoft}`}>
                  {f.icon}
                </div>
                <div>
                  <div className="font-semibold text-gray-900">{f.titulo}</div>
                  <div className="mt-1 text-sm leading-relaxed text-gray-500">{f.texto}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Proceso */}
      <section className="px-6 py-12">
        <div className="mx-auto max-w-3xl">
          <h2 className="mb-8 text-center text-xl font-semibold text-gray-900">Cómo funciona</h2>
          <div className="space-y-0">
            {proceso.map((p, i) => (
              <div key={p.titulo} className="relative flex gap-5 pb-8 last:pb-0">
                {/* Línea conectora */}
                {i < proceso.length - 1 && (
                  <div className={`absolute left-[19px] top-10 h-full w-0.5 ${color.replace("bg-", "bg-").split(" ")[0]} opacity-20`} />
                )}
                <div className={`z-10 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full text-sm font-bold ${color} text-white`}>
                  {i + 1}
                </div>
                <div className="pt-1.5">
                  <div className="font-semibold text-gray-900">{p.titulo}</div>
                  <div className="mt-1 text-sm leading-relaxed text-gray-500">{p.texto}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Acceso / precios */}
      <section className="px-6 pb-12">
        <div className="mx-auto max-w-xl rounded-2xl border-2 p-7 text-center" style={{ borderColor: undefined }}>
          <div className={`rounded-2xl border-2 border-gray-900/5 ${color} p-7 text-white`}>
            <h3 className="mb-5 text-lg font-bold">{accesoTitulo}</h3>
            <ul className="mx-auto mb-7 max-w-sm space-y-2.5 text-left text-sm">
              {accesoItems.map((a) => (
                <li key={a} className="flex items-start gap-2">
                  <Check className="mt-0.5 h-4 w-4 flex-shrink-0" />
                  <span>{a}</span>
                </li>
              ))}
            </ul>
            <Link
              href={ctaHref}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-white px-5 py-4 text-base font-semibold text-gray-900 transition hover:bg-gray-100 sm:w-auto sm:self-center"
            >
              {ctaTexto}
              <ArrowRight className="h-4 w-4" />
            </Link>
            <p className="mt-4 text-xs text-white/70">
              Sin tarjetas · Puedes salir cuando quieras
            </p>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-100 px-6 py-8 text-center">
        <p className="mx-auto max-w-2xl text-xs text-gray-400">
          {notaLegal ??
            "⚠️ El contenido generado por IA es exclusivamente informativo. No constituye asesoramiento legal ni sustituye la consulta con un abogado colegiado, quien es el único profesional autorizado para brindar orientación jurídica formal."}
        </p>
        <p className="mt-2 text-[10px] font-medium text-[#047857]">
          🇲🇽 Hecho en México, para México — 32 entidades federativas + normativa federal
        </p>
      </footer>
    </div>
  );
}
