"use client";

/**
 * /studio — la nueva app de trabajo (reemplaza /app).
 * Layout: Sidebar + Topbar + Main + IzelRail.
 * Login dual: Despacho (NC) | Abogado (frase).
 * i18n es/en + dark/light mode.
 */
import { useEffect, useState, useCallback } from "react";
import { Scale, KeyRound, Loader2, Building2, LogIn, AlertCircle, Languages } from "lucide-react";
import { StudioShell, type StudioPage } from "@/components/studio/Shell";
import { CasesPage } from "@/components/studio/CasesPage";
import {
  DashboardPage, ClientsPage, LibraryPage, AgendaPage,
  ConflictsPage, SettingsPage,
} from "@/components/studio/Pages";
import { useT, useLang } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";

type Tokens = { access: string; refresh: string };

function leerTokens(): Tokens | null {
  try {
    const raw = sessionStorage.getItem("aij_tokens");
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

const TITULOS: Record<StudioPage, [string, string?]> = {
  panel: ["Panel del despacho", ""],
  casos: ["Casos", "El caso es el centro de todo"],
  clientes: ["Clientes", "Directorio"],
  biblioteca: ["Biblioteca", "Plantillas · memos"],
  agenda: ["Agenda y plazos", "Términos fatales primero"],
  tiempo: ["Tiempo y honorarios", "Registro"],
  conflictos: ["Verificación de conflictos", "Cumplimiento"],
  ajustes: ["Ajustes", ""],
};

export default function StudioPage() {
  const t = useT();
  const [lang, setLang] = useLang();
  const [theme] = useTheme();
  const [tokens, setTokens] = useState<Tokens | null>(null);
  const [usuario, setUsuario] = useState("");
  const [firma, setFirma] = useState("");
  const [page, setPage] = useState<StudioPage>("casos");
  const [casoNombre, setCasoNombre] = useState<string | null>(null);
  const [casoId, setCasoId] = useState<string | null>(null);
  const [nuevoCasoOpen, setNuevoCasoOpen] = useState(false);
  const [loginForm, setLoginForm] = useState({ user: "", pass: "", frase: "" });
  const [loginError, setLoginError] = useState("");
  const [logueando, setLogueando] = useState(false);
  const [modoLogin, setModoLogin] = useState<"despacho" | "abogado">("despacho");

  useEffect(() => {
    const tk = leerTokens();
    if (tk) {
      setTokens(tk);
      setUsuario(sessionStorage.getItem("aij_usuario") || "");
    }
  }, []);

  const api = useCallback(async (path: string, init?: RequestInit) => {
    const tk = leerTokens();
    return fetch(path, {
      ...init,
      headers: { ...init?.headers, ...(tk?.access ? { Authorization: `Bearer ${tk.access}` } : {}) },
    });
  }, []);

  const salir = useCallback(() => {
    sessionStorage.removeItem("aij_tokens");
    sessionStorage.removeItem("aij_usuario");
    setTokens(null);
  }, []);

  const login = async (e: React.FormEvent) => {
    e.preventDefault();
    setLogueando(true); setLoginError("");
    try {
      const body = modoLogin === "despacho"
        ? JSON.stringify({ via: "nc", user: loginForm.user.trim(), credential: loginForm.pass })
        : JSON.stringify({ via: "frase", credential: loginForm.frase.trim() });
      const r = await fetch("/auth/token", {
        method: "POST", headers: { "Content-Type": "application/json" }, body,
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        setLoginError(d.detail || "Error");
        return;
      }
      const d = await r.json();
      const tk: Tokens = { access: d.access_token, refresh: d.refresh_token };
      sessionStorage.setItem("aij_tokens", JSON.stringify(tk));
      sessionStorage.setItem("aij_usuario", modoLogin === "despacho" ? loginForm.user.trim() : "abogado");
      setUsuario(modoLogin === "despacho" ? loginForm.user.trim() : "abogado");
      setLoginForm({ user: "", pass: "", frase: "" });
      setTokens(tk);
    } catch { setLoginError("Error de conexión"); }
    finally { setLogueando(false); }
  };

  const crearCaso = async (nombre: string, materia: string) => {
    await api("/bufetes/casos", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nombre, materia: materia || null }),
    }).catch(() => null);
  };

  // ── LOGIN ──
  if (!tokens) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <form onSubmit={login} className="w-full max-w-sm rounded-2xl border border-border bg-card p-8 shadow-sm">
          <div className="mb-6 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
              <Scale className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-foreground">AI Justicia</h1>
              <p className="text-xs text-muted-foreground">Abogados y despachos</p>
            </div>
          </div>

          <div className="mb-5 grid grid-cols-2 gap-1 rounded-xl bg-muted p-1">
            <button type="button" onClick={() => setModoLogin("despacho")}
              className={`flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition ${modoLogin === "despacho" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground"}`}>
              <Building2 className="h-3.5 w-3.5" /> {t("common.despacho")}
            </button>
            <button type="button" onClick={() => setModoLogin("abogado")}
              className={`flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition ${modoLogin === "abogado" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground"}`}>
              <KeyRound className="h-3.5 w-3.5" /> {t("common.abogado")}
            </button>
          </div>

          {modoLogin === "despacho" ? (
            <>
              <input value={loginForm.user} onChange={(e) => setLoginForm({ ...loginForm, user: e.target.value })}
                placeholder={t("common.usuario")} autoComplete="username"
                className="mb-3 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground" />
              <input type="password" value={loginForm.pass} onChange={(e) => setLoginForm({ ...loginForm, pass: e.target.value })}
                placeholder={t("common.contrasena")} autoComplete="current-password"
                className="mb-4 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground" />
            </>
          ) : (
            <textarea value={loginForm.frase} onChange={(e) => setLoginForm({ ...loginForm, frase: e.target.value })}
              placeholder={t("common.frase")} rows={2}
              className="mb-4 w-full resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground" />
          )}

          {loginError && (
            <p className="mb-3 flex items-center gap-1.5 rounded-lg bg-red-50 dark:bg-red-950/30 px-3 py-2 text-xs text-red-600">
              <AlertCircle className="h-3.5 w-3.5" /> {loginError}
            </p>
          )}
          <button type="submit" disabled={logueando}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary py-2.5 text-sm font-semibold text-primary-foreground disabled:opacity-40">
            {logueando ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogIn className="h-4 w-4" />} {t("common.entrar")}
          </button>

          <div className="mt-4 flex items-center justify-center gap-2">
            <button type="button" onClick={() => setLang(lang === "es" ? "en" : "es")}
              className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground">
              <Languages className="size-3" /> {lang === "es" ? "English" : "Español"}
            </button>
          </div>
        </form>
      </div>
    );
  }

  // ── STUDIO ──
  const [titulo, subtitulo] = TITULOS[page];
  return (
    <StudioShell
      page={page}
      onNavigate={setPage}
      titulo={t(`nav.${page}`) || titulo}
      subtitulo={subtitulo}
      firma={usuario || "despacho"}
      usuario={usuario}
      casoNombre={casoNombre}
      casoId={casoId}
      onNuevoCaso={() => setNuevoCasoOpen(true)}
      onSalir={salir}
    >
      {page === "casos" && <CasesPage onCasoNombre={setCasoNombre} onCasoId={setCasoId} />}
      {page === "panel" && <DashboardPage onNavigate={(p) => setPage(p as StudioPage)} />}
      {page === "clientes" && <ClientsPage />}
      {page === "biblioteca" && <LibraryPage />}
      {page === "agenda" && <AgendaPage />}
      {page === "conflictos" && <ConflictsPage />}
      {page === "ajustes" && <SettingsPage />}
      {page === "tiempo" && <SettingsPage />}

      {nuevoCasoOpen && (
        <NuevoCasoDialog onClose={() => setNuevoCasoOpen(false)} crear={crearCaso} />
      )}
    </StudioShell>
  );
}

