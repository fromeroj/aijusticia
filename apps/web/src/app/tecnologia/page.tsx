"use client";

import Link from "next/link";
import {
  Scale, ArrowLeft, ArrowRight, Lock, Brain, Server, Database,
  FileText, GitBranch, MessageSquareText, ShieldCheck,
} from "lucide-react";
import { Mermaid } from "@/components/Mermaid";

const DIAGRAMA_SOBERANIA = `flowchart LR
    U[Usuario del despacho] --> Q[Consulta jurídica]
    Q --> R[RAG: 2.9B tokens<br/>ley + jurisprudencia + doctrina]
    R --> T[Tlamatini<br/>corre AQUI dentro del despacho]
    T --> A[Respuesta con citas verificadas]
    style T fill:#ecfdf5,stroke:#047857
    style R fill:#f0fdf4,stroke:#047857`;

const DIAGRAMA_ADAPTER = `flowchart TB
    subgraph TU["Tu despacho — perímetro sellado"]
        D1[Documentos y casos] --> D2{PII-scan<br/>automático}
        D2 -->|datos personales| D3[(Expediente del caso<br/>aislado, confidencial)]
        D2 -->|conocimiento anónimo| D4[Plantillas y<br/>cláusulas de la firma]
        D4 --> L[Adapter privado<br/>Tlamatini-bufete-TUYO]
        L --> T2[Tlamatini local]
    end
    T2 --> R2[La IA habla con el estilo<br/>de TU despacho]
    style L fill:#fef3c7,stroke:#f59e0b
    style D3 fill:#fee2e2,stroke:#ef4444`;

const DIAGRAMA_DATOS = `flowchart TB
    C[Caso: acta constitutiva<br/>con datos reales del cliente] --> S{Promover a plantilla}
    S --> P[PII-scan: nombres, RFC,<br/>capital → DENOMINACIÓN, CAPITAL]
    P --> H[Revisión del socio]
    H -->|aprueba| B[Biblioteca de la firma<br/>Acta SA v4.0]
    H -->|rechaza| C
    B --> L2[El adapter aprende:<br/>esta casa usa mayoría calificada]
    style B fill:#ecfdf5,stroke:#047857
    style L2 fill:#fef3c7,stroke:#f59e0b`;

