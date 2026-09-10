"use client";

/**
 * IzelPanel — panel flotante anclado a la derecha, ancho ajustable.
 * - Chat persistente por caso (visible a todos los participantes)
 * - Cada mensaje muestra AUTOR + TIMESTAMP
 * - Markdown renderizado
 * - Spinner prominente cuando Izel está procesando
 * - Drag para redimensionar (280-640px)
 */
import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ChevronRight, Loader2, Mic, MicOff, Send, Sparkles, Volume2, VolumeX, X, Bot, User,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n";

interface Msg {
  rol: "user" | "izel";
  texto: string;
  citas?: string[] | null;
  creado_en?: string;
  autor?: string;
}

const WIDTH_KEY = "aij_izel_width";
const OPEN_KEY = "aij_izel_open";
const MIN_W = 280;
const MAX_W = 640;

// ── Markdown renderer ─────────────────────────────────────────────────────

function Markdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: ({ children }) => <h1 className="mt-3 mb-2 text-base font-bold text-foreground">{children}</h1>,
        h2: ({ children }) => <h2 className="mt-3 mb-1.5 text-sm font-bold text-foreground">{children}</h2>,
        h3: ({ children }) => <h3 className="mt-2 mb-1 text-[13px] font-semibold text-foreground">{children}</h3>,
        p: ({ children }) => <p className="my-1.5 leading-relaxed">{children}</p>,
        ul: ({ children }) => <ul className="my-1.5 ml-4 list-disc space-y-0.5">{children}</ul>,
        ol: ({ children }) => <ol className="my-1.5 ml-4 list-decimal space-y-0.5">{children}</ol>,
        li: ({ children }) => <li className="text-[13px]">{children}</li>,
        strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
        blockquote: ({ children }) => (
          <blockquote className="my-2 border-l-2 border-primary/30 pl-3 text-muted-foreground">{children}</blockquote>
        ),
        code: ({ children, className }) => {
          if (className?.includes("language-")) {
            return (
              <code className="my-2 block overflow-x-auto rounded-lg bg-muted p-3 text-[12px] font-mono text-foreground">
                {children}
              </code>
            );
          }
          return <code className="rounded bg-muted px-1 py-0.5 font-mono text-[12px]">{children}</code>;
        },
        pre: ({ children }) => <pre className="overflow-x-auto">{children}</pre>,
        table: ({ children }) => (
          <div className="my-2 overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-[12px]">{children}</table>
          </div>
        ),
        th: ({ children }) => (
          <th className="border-b border-border bg-muted px-2.5 py-1.5 text-left font-semibold text-foreground">{children}</th>
        ),
        td: ({ children }) => (
          <td className="border-b border-border/50 px-2.5 py-1.5 text-foreground">{children}</td>
        ),
        hr: () => <hr className="my-3 border-border" />,
        a: ({ href, children }) => (
          <a href={href} target="_blank" rel="noopener" className="text-primary underline hover:no-underline">{children}</a>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

// ── Loading overlay prominente ────────────────────────────────────────────

function ThinkingOverlay() {
  const [segundos, setSegundos] = useState(0);
  useEffect(() => {
    const iv = setInterval(() => setSegundos((s) => s + 1), 1000);
    return () => clearInterval(iv);
  }, []);
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-6">
      <div className="relative">
        <div className="size-16 rounded-full border-4 border-primary/20" />
        <div className="absolute inset-0 size-16 rounded-full border-4 border-transparent border-t-primary animate-spin" />
        <Sparkles className="absolute inset-0 m-auto size-6 text-primary" />
      </div>
      <p className="text-[13px] font-medium text-foreground">Izel está pensando…</p>
      <p className="text-[11px] text-muted-foreground">
        {segundos < 15 ? "Buscando en el corpus jurídico" :
         segundos < 45 ? "Analizando documentos del caso" :
         segundos < 90 ? "Generando respuesta detallada" :
         `Procesando — ${segundos}s`}
      </p>
      <div className="h-1 w-40 overflow-hidden rounded-full bg-muted">
        <div className="h-full w-1/3 animate-pulse rounded-full bg-primary" />
      </div>
    </div>
  );
}

// ── Mensaje individual con autor y timestamp ──────────────────────────────

