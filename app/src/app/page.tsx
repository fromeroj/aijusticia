"use client";

import Link from "next/link";
import {
  Scale, ShieldCheck, BookOpenCheck, MessageCircleQuestion,
  FileSearch, BadgeCheck, ArrowRight, Building2, UserCheck,
  MapPin, Lock, Handshake, Sparkles,
} from "lucide-react";
import { useChatStore } from "@/lib/store";

export default function Landing() {
  const sesion = useChatStore((s) => s.sesion);

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <header className="border-b border-gray-100 px-6 py-4">
        <div className="mx-auto flex max-w-5xl items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#047857]">
            <Scale className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-base font-bold text-gray-900">AI Justicia</h1>
            <p className="text-[10px] text-gray-400">Justicia mexicana, al alcance de todos</p>
          </div>
          {sesion ? (
            <Link
              href="/chat"
              className="ml-auto rounded-lg bg-[#047857] px-4 py-2 text-sm font-medium text-white hover:bg-[#064e3b]"
            >
              Volver a mi chat →
            </Link>
          ) : (
            <Link
              href="/entrar"
              className="ml-auto rounded-lg border border-[#047857]/30 px-4 py-2 text-sm font-medium text-[#047857] transition hover:bg-[#047857]/5"
            >
              Ya tengo cuenta — entrar
            </Link>
          )}
        </div>
      </header>

      {/* Franja tricolor sutil */}
      <div className="flex h-1">
        <div className="w-1/3 bg-[#047857]" />
        <div className="w-1/3 bg-gray-200" />
        <div className="w-1/3 bg-[#c81e1e]" />
      </div>

      {/* Hero */}
      <section className="px-6 pb-12 pt-16 text-center">
        <div className="mx-auto max-w-2xl">
          <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-[#047857]">
            <Scale className="h-8 w-8 text-white" />
          </div>
          <h2 className="mb-4 font-serif text-4xl font-bold leading-tight text-gray-900 sm:text-5xl">
            La IA te orienta.{" "}
            <span className="text-[#047857]">El abogado te respalda.</span>
          </h2>
          <p className="mb-4 text-lg leading-relaxed text-gray-600">
            Cuenta tu caso en tus palabras. Nuestra IA mexicana lo analiza contra{" "}
            <strong>159,000+ leyes y jurisprudencias oficiales</strong> y te dice
            dónde estás parado — <strong>gratis y en minutos</strong>, no en semanas.
          </p>
          <p className="mb-8 text-base leading-relaxed text-gray-500">
            Y cuando tu caso necesita más que orientación,{" "}
            <strong className="text-gray-700">te enlazamos con un abogado verificado</strong>{" "}
            que ya conoce tu expediente y te da la respuesta formal.
          </p>

          <div className="flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              href="/para-ti"
              className="flex items-center gap-2 rounded-xl bg-[#047857] px-7 py-3.5 text-base font-semibold text-white shadow-lg shadow-[#047857]/20 transition hover:bg-[#064e3b]"
            >
              Iniciar mi consulta gratis
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/abogados"
              className="rounded-xl border border-gray-300 px-7 py-3.5 text-base font-semibold text-gray-700 transition hover:border-gray-400 hover:bg-gray-50"
            >
              Soy abogado
            </Link>
          </div>
          <p className="mt-4 text-xs text-gray-400">
            🇲🇽 Hecho en México · Español mexicano · Ley federal + 32 estados
          </p>
        </div>
      </section>

      {/* El problema / la solución */}
      <section className="bg-gray-50 px-6 py-12">
        <div className="mx-auto max-w-4xl">
          <div className="mb-10 grid gap-6 md:grid-cols-2">
            <div className="rounded-2xl border border-red-100 bg-red-50/50 p-6">
              <h3 className="mb-3 font-semibold text-gray-800">😔 Sin orientación legal…</h3>
              <ul className="space-y-2 text-sm text-gray-600">
                <li>✗ Una primera consulta cuesta $500–$2,500 y solo para escucharte</li>
                <li>✗ No sabes si tu caso es caso — ni por dónde empezar</li>
                <li>✗ Google te da respuestas de otros países o desactualizadas</li>
                <li>✗ El miedo a preguntar te deja peor de lo que empezaste</li>
              </ul>
            </div>
            <div className="rounded-2xl border border-[#047857]/20 bg-[#047857]/5 p-6">
              <h3 className="mb-3 font-semibold text-gray-800">🙂 Con AI Justicia…</h3>
              <ul className="space-y-2 text-sm text-gray-600">
                <li>✓ Platicas tu caso gratis, como se lo contarías a un amigo abogado</li>
                <li>✓ La IA entrevista, busca la ley de TU estado y cita artículos exactos</li>
                <li>✓ Sabes si tienes caso antes de gastar un peso</li>
                <li>✓ Si necesitas abogado, llega con tu expediente listo — y más barato</li>
              </ul>
            </div>
          </div>

          {/* Cómo funciona */}
          <h3 className="mb-8 text-center text-xl font-semibold text-gray-900">¿Cómo funciona?</h3>
          <div className="grid gap-6 md:grid-cols-3">
            <Paso
              icon={<MessageCircleQuestion className="h-6 w-6" />}
              num="1"
              titulo="Platica tu caso"
              texto="En lenguaje ciudadano. La IA te pregunta solo lo que la ley necesita: dónde pasa, quién está involucrado, fechas clave."
            />
            <Paso
              icon={<FileSearch className="h-6 w-6" />}
              num="2"
              titulo="La IA busca tu ley"
              texto="Analiza leyes federales, de tu estado y jurisprudencia del SJF. Si falta un dato que cambia el resultado, te lo pregunta."
            />
            <Paso
              icon={<Handshake className="h-6 w-6" />}
              num="3"
              titulo="Respuesta + abogado"
              texto="Orientación con citas verificadas. Y si tu caso va en serio, un abogado verificado lo retoma con tu expediente listo."
            />
          </div>
        </div>
      </section>

      {/* Las 3 rutas */}
      <section className="px-6 py-14">
        <div className="mx-auto max-w-5xl">
          <h3 className="mb-2 text-center text-2xl font-bold text-gray-900">¿Cómo te podemos ayudar?</h3>
          <p className="mb-10 text-center text-sm text-gray-500">
            Tres caminos, un mismo estándar: rigor jurídico mexicano.
          </p>

          <div className="grid gap-6 md:grid-cols-3">
            {/* Ciudadano */}
            <Ruta
              href="/para-ti"
              color="green"
              icon={<ShieldCheck className="h-6 w-6" />}
              titulo="Necesito apoyo legal"
              texto="Despido, pensión, renta, fraude, custodia… Orientación gratis con citas de la ley, y abogado cuando el caso lo amerita."
              items={["Primera orientación 100% gratis", "Expediente cifrado y privado", "Abogado verificado desde $100 MXN"]}
              cta="Iniciar mi consulta"
            />

            {/* Abogado */}
            <Ruta
              href="/abogados"
              color="red"
              icon={<BadgeCheck className="h-6 w-6" />}
              titulo="Soy abogado"
              texto="Consultas técnicas con fundamento al instante, generación de documentos y casos nuevos de tu especialidad."
              items={["Respuestas con artículos y SJF citados", "Contratos y demandas en minutos", "Recibe casos con expediente listo"]}
              cta="Crear mi cuenta"
            />

            {/* Despacho */}
            <Ruta
              href="/despachos"
              color="slate"
              icon={<Building2 className="h-6 w-6" />}
              titulo="Tengo un despacho"
              texto="Un modelo de IA privado entrenado solo con los casos de TU firma. Tu know-how jamás sale de tu despacho."
              items={["IA con el estilo de tu despacho", "Aislamiento total de tus datos", "Tu equipo más rápido, sin crecer nómina"]}
              cta="Registrar mi despacho"
            />
          </div>
        </div>
      </section>

      {/* Tlamatini — el motor */}
      <section className="border-t border-[#047857]/10 bg-gradient-to-b from-[#ecfdf5] to-white px-6 py-14">
        <div className="mx-auto max-w-3xl text-center">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[#047857]/30 bg-white px-4 py-1.5 text-xs font-medium text-[#047857]">
            <Sparkles className="h-3.5 w-3.5" />
            En construcción — primer release 2027
          </div>
          <h3 className="mb-3 font-serif text-3xl font-bold text-gray-900">
            Tlamatini
          </h3>
          <p className="mb-2 text-sm italic text-[#047857]">
            Del náhuatl <strong>tlamatini</strong> — "el que sabe": los sabios consejeros del México antiguo.
          </p>
          <p className="mx-auto mb-6 max-w-2xl text-sm leading-relaxed text-gray-600">
            El primer modelo de IA jurídica entrenado exclusivamente con derecho mexicano — leyes
            federales y de los 32 estados, jurisprudencia y doctrina. Cuando un modelo general
            <em> alucina</em> artículos, Tlamatini responde con la ley real y la cita exacta. Y como
            un sabio de verdad: <strong>si no sabe, lo dice</strong>.
          </p>
          <div className="grid gap-3 text-left sm:grid-cols-3">
            <div className="rounded-xl border border-[#047857]/15 bg-white p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-[#047857]">Soberano</p>
              <p className="mt-1 text-xs text-gray-600">
                Corre dentro del despacho. Ninguna consulta sale de la firma — compatible con el
                secreto profesional.
              </p>
            </div>
            <div className="rounded-xl border border-[#047857]/15 bg-white p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-[#047857]">Mexicano</p>
              <p className="mt-1 text-xs text-gray-600">
                Entrenado con miles de millones de tokens de fuentes oficiales: DOF, gacetas
                estatales, sentencias, IIJ-UNAM.
              </p>
            </div>
            <div className="rounded-xl border border-[#047857]/15 bg-white p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-[#047857]">Verificable</p>
              <p className="mt-1 text-xs text-gray-600">
                Cada afirmación con su cita. Sin respuestas inventadas — la honestidad es parte
                del diseño.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Confianza */}
      <section className="border-t border-gray-100 bg-gray-50 px-6 py-12">
        <div className="mx-auto max-w-4xl">
          <div className="grid gap-6 text-center sm:grid-cols-2 lg:grid-cols-4">
            <Dato icon={<MapPin className="h-5 w-5" />} titulo="100% mexicana" texto="Ley federal y de los 32 estados, en español mexicano." />
            <Dato icon={<BookOpenCheck className="h-5 w-5" />} titulo="Citas verificadas" texto="Cada afirmación se valida contra la fuente oficial." />
            <Dato icon={<Lock className="h-5 w-5" />} titulo="Privado por diseño" texto="Tu caso cifrado; tus archivos solo los abre tu llave." />
            <Dato icon={<UserCheck className="h-5 w-5" />} titulo="Abogados reales" texto="La IA apoya; la respuesta formal siempre es de un licenciado." />
          </div>
        </div>
      </section>

      {/* CTA final */}
      <section className="px-6 py-14 text-center">
        <h3 className="mb-3 text-2xl font-bold text-gray-900">Tu caso no se resuelve con dudas</h3>
        <p className="mb-7 text-gray-500">Empieza gratis hoy. Saber dónde estás parado no debe costar una fortuna.</p>
        <Link
          href="/para-ti"
          className="inline-flex items-center gap-2 rounded-xl bg-[#047857] px-8 py-4 text-base font-semibold text-white shadow-lg shadow-[#047857]/20 transition hover:bg-[#064e3b]"
        >
          Iniciar mi consulta gratis <ArrowRight className="h-4 w-4" />
        </Link>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-100 px-6 py-8 text-center">
        <p className="mx-auto max-w-2xl text-xs text-gray-400">
          ⚠️ El contenido generado por IA es exclusivamente informativo. No constituye
          asesoramiento legal ni sustituye la consulta con un abogado colegiado, quien
          es el único profesional autorizado para brindar orientación jurídica formal.
        </p>
        <p className="mt-3 text-[10px] font-medium text-[#047857]">
          🇲🇽 AI Justicia — Hecho en México, para México
        </p>
      </footer>
    </div>
  );
}