export default function TecnologiaPage() {
  return (
    <div className="min-h-screen bg-white">
      <header className="border-b border-gray-100 px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center gap-2">
          <Link href="/" className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#047857]">
            <Scale className="h-5 w-5 text-white" />
          </Link>
          <span className="text-sm font-semibold text-gray-900">AI Justicia</span>
          <Link href="/" className="ml-auto flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600">
            <ArrowLeft className="h-3.5 w-3.5" /> Inicio
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section className="bg-gradient-to-b from-[#ecfdf5] to-white px-6 py-14">
        <div className="mx-auto max-w-3xl text-center">
          <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-[#047857]">Tecnología</p>
          <h1 className="mb-4 font-serif text-4xl font-bold text-gray-900">
            Dos promesas que nadie más puede cumplir
          </h1>
          <p className="mx-auto max-w-2xl text-sm leading-relaxed text-gray-600">
            Una IA jurídica <strong>soberana</strong> que corre dentro de tu despacho, y
            <strong> adaptadores privados</strong> que aprenden de tu práctica sin que un solo dato
            salga de la firma. Esto no es una política de privacidad — es arquitectura.
          </p>
        </div>
      </section>

      {/* Diferenciador 1 */}
      <section className="border-t border-gray-100 px-6 py-14">
        <div className="mx-auto max-w-4xl">
          <div className="mb-6 flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#047857]">
              <Server className="h-6 w-6 text-white" />
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-[#047857]">Diferenciador 1</p>
              <h2 className="text-2xl font-bold text-gray-900">LLM soberana: la inferencia nunca sale</h2>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-gray-600">
                Harvey, Legora, CoCounsel: todos procesan tus consultas en sus nubes. Nosotros
                desplegamos <strong>Tlamatini dentro de tu infraestructura</strong> — una GPU de
                24GB basta. Secreto profesional (arts. 210-211 CPF) y LFPDPPP cumplidos por
                construcción, no por contrato.
              </p>
            </div>
          </div>
          <Mermaid chart={DIAGRAMA_SOBERANIA} />
        </div>
      </section>

      {/* Diferenciador 2 */}
      <section className="border-t border-gray-100 bg-gray-50/60 px-6 py-14">
        <div className="mx-auto max-w-4xl">
          <div className="mb-6 flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#f59e0b]">
              <Brain className="h-6 w-6 text-white" />
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-[#b45309]">Diferenciador 2</p>
              <h2 className="text-2xl font-bold text-gray-900">
                Adaptadores locales: aprendemos a ser un miembro más
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-gray-600">
                Los incumbentes presumen <em>"zero AI training on your data"</em>. Nosotros
                entrenamos — <strong>pero solo para ti</strong>. Tus documentos alimentan un adapter
                privado que vive en tu perímetro; la IA adopta el estilo, los criterios y las
                estrategias de TU casa. Cuando un asociado se va, ese aprendizaje se queda.
              </p>
            </div>
          </div>
          <Mermaid chart={DIAGRAMA_ADAPTER} />
        </div>
      </section>

      {/* Cómo fluyen los datos */}
      <section className="border-t border-gray-100 px-6 py-14">
        <div className="mx-auto max-w-4xl">
          <div className="mb-6 text-center">
            <h2 className="text-2xl font-bold text-gray-900">La política de datos, en un flujo</h2>
            <p className="mx-auto mt-2 max-w-xl text-sm text-gray-500">
              El ejemplo del acta constitutiva: el caso tiene datos reales; la plantilla de la firma
              jamás los contiene.
            </p>
          </div>
          <Mermaid chart={DIAGRAMA_DATOS} />
        </div>
      </section>

      {/* Documentos */}
      <section className="border-t border-gray-100 bg-gray-900 px-6 py-14">
        <div className="mx-auto max-w-4xl">
          <h2 className="mb-8 text-center text-2xl font-bold text-white">
            Documentos con memoria de firma
          </h2>
          <div className="grid gap-4 sm:grid-cols-3">
            {[
              { icon: GitBranch, t: "Versionado real", d: "Cada guardado es una versión con autor, diff visual (redline) y restauración. Nada se pierde nunca." },
              { icon: MessageSquareText, t: "Edición y comentarios", d: "Markdown con el stylesheet de tu despacho; comentarios inline con hilos por cláusula, como el equipo ya revisa." },
              { icon: FileText, t: "Plantillas que aprenden", d: "Cada documento cerrado puede promoverse a plantilla — anonimizado automáticamente, aprobado por un socio." },
            ].map((x) => (
              <div key={x.t} className="rounded-2xl border border-white/10 bg-white/5 p-5">
                <x.icon className="mb-3 h-6 w-6 text-[#6ee7b7]" />
                <p className="text-sm font-semibold text-white">{x.t}</p>
                <p className="mt-1 text-xs leading-relaxed text-gray-300">{x.d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Cumplimiento */}
      <section className="border-t border-gray-100 px-6 py-14">
        <div className="mx-auto max-w-4xl">
          <div className="mb-8 flex items-center gap-3">
            <ShieldCheck className="h-6 w-6 text-[#047857]" />
            <h2 className="text-2xl font-bold text-gray-900">Cumplimiento que se demuestra</h2>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-2xl border border-gray-100 bg-white p-5">
              <p className="text-sm font-semibold text-gray-800">Inventario LFPDPPP automático</p>
              <p className="mt-1 text-xs leading-relaxed text-gray-500">
                Qué datos personales trata el despacho, dónde, con qué finalidad y retención —
                exportable como anexo de cumplimiento, actualizado al día.
              </p>
            </div>
            <div className="rounded-2xl border border-gray-100 bg-white p-5">
              <p className="text-sm font-semibold text-gray-800">Derechos ARDPC implementados</p>
              <p className="mt-1 text-xs leading-relaxed text-gray-500">
                El ciudadano accede, rectifica y solicita borrado — y el borrado funciona: datos
                personales fuera, conocimiento anónimo de la firma preservado.
              </p>
            </div>
            <div className="rounded-2xl border border-gray-100 bg-white p-5">
              <p className="text-sm font-semibold text-gray-800">Auditoría por caso</p>
              <p className="mt-1 text-xs leading-relaxed text-gray-500">
                Quién vio qué y cuándo — registro inmutable, esencial cuando el caso es "solo socios".
              </p>
            </div>
            <div className="rounded-2xl border border-gray-100 bg-white p-5">
              <p className="text-sm font-semibold text-gray-800">Aislamiento verificable</p>
              <p className="mt-1 text-xs leading-relaxed text-gray-500">
                Row-Level Security de PostgreSQL a nivel de fila: tus datos técnicos y
                contractualmente separados de cualquier otro bufete.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-gray-100 bg-[#ecfdf5] px-6 py-12">
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="mb-3 text-xl font-bold text-gray-900">
            La IA legal que tu despacho controla
          </h2>
          <div className="flex flex-wrap justify-center gap-3">
            <Link href="/despachos" className="flex items-center gap-2 rounded-xl bg-[#047857] px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#036c4c]">
              Conocer el plan despachos <ArrowRight className="h-4 w-4" />
            </Link>
            <Link href="/tlamatini" className="flex items-center gap-2 rounded-xl border border-[#047857]/30 px-5 py-3 text-sm font-medium text-[#047857] transition hover:bg-white">
              Conocer a Tlamatini
            </Link>
          </div>
        </div>
      </section>

      <footer className="px-6 py-6 text-center">
        <p className="text-[10px] text-gray-400">
          AI Justicia — orientación jurídica con fuentes verificadas. No sustituye la asesoría de un
          abogado con cédula profesional.
        </p>
      </footer>
    </div>
  );
}
