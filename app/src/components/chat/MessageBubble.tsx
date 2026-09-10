"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ShieldCheck, ShieldAlert, FileText, Scale, ChevronDown, ChevronUp, Printer, Share2 } from "lucide-react";
import type { Message } from "@/lib/store";
import { AnalysisCard } from "./AnalysisCard";
import { ClarifyCard } from "./ClarifyCard";

function Markdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: ({ children }) => <h1 className="mt-3 mb-2 text-base font-bold">{children}</h1>,
        h2: ({ children }) => <h2 className="mt-3 mb-1.5 text-sm font-bold">{children}</h2>,
        h3: ({ children }) => <h3 className="mt-2 mb-1 text-[13px] font-semibold">{children}</h3>,
        p: ({ children }) => <p className="my-1.5 leading-relaxed">{children}</p>,
        ul: ({ children }) => <ul className="my-1.5 ml-4 list-disc space-y-0.5">{children}</ul>,
        ol: ({ children }) => <ol className="my-1.5 ml-4 list-decimal space-y-0.5">{children}</ol>,
        li: ({ children }) => <li className="text-sm">{children}</li>,
        strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
        blockquote: ({ children }) => (
          <blockquote className="my-2 border-l-2 border-[#047857]/30 pl-3 text-gray-600">{children}</blockquote>
        ),
        a: ({ href, children }) => (
          <a href={href} target="_blank" rel="noopener" className="text-[#047857] underline hover:no-underline">{children}</a>
        ),
        hr: () => <hr className="my-3 border-gray-300" />,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