function Mensaje({ m }: { m: Msg }) {
  const esUser = m.rol === "user";
  const hora = m.creado_en
    ? new Date(m.creado_en).toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" })
    : "";
  return (
    <div className={cn("flex gap-2", esUser ? "flex-row-reverse" : "")}>
      {/* avatar */}
      <div className={cn(
        "flex size-6 shrink-0 items-center justify-center rounded-full text-[9px] font-bold mt-1",
        esUser ? "bg-blue-500/20 text-blue-600" : "bg-gradient-to-br from-primary to-teal-500 text-white"
      )}>
        {esUser ? <User className="size-3" /> : <Bot className="size-3" />}
      </div>
      <div className={cn("min-w-0 max-w-[85%]", esUser ? "items-end" : "")}>
        {/* autor + hora */}
        <div className={cn("mb-0.5 flex items-center gap-1.5", esUser && "flex-row-reverse")}>
          <span className="text-[10px] font-medium text-foreground">
            {esUser ? (m.autor || "Tú") : "Izel"}
          </span>
          {hora && <span className="text-[9px] text-muted-foreground">{hora}</span>}
        </div>
        {/* contenido */}
        <div className={cn(
          "rounded-xl px-3 py-2.5",
          esUser ? "bg-primary/10" : "bg-muted/80"
        )}>
          {esUser ? (
            <p className="text-[13px] whitespace-pre-wrap">{m.texto}</p>
          ) : (
            <div className="text-[13px]"><Markdown content={m.texto} /></div>
          )}
        </div>
        {/* citas */}
        {m.citas && m.citas.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {m.citas.map((c: string, j: number) => (
              <span key={j} className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[9px] text-primary">{c}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── STT: Chrome SpeechRecognition ──

function getRecognition(): any {
  const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
  if (!SR) return null;
  const rec = new SR();
  rec.lang = "es-MX";
  rec.interimResults = true;
  rec.continuous = false;
  return rec;
}

function limpiarMarkdown(md: string): string {
  return md
    .replace(/#{1,6}\s/g, "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/`{3}[^`]*`{3}/g, "")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\n{2,}/g, ". ")
    .replace(/\n/g, ", ")
    .replace(/[#|>\-]{2,}/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim()
    .slice(0, 2000);
}

// ── Panel principal ───────────────────────────────────────────────────────

export function IzelPanel({ casoNombre, casoId }: { casoNombre?: string | null; casoId?: string | null }) {
  const t = useT();
  const [open, setOpen] = useState(true);
  const [width, setWidth] = useState(380);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [cargandoChat, setCargandoChat] = useState(false);
  const [input, setInput] = useState("");
  const [escribiendo, setEscribiendo] = useState(false);
  const [ttsOn, setTtsOn] = useState(() => localStorage.getItem("aij_tts") === "1");
  const [escuchando, setEscuchando] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);

  // cargar preferencias
  useEffect(() => {
    const w = localStorage.getItem(WIDTH_KEY);
    if (w) setWidth(Math.max(MIN_W, Math.min(MAX_W, parseInt(w))));
    const o = localStorage.getItem(OPEN_KEY);
    if (o === "0") setOpen(false);
  }, []);

  useEffect(() => {
    localStorage.setItem(OPEN_KEY, open ? "1" : "0");
  }, [open]);

  const speak = useCallback(async (texto: string) => {
    if (!ttsOn) return;
    try {
      const raw = sessionStorage.getItem("aij_tokens");
      const tk = raw ? JSON.parse(raw) : null;
      const r = await fetch("/tts", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(tk?.access ? { Authorization: `Bearer ${tk.access}` } : {}),
        },
        body: JSON.stringify({ text: limpiarMarkdown(texto) }),
      });
      if (r.ok) {
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audio.play().catch(() => {});
      }
    } catch { /* silencioso */ }
  }, [ttsOn]);

  // cargar chat persistente del caso
  useEffect(() => {
    if (!casoId || !open) { setMsgs([]); return; }
    setCargandoChat(true);
    const raw = sessionStorage.getItem("aij_tokens");
    const tk = raw ? JSON.parse(raw) : null;
    fetch(`/bufetes/casos/${casoId}/chat`, {
      headers: tk?.access ? { Authorization: `Bearer ${tk.access}` } : {},
    })
      .then((r) => (r.ok ? r.json() : { mensajes: [] }))
      .then((d) => setMsgs(d.mensajes ?? []))
      .catch(() => setMsgs([]))
      .finally(() => setCargandoChat(false));
  }, [casoId, open]);

  // auto-scroll
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [msgs, escribiendo]);

  // guardar mensaje en DB
  const persistir = useCallback(async (casoId: string, rol: string, texto: string, citas?: string[]) => {
    const raw = sessionStorage.getItem("aij_tokens");
    const tk = raw ? JSON.parse(raw) : null;
    await fetch(`/bufetes/casos/${casoId}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(tk?.access ? { Authorization: `Bearer ${tk.access}` } : {}),
      },
      body: JSON.stringify({ rol, texto, citas: citas || null }),
    }).catch(() => {});
  }, []);

  const enviar = async () => {
    const q = input.trim();
    if (!q || escribiendo) return;
    setMsgs((m) => [...m, { rol: "user", texto: q }]);
    setInput("");
    setEscribiendo(true);

    // persistir mensaje del usuario
    if (casoId) persistir(casoId, "user", q);

    try {
      const raw = sessionStorage.getItem("aij_tokens");
      const tk = raw ? JSON.parse(raw) : null;
      const r = await fetch("/bufetes/studio/query", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(tk?.access ? { Authorization: `Bearer ${tk.access}` } : {}),
        },
        body: JSON.stringify({ consulta: q, caso_id: casoId || null }),
      });
      if (r.ok) {
        const d = await r.json();
        const citas = (d.pasajes ?? []).slice(0, 3).map((p: any) =>
          `${p.titulo?.slice(0, 40) ?? ""} (${p.fuente ?? ""})`
        );
        const textoRespuesta = d.respuesta || "...";
        setMsgs((m) => [...m, {
          rol: "izel", texto: textoRespuesta,
          citas: citas.length > 0 ? citas : d.tool_calls_ejecutados?.map((tc: any) => `${tc.tool} ✓`).slice(0, 3),
          creado_en: new Date().toISOString(),
        }]);
        speak(textoRespuesta);
        if (casoId) persistir(casoId, "izel", d.respuesta || "...", citas);
        // ejecutar accion_ui (navegar, refrescar, etc.)
        if (d.accion_ui) {
          const au = d.accion_ui;
          if (au.tipo === "navegar" && au.destino) {
            window.dispatchEvent(new CustomEvent("izel-navigate", { detail: au }));
          } else if (au.tipo === "refresh") {
            window.dispatchEvent(new CustomEvent("izel-refresh"));
          }
        }
      } else {
        setMsgs((m) => [...m, { rol: "izel", texto: "Error de conexión." }]);
      }
    } catch {
      setMsgs((m) => [...m, { rol: "izel", texto: "Error de conexión." }]);
    } finally {
      setEscribiendo(false);
    }
  };

  // drag para redimensionar
  const onDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = width;
    const onMove = (ev: MouseEvent) => {
      const delta = startX - ev.clientX;
      setWidth(Math.max(MIN_W, Math.min(MAX_W, startW + delta)));
    };
    const onUp = () => {
      localStorage.setItem(WIDTH_KEY, String(width));
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [width]);

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-40 flex size-14 items-center justify-center rounded-full
          bg-gradient-to-br from-primary to-teal-500 text-white shadow-lg transition-transform
          hover:scale-105 active:scale-95"
        title="Abrir Izel"
      >
        <Sparkles className="size-6" />
      </button>
    );
  }

  return (
    <div
      className="fixed inset-y-0 right-0 z-30 flex flex-col border-l border-border bg-background shadow-2xl"
      style={{ width }}
    >
      {/* handle resize */}
      <div
        onMouseDown={onDragStart}
        className="absolute inset-y-0 left-0 z-10 w-1.5 cursor-col-resize transition-colors hover:bg-primary/30"
        title="Arrastra para redimensionar"
      />

      {/* header */}
      <div className="flex items-center gap-2 border-b border-border px-3 py-2.5">
        <span className="flex size-7 items-center justify-center rounded-full bg-gradient-to-br from-primary to-teal-500 text-[11px] font-bold text-white">
          I
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-semibold text-foreground">Izel</p>
          {casoNombre && <p className="truncate text-[9px] text-muted-foreground">{casoNombre}</p>}
        </div>
        <button onClick={() => setOpen(false)}
          className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground">
          <ChevronRight className="size-4" />
        </button>
        <button onClick={() => setOpen(false)}
          className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground">
          <X className="size-4" />
        </button>
      </div>

      {/* mensajes */}
      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-3.5 py-3">
        {cargandoChat ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="size-5 animate-spin text-primary" />
          </div>
        ) : msgs.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-8 text-center">
            <span className="flex size-12 items-center justify-center rounded-full bg-gradient-to-br from-primary to-teal-500 text-base font-bold text-white">I</span>
            <p className="text-[14px] font-semibold text-foreground">{t("izel.hola")}</p>
            <p className="text-[11px] leading-relaxed text-muted-foreground">{t("izel.descripcion")}</p>
          </div>
        ) : (
          msgs.map((m, i) => <Mensaje key={i} m={m} />)
        )}

        {/* overlay de "pensando" */}
        {escribiendo && <ThinkingOverlay />}
      </div>

      {/* input */}
      <div className="border-t border-border p-3">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(); } }}
            rows={2}
            placeholder={t("izel.placeholder")}
            className="min-h-[40px] flex-1 resize-none rounded-lg border border-input bg-background px-3 py-2 text-[12.5px] text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
          />
          <button onClick={enviar} disabled={!input.trim() || escribiendo}
            className="rounded-lg bg-primary p-2.5 text-primary-foreground disabled:opacity-40">
            <Send className="size-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