function NuevoCasoDialog({ onClose, crear }: {
  onClose: () => void;
  crear: (nombre: string, materia: string) => Promise<void>;
}) {
  const t = useT();
  const [nombre, setNombre] = useState("");
  const [materia, setMateria] = useState("");
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-full max-w-sm rounded-2xl bg-background p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-4 text-[15px] font-semibold">{t("casos.nuevo")}</h3>
        <input value={nombre} onChange={(e) => setNombre(e.target.value)}
          placeholder="Nombre del caso" autoFocus
          className="mb-3 w-full rounded-lg border border-input bg-background px-3 py-2 text-[13px]" />
        <select value={materia} onChange={(e) => setMateria(e.target.value)}
          className="mb-4 w-full rounded-lg border border-input bg-background px-3 py-2 text-[13px]">
          <option value="">Materia…</option>
          {["Civil", "Mercantil", "Laboral", "Familiar", "Penal", "Amparo", "Administrativo", "Fiscal"].map((m) => (
            <option key={m} value={m.toLowerCase()}>{m}</option>
          ))}
        </select>
        <div className="flex gap-2">
          <button onClick={onClose}
            className="flex-1 rounded-lg border border-border py-2 text-[12px] font-medium text-muted-foreground">
            {t("common.cancelar")}
          </button>
          <button onClick={async () => { await crear(nombre, materia); onClose(); }}
            disabled={!nombre.trim()}
            className="flex-1 rounded-lg bg-primary py-2 text-[12px] font-semibold text-primary-foreground disabled:opacity-40">
            {t("common.crear")}
          </button>
        </div>
      </div>
    </div>
  );
}