function Paso({ icon, num, titulo, texto }: { icon: React.ReactNode; num: string; titulo: string; texto: string }) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-6 text-center">
      <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-[#047857]/10 text-[#047857]">
        {icon}
      </div>
      <div className="mb-1 text-xs font-bold text-[#047857]">PASO {num}</div>
      <h4 className="mb-2 font-semibold text-gray-900">{titulo}</h4>
      <p className="text-sm leading-relaxed text-gray-500">{texto}</p>
    </div>
  );
}

function Ruta({
  href, color, icon, titulo, texto, items, cta,
}: {
  href: string;
  color: "green" | "red" | "slate";
  icon: React.ReactNode;
  titulo: string;
  texto: string;
  items: string[];
  cta: string;
}) {
  const styles = {
    green: {
      border: "border-[#047857]/20 hover:border-[#047857]/60",
      bg: "from-[#047857]/5",
      chip: "bg-[#047857]",
      soft: "bg-[#047857]/10 text-[#047857]",
      btn: "bg-[#047857] hover:bg-[#064e3b]",
    },
    red: {
      border: "border-[#c81e1e]/20 hover:border-[#c81e1e]/60",
      bg: "from-[#c81e1e]/5",
      chip: "bg-[#c81e1e]",
      soft: "bg-[#c81e1e]/10 text-[#c81e1e]",
      btn: "bg-[#c81e1e] hover:bg-[#a01717]",
    },
    slate: {
      border: "border-gray-300 hover:border-gray-500",
      bg: "from-gray-100",
      chip: "bg-gray-800",
      soft: "bg-gray-800/10 text-gray-700",
      btn: "bg-gray-900 hover:bg-gray-800",
    },
  }[color];

  return (
    <Link
      href={href}
      className={`flex flex-col rounded-2xl border-2 bg-gradient-to-b ${styles.bg} to-white p-6 transition ${styles.border}`}
    >
      <div className={`mb-4 flex h-12 w-12 items-center justify-center rounded-xl ${styles.chip}`}>
        {icon}
      </div>
      <h4 className="mb-2 text-lg font-bold text-gray-900">{titulo}</h4>
      <p className="mb-4 text-sm leading-relaxed text-gray-600">{texto}</p>
      <ul className="mb-5 space-y-1.5 text-xs text-gray-500">
        {items.map((i) => (
          <li key={i}>✓ {i}</li>
        ))}
      </ul>
      <span className={`mt-auto flex items-center justify-center gap-1.5 rounded-xl px-4 py-2.5 text-sm font-semibold text-white ${styles.btn}`}>
        {cta} <ArrowRight className="h-3.5 w-3.5" />
      </span>
    </Link>
  );
}

function Dato({ icon, titulo, texto }: { icon: React.ReactNode; titulo: string; texto: string }) {
  return (
    <div>
      <div className="mx-auto mb-2 flex h-9 w-9 items-center justify-center rounded-full bg-[#047857]/10 text-[#047857]">
        {icon}
      </div>
      <div className="text-sm font-semibold text-gray-800">{titulo}</div>
      <div className="mt-1 text-xs text-gray-500">{texto}</div>
    </div>
  );
}