export function MessageBubble({
  msg,
  stage,
  isQuerying,
  onClarifySubmit,
}: {
  msg: Message;
  stage: import("@/lib/store").StageId | null;
  isQuerying: boolean;
  onClarifySubmit?: (respuestas: Record<string, string>) => void;
}) {
  const isUser = msg.role === "user";

  // Burbuja de ACLARACIÓN (preguntas interactivas; viejas = solo lectura)
  if (!isUser && msg.clarify) {
    return (
      <ClarifyCard
        clarify={msg.clarify}
        respondido={msg.respondido === true}
        onSubmit={(r) => onClarifySubmit?.(r)}
      />
    );
  }

  // Burbuja de REFERENCIAS (sin texto principal, solo done)
  if (!isUser && msg.done && !msg.text && !msg.isStreaming) {
    return <ReferencesCard done={msg.done} />;
  }

  // Burbuja de ABSTENCIÓN
  if (!isUser && msg.done?.abstenido && msg.text && !msg.isStreaming) {
    return <AbstencionCard text={msg.text} done={msg.done} />;
  }

  // Burbuja de ANÁLISIS (burbuja 1: etapas + materia) — persistente
  // Se identifica por tener analysisInfo. Se queda visible siempre.
  if (!isUser && msg.analysisInfo) {
    return (
      <AnalysisCard
        materia={msg.analysisInfo.materia || null}
        currentStage={stage}
        isQuerying={isQuerying}
      />
    );
  }

  // Burbuja de RESPUESTA vacía (aún no llega texto) — no renderizar nada
  if (!isUser && !msg.text && !msg.clarify && !msg.done && msg.isStreaming) {
    return null;
  }

  return (
    <div className={cn("flex gap-3 px-4 py-3", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-[#047857] text-white text-sm font-bold">
          AI
        </div>
      )}
      <div className={cn("max-w-[85%] rounded-2xl px-4 py-2.5", isUser ? "bg-[#047857] text-white" : "bg-gray-100 text-gray-900")}>
        {/* Texto del mensaje — markdown para Izel, texto plano para usuario */}
        {msg.text && (
          isUser ? (
            <div className="whitespace-pre-wrap text-sm leading-relaxed">
              {msg.text}
              {msg.isStreaming && <span className="ml-0.5 inline-block h-4 w-1 animate-pulse bg-gray-400" />}
            </div>
          ) : (
            <div className="text-sm leading-relaxed [&_*]:max-w-none">
              <Markdown content={msg.text} />
              {msg.isStreaming && <span className="ml-0.5 inline-block h-4 w-1 animate-pulse bg-gray-400" />}
            </div>
          )
        )}
      </div>
      {isUser && (
        <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-gray-300 text-gray-600 text-sm font-bold">
          Tú
        </div>
      )}
    </div>
  );
}

function ReferencesCard({ done }: { done: import("@/lib/streamQuery").DonePayload }) {
  const exportar = () => {
    const pasajes = (done.pasajes || [])
      .map((p, i) => `${i + 1}. ${p.titulo || p.fuente || "Fuente"}`)
      .join("\n");
    const texto = `AI JUSTICIA — Resumen de consulta\nFecha: ${new Date().toLocaleDateString("es-MX")}\n\nRESPUESTA:\n${done.respuesta}\n\nFUENTES VERIFICADAS (${done.n_sustentadas}/${done.n_oraciones} oraciones con cita):\n${pasajes}\n\nEste documento no sustituye asesoría legal profesional.`;
    // Abrir vista imprimible en ventana nueva (Guardar como PDF)
    const w = window.open("", "_blank", "width=800,height=900");
    if (w) {
      w.document.write(`<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><title>Consulta AI Justicia</title>
<style>body{font-family:Georgia,serif;max-width:720px;margin:2rem auto;padding:0 1rem;color:#1f2937;line-height:1.7}
h1{color:#047857;font-size:1.3rem}pre{white-space:pre-wrap;font-family:inherit;font-size:.95rem;background:#f9fafb;padding:1rem;border-radius:.5rem;border:1px solid #e5e7eb}
small{color:#6b7280}</style></head><body>
<h1>⚖️ AI Justicia — Resumen de consulta</h1>
<pre>${texto.replace(/[<>&]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c] || c))}</pre>
<small>Generado por aijusticia.mx — orientación jurídica con fuentes verificadas. No sustituye asesoría profesional.</small>
<script>window.print()<\/script></body></html>`);
      w.document.close();
    }
  };

  const compartir = async () => {
    const resumen = `Consulta AI Justicia:\n\n${(done.respuesta || "").slice(0, 600)}…\n\nCon ${done.n_sustentadas} citas verificadas — aijusticia.mx`;
    if (navigator.share) {
      try {
        await navigator.share({ title: "Consulta AI Justicia", text: resumen });
      } catch { /* cancelado */ }
    } else {
      navigator.clipboard?.writeText(resumen);
    }
  };

  return (
    <div className="flex gap-3 px-4 py-2">
      <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-[#d1fae5]">
        <ShieldCheck className="h-4 w-4 text-[#047857]" />
      </div>
      <div className="max-w-[85%] rounded-2xl border border-gray-200 bg-white px-4 py-3">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-gray-600">
          <FileText className="h-3.5 w-3.5" />
          Referencias legales verificadas
        </div>

        {/* Score de verificación */}
        <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-gray-400">
          <ShieldCheck className="h-3 w-3" />
          {done.n_sustentadas}/{done.n_oraciones} oraciones con cita verificada
        </div>

        {/* Lista de fuentes expandibles */}
        <div className="mt-2 space-y-1.5">
          {done.pasajes?.slice(0, 5).map((p, i) => (
            <ExpandiblePasaje key={i} indice={i} pasaje={p} />
          ))}
        </div>

        {/* Exportar / compartir */}
        <div className="mt-3 flex gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={exportar}
            className="flex-1 gap-2 border-[#047857]/30 text-[#047857] hover:bg-[#ecfdf5]"
          >
            <Printer className="h-3.5 w-3.5" />
            Exportar PDF
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={compartir}
            className="flex-1 gap-2 border-gray-200 text-gray-600 hover:bg-gray-50"
          >
            <Share2 className="h-3.5 w-3.5" />
            Compartir
          </Button>
        </div>

        {/* Botón siempre presente: consultar abogado */}
        <a href="/para-ti" className="mt-2 block">
          <Button size="sm" className="w-full gap-2 bg-[#047857] hover:bg-[#064e3b]">
            <Scale className="h-3.5 w-3.5" />
            Validar con un abogado
          </Button>
        </a>
      </div>
    </div>
  );
}

function AbstencionCard({ text, done }: { text: string; done: import("@/lib/streamQuery").DonePayload }) {
  const isDownloading = done.tipo_abstencion === "NORMA_FALTANTE" && done.job_id;
  return (
    <div className="flex gap-3 px-4 py-2">
      <div className={cn(
        "flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full",
        isDownloading ? "bg-blue-100" : "bg-amber-100",
      )}>
        {isDownloading ? (
          <FileText className="h-4 w-4 text-blue-600 animate-pulse" />
        ) : (
          <ShieldAlert className="h-4 w-4 text-amber-600" />
        )}
      </div>
      <div className={cn(
        "max-w-[85%] rounded-2xl border px-4 py-3",
        isDownloading ? "border-blue-200 bg-blue-50" : "border-amber-200 bg-amber-50",
      )}>
        {isDownloading ? (
          <>
            <div className="flex items-center gap-2 text-xs font-semibold text-blue-800">
              <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-blue-400 border-t-blue-700" />
              Investigando leyes vigentes...
            </div>
            <p className="mt-1.5 text-sm leading-relaxed text-blue-900">{text}</p>
            <p className="mt-2 text-xs text-blue-700">
              Estoy descargando la normativa aplicable para darte una respuesta precisa.
              Esto puede tardar unos minutos. Tu consulta es la <strong>#{done.job_id}</strong>.
            </p>
            <div className="mt-2 flex items-center gap-1.5 text-[11px] text-blue-500">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-blue-400" />
              En proceso — te avisaré cuando esté lista
            </div>
          </>
        ) : (
          <>
            <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-800">
              <ShieldAlert className="h-3.5 w-3.5" />
              Requiere asesoría de un abogado
            </div>
            <p className="mt-1.5 text-sm leading-relaxed text-amber-900">{text}</p>
          </>
        )}
        <a href="/para-ti" className="mt-3 block">
          <Button size="sm" className={cn(
            "w-full gap-2",
            isDownloading ? "bg-blue-600 hover:bg-blue-700" : "bg-amber-600 hover:bg-amber-700",
          )}>
            <Scale className="h-3.5 w-3.5" />
            {isDownloading ? "Mientras tanto, hablar con un abogado" : "Hablar con un abogado ahora"}
          </Button>
        </a>
      </div>
    </div>
  );
}

function ExpandiblePasaje({ indice, pasaje }: {
  indice: number;
  pasaje: { titulo: string; fuente: string; clave_cita: string; vinculante: boolean; fragmento: string; jerarquia: number };
}) {
  const [expandido, setExpandido] = useState(false);

  return (
    <div className="rounded-lg border border-gray-100 bg-gray-50/50">
      {/* Header clickeable */}
      <button
        onClick={() => setExpandido(!expandido)}
        className="flex w-full items-start gap-1.5 p-2 text-left text-xs hover:bg-gray-100/50 rounded-lg transition-colors"
      >
        <Badge
          variant="outline"
          className={cn(
            "flex-shrink-0 gap-0.5 text-[10px]",
            pasaje.vinculante ? "border-green-300 bg-green-50 text-green-700" : "border-gray-300 bg-gray-50 text-gray-500",
          )}
        >
          [{indice + 1}]
        </Badge>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1">
            <span className="font-medium text-gray-700">{pasaje.fuente}</span>
            {pasaje.vinculante && <ShieldCheck className="h-3 w-3 text-green-600" />}
            {expandido
              ? <ChevronUp className="ml-auto h-3 w-3 flex-shrink-0 text-gray-400" />
              : <ChevronDown className="ml-auto h-3 w-3 flex-shrink-0 text-gray-400" />}
          </div>
          <p className="line-clamp-1 text-gray-500">{pasaje.titulo}</p>
        </div>
      </button>

      {/* Fragmento expandible */}
      {expandido && pasaje.fragmento && (
        <div className="border-t border-gray-100 px-3 py-2">
          <p className="mb-1 text-[11px] font-medium text-gray-400">Fragmento de la fuente:</p>
          <p className="max-h-48 overflow-y-auto whitespace-pre-wrap text-xs leading-relaxed text-gray-600">
            {pasaje.fragmento}
          </p>
        </div>
      )}
    </div>
  );
}
