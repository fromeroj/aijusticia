"use client";

import Link from "next/link";
import {
  Scale, BookOpenCheck, ShieldCheck, Sparkles, ArrowRight, ArrowLeft,
  Brain, FileSearch, Lock, MapPin, XCircle, CheckCircle2, GitBranch,
  Landmark, ScrollText, Gavel, Building2,
} from "lucide-react";

export default function TlamatiniPage() {
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
            <ArrowLeft className="h-3.5 w-3.5" /> Inicio
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section className="bg-gradient-to-b from-[#ecfdf5] to-white px-6 py-16">
        <div className="mx-auto max-w-3xl text-center">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-[#047857]/30 bg-white px-4 py-1.5 text-xs font-medium text-[#047857]">
            <Sparkles className="h-3.5 w-3.5" />
            En construcción — primer release 2027
          </div>
          <h1 className="mb-3 font-serif text-5xl font-bold tracking-tight text-gray-900">
            Tlamatini
          </h1>
          <p className="mx-auto mb-8 max-w-xl text-base leading-relaxed text-gray-600">
            Del náhuatl <strong className="text-[#047857]">tlamatini</strong> — <em>"el que sabe"</em>.
            Así se llamaban los sabios consejeros del México antiguo: juristas, poetas, filósofos.
            Tlamatini es el primer modelo de IA jurídica entrenado exclusivamente con derecho
            mexicano.
          </p>
          <div className="mx-auto grid max-w-2xl gap-3 text-left sm:grid-cols-2">
            <div className="rounded-xl border border-[#047857]/15 bg-white p-4">
              <p className="text-2xl font-bold text-[#047857]">10B+</p>
              <p className="text-xs text-gray-500">tokens de fuentes legales mexicanas en entrenamiento</p>
            </div>
            <div className="rounded-xl border border-[#047857]/15 bg-white p-4">
              <p className="text-2xl font-bold text-[#047857]">32 + 1</p>
              <p className="text-xs text-gray-500">jurisdicciones: ley federal y de cada entidad federativa</p>
            </div>
          </div>
        </div>
      </section>

      {/* El problema */}
      <section className="border-t border-gray-100 px-6 py-14">
        <div className="mx-auto max-w-4xl">
          <h2 className="mb-2 text-center text-2xl font-bold text-gray-900">
            El problema: una cita inventada parece verdad
          </h2>
          <p className="mx-auto mb-10 max-w-2xl text-center text-sm text-gray-500">
            Probamos un modelo legal de clase mundial con 30 preguntas de la vida cotidiana
            mexicana. Respondió todo con fluidez profesional — pero con artículos equivocados.
          </p>

          <div className="grid gap-5 md:grid-cols-2">
            <div className="rounded-2xl border border-red-100 bg-red-50/40 p-6">
              <div className="mb-3 flex items-center gap-2 text-red-700">
                <XCircle className="h-5 w-5" />
                <span className="text-sm font-semibold">Modelo general entrenado en el extranjero</span>
              </div>
              <p className="text-sm leading-relaxed text-gray-700">
                <em>"Si te despidieron estando embarazada, el <strong>artículo 139</strong> de la
                Ley Federal del Trabajo te protege…"</em>
              </p>
              <p className="mt-3 rounded-lg bg-white px-3 py-2 text-xs text-red-600">
                ✗ El artículo 139 no existe con ese contenido. El correcto es el <strong>164</strong>.
                Suena perfecto. Es falso.
              </p>
            </div>
            <div className="rounded-2xl border border-[#047857]/20 bg-[#ecfdf5] p-6">
              <div className="mb-3 flex items-center gap-2 text-[#047857]">
                <CheckCircle2 className="h-5 w-5" />
                <span className="text-sm font-semibold">Tlamatini (enfoque anclado)</span>
              </div>
              <p className="text-sm leading-relaxed text-gray-700">
                <em>"…la trabajadora embarazada goza de estabilidad reforzada (<strong>art. 164
                LFT</strong>) <span className="text-xs text-gray-400">[SJI 2a./J. 42/2016]</span>…"</em>
              </p>
              <p className="mt-3 rounded-lg bg-white px-3 py-2 text-xs text-[#047857]">
                ✓ Cada afirmación sale de un pasaje recuperado del corpus — con su cita verificable.
              </p>
            </div>
          </div>

          <p className="mx-auto mt-8 max-w-2xl text-center text-xs italic text-gray-400">
            El 58–88% de las respuestas jurídicas de modelos generales contienen alucinación
            (Dahl et al., 2024). En derecho, una cita fluida y falsa es peor que no responder.
          </p>
        </div>
      </section>

      {/* Cómo se construye */}
      <section className="border-t border-gray-100 bg-gray-50/60 px-6 py-14">
        <div className="mx-auto max-w-4xl">
          <h2 className="mb-2 text-center text-2xl font-bold text-gray-900">
            Cómo se construye un sabio
          </h2>
          <p className="mx-auto mb-10 max-w-2xl text-center text-sm text-gray-500">
            Tres ingredientes: el derecho mexicano completo, la disciplina de citar y la honestidad
            de admitir límites.
          </p>

          <div className="grid gap-5 md:grid-cols-3">
            <div className="rounded-2xl border border-gray-100 bg-white p-6">
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-[#047857]/10 text-[#047857]">
                <Landmark className="h-5 w-5" />
              </div>
              <h3 className="mb-1.5 text-sm font-semibold text-gray-900">1. Lee el derecho mexicano</h3>
              <p className="text-xs leading-relaxed text-gray-600">
                Leyes federales y de los 32 estados, el Diario Oficial desde 1999, gacetas estatales,
                sentencias de tribunales de justicia local, jurisprudencia del SJF y la doctrina del
                IIJ-UNAM. Miles de millones de palabras de fuentes oficiales — ninguna ley extranjera.
              </p>
            </div>
            <div className="rounded-2xl border border-gray-100 bg-white p-6">
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-[#047857]/10 text-[#047857]">
                <FileSearch className="h-5 w-5" />
              </div>
              <h3 className="mb-1.5 text-sm font-semibold text-gray-900">2. Aprende a responder con fundamento</h3>
              <p className="text-xs leading-relaxed text-gray-600">
                Se entrena con el formato exacto de trabajo: pasaje de ley recuperado → pregunta →
                respuesta con cita. Como los considerandos de un juez: cada afirmación, su artículo.
                El modelo no memoriza respuestas; aprende el <em>oficio</em> de fundamentar.
              </p>
            </div>
            <div className="rounded-2xl border border-gray-100 bg-white p-6">
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-[#047857]/10 text-[#047857]">
                <ShieldCheck className="h-5 w-5" />
              </div>
              <h3 className="mb-1.5 text-sm font-semibold text-gray-900">3. Admite lo que no sabe</h3>
              <p className="text-xs leading-relaxed text-gray-600">
                La virtud que le da nombre: si las fuentes no sustentan una respuesta, Tlamatini se
                abstiene y lo dice — en vez de inventar con confianza. La honestidad no es un parche;
                está en el entrenamiento.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Soberanía */}
      <section className="border-t border-gray-100 px-6 py-14">
        <div className="mx-auto grid max-w-4xl items-center gap-8 md:grid-cols-2">
          <div>
            <h2 className="mb-3 text-2xl font-bold text-gray-900">
              Soberano: la ley de tu despacho no cruza la frontera
            </h2>
            <p className="mb-4 text-sm leading-relaxed text-gray-600">
              El secreto profesional es un deber con sanción penal (arts. 210–211 del Código Penal
              Federal). Subir expedientes de clientes a una API extranjera que puede retenerlos no
              es una opción para un despacho mexicano.
            </p>
            <p className="text-sm leading-relaxed text-gray-600">
              Tlamatini se despliega <strong>dentro de la infraestructura de la firma</strong>, y cada
              despacho entrena un adaptador privado con sus propios casos: el estilo de la casa, sus
              estrategias, su memoria institucional — sin que un solo byte salga del perímetro.
            </p>
          </div>
          <div className="rounded-2xl bg-gray-900 p-6 text-white">
            <div className="mb-4 flex items-center gap-2">
              <Building2 className="h-5 w-5 text-[#6ee7b7]" />
              <span className="text-sm font-semibold">Despliegue en tu firma</span>
            </div>
            <ul className="space-y-2.5 text-xs leading-relaxed text-gray-300">
              <li className="flex gap-2"><CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#6ee7b7]" />
                Inferencia 100% local — cero llamadas a nubes extranjeras</li>
              <li className="flex gap-2"><CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#6ee7b7]" />
                Adaptador privado por despacho, aislamiento verificable</li>
              <li className="flex gap-2"><CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#6ee7b7]" />
                Compatible con LFPDPPP y el deber de sigilo</li>
              <li className="flex gap-2"><CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#6ee7b7]" />
                La base mejora para todos; tu know-how jamás se mezcla</li>
            </ul>
          </div>
        </div>
      </section>

      {/* Qué es y qué no es */}
      <section className="border-t border-gray-100 bg-gray-50/60 px-6 py-14">
        <div className="mx-auto max-w-4xl">
          <h2 className="mb-8 text-center text-2xl font-bold text-gray-900">
            Lo que Tlamatini no es
          </h2>
          <div className="grid gap-4 sm:grid-cols-3">
            {[
              { icon: Gavel, t: "No es juez", d: "No decide casos ni sustituye la función jurisdiccional. Orienta con la ley en la mano." },
              { icon: ScrollText, t: "No es abogado", d: "La respuesta formal y la firma de un licenciado con cédula siguen siendo insustituibles." },
              { icon: Brain, t: "No es oráculo", d: "No responde todo: cuando no hay sustento en las fuentes, lo dice. Esa es su virtud." },
            ].map((x) => (
              <div key={x.t} className="rounded-2xl border border-gray-100 bg-white p-5 text-center">
                <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-gray-100 text-gray-500">
                  <x.icon className="h-5 w-5" />
                </div>
                <p className="text-sm font-semibold text-gray-800">{x.t}</p>
                <p className="mt-1 text-xs leading-relaxed text-gray-500">{x.d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Roadmap */}
      <section className="border-t border-gray-100 px-6 py-14">
        <div className="mx-auto max-w-2xl">
          <h2 className="mb-2 text-center text-2xl font-bold text-gray-900">Camino al primer release</h2>
          <p className="mb-10 text-center text-sm text-gray-500">Dónde estamos y qué sigue</p>
          <div className="space-y-0">
            {[
              { fase: "Corpus", estado: "en curso", detalle: "Miles de millones de tokens cosechados de fuentes oficiales; ingesta diaria diferencial", hecho: true },
              { fase: "Entrenamiento (CPT)", estado: "siguiente", detalle: "Preentrenamiento continuo sobre derecho mexicano en infraestructura dedicada", hecho: false },
              { fase: "Evaluación pública", estado: "2027", detalle: "Batería de preguntas ciudadanas con citas verificables, resultados abiertos", hecho: false },
              { fase: "Despliegue en despachos", estado: "2027", detalle: "Primeros pilotos on-premise con adaptadores privados", hecho: false },
            ].map((p, i, arr) => (
              <div key={p.fase} className="flex gap-4">
                <div className="flex flex-col items-center">
                  <div className={`flex h-8 w-8 items-center justify-center rounded-full border-2 ${p.hecho ? "border-[#047857] bg-[#047857]" : "border-gray-200 bg-white"}`}>
                    {p.hecho ? <CheckCircle2 className="h-4 w-4 text-white" /> : <GitBranch className="h-3.5 w-3.5 text-gray-300" />}
                  </div>
                  {i < arr.length - 1 && <div className={`h-10 w-0.5 ${p.hecho ? "bg-[#047857]/40" : "bg-gray-200"}`} />}
                </div>
                <div className="pb-8">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold text-gray-900">{p.fase}</p>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${p.hecho ? "bg-[#ecfdf5] text-[#047857]" : "bg-gray-100 text-gray-500"}`}>
                      {p.estado}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs leading-relaxed text-gray-500">{p.detalle}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-gray-100 bg-gray-900 px-6 py-12">
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="mb-3 text-xl font-bold text-white">
            Mientras Tlamatini termina de formarse…
          </h2>
          <p className="mx-auto mb-6 max-w-lg text-sm text-gray-300">
            AI Justicia ya orienta con citas verificadas contra las fuentes oficiales — el mismo
            estándar de honestidad que Tlamatini llevará a cada despacho.
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <Link
              href="/para-ti"
              className="flex items-center gap-2 rounded-xl bg-[#047857] px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#036c4c]"
            >
              Probar la orientación gratis <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/despachos"
              className="flex items-center gap-2 rounded-xl border border-white/25 px-5 py-3 text-sm font-medium text-white transition hover:bg-white/10"
            >
              Soy despacho <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>

      <footer className="px-6 py-6 text-center">
        <p className="text-[10px] text-gray-400">
          Tlamatini es un modelo en desarrollo. El contenido generado por IA es informativo y no
          sustituye la asesoría de un abogado con cédula profesional.
        </p>
      </footer>
    </div>
  );
}
