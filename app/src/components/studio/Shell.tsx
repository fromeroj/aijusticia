"use client";

/**
 * Shell — layout principal de la nueva UI (Studio).
 *
 * ┌─────────┬──────────────────────────────┬──────────┐
 * │ Sidebar │  Main content (page)          │ IzelRail │
 * │ (248px) │  - Cases list + detail        │ (280px)  │
 * │         │  - Dashboard, Library, etc    │  chat    │
 * └─────────┴──────────────────────────────┴──────────┘
 * Topbar: búsqueda (Cmd+K), notificaciones, dark/light, i18n, perfil
 */
import { useEffect, useState, type ReactNode } from "react";
import {
  Bell, Briefcase, CalendarClock, Clock3, FolderKanban, LayoutDashboard,
  Library, Moon, Scale, Search, ShieldCheck, Sun, Users, Plus,
  Languages,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useT, useLang, type Lang } from "@/lib/i18n";
import { IzelPanel } from "@/components/studio/IzelPanel";
import { useTheme } from "@/lib/theme";

export type StudioPage =
  | "panel" | "casos" | "clientes" | "biblioteca"
  | "agenda" | "tiempo" | "conflictos" | "ajustes";

const NAV: { id: StudioPage; icon: any }[] = [
  { id: "panel", icon: LayoutDashboard },
  { id: "casos", icon: FolderKanban },
  { id: "clientes", icon: Users },
  { id: "biblioteca", icon: Library },
  { id: "agenda", icon: CalendarClock },
  { id: "tiempo", icon: Clock3 },
];
const NAV_OPS: { id: StudioPage; icon: any }[] = [
  { id: "conflictos", icon: ShieldCheck },
];

// ── Sidebar ────────────────────────────────────────────────────────────────

function Sidebar({ page, onNavigate, firma, onNuevoCaso }: {
  page: StudioPage; onNavigate: (p: StudioPage) => void;
  firma: string; onNuevoCaso: () => void;
}) {
  const t = useT();
  return (
    <aside className="flex h-full w-[248px] shrink-0 flex-col border-r border-border bg-sidebar-background">
      <div className="flex items-center gap-2.5 border-b border-border px-5 py-4">
        <span className="flex size-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Scale className="size-4" />
        </span>
        <div className="min-w-0">
          <p className="text-[15px] font-semibold leading-tight tracking-tight text-foreground">
            AI Justicia
          </p>
          <p className="truncate text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            {firma}
          </p>
        </div>
      </div>

      <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
        <div>
          <p className="mb-1.5 px-2 text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
            {t("nav.trabajo")}
          </p>
          {NAV.map((item) => (
            <NavItem
              key={item.id}
              active={page === item.id}
              onClick={() => onNavigate(item.id)}
              icon={<item.icon className="size-4" />}
              label={t(`nav.${item.id}`)}
            />
          ))}
        </div>
        <div>
          <p className="mb-1.5 px-2 text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
            {t("nav.cumplimiento")}
          </p>
          {NAV_OPS.map((item) => (
            <NavItem
              key={item.id}
              active={page === item.id}
              onClick={() => onNavigate(item.id)}
              icon={<item.icon className="size-4" />}
              label={t(`nav.${item.id}`)}
            />
          ))}
        </div>
      </nav>

      <div className="border-t border-border p-3">
        <button
          onClick={onNuevoCaso}
          className="flex w-full items-center gap-2 rounded-md bg-primary/10 px-3 py-2 text-[13px] font-medium text-primary transition-colors hover:bg-primary/20"
        >
          <Plus className="size-4" /> {t("casos.nuevo")}
        </button>
      </div>
    </aside>
  );
}

function NavItem({ active, onClick, icon, label }: {
  active: boolean; onClick: () => void; icon: ReactNode; label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2.5 rounded-md px-3 py-1.5 text-[13.5px] transition-colors",
        active ? "bg-primary/10 font-medium text-primary" : "text-muted-foreground hover:bg-accent hover:text-foreground"
      )}
    >
      {icon}
      <span className="truncate">{label}</span>
    </button>
  );
}

// ── Topbar ─────────────────────────────────────────────────────────────────

function Topbar({ titulo, subtitulo, onNuevoCaso, onSalir }: {
  titulo: string; subtitulo?: string; onNuevoCaso: () => void; onSalir: () => void;
}) {
  const [theme, toggleTheme] = useTheme();
  const [lang, setLang] = useLang();
  const t = useT();

  return (
    <header className="flex h-[52px] shrink-0 items-center gap-3 border-b border-border bg-background px-5">
      <div className="min-w-0">
        <h1 className="truncate text-[15px] font-semibold tracking-tight text-foreground">{titulo}</h1>
        {subtitulo && <p className="truncate text-[11px] text-muted-foreground">{subtitulo}</p>}
      </div>

      <div className="ml-auto flex items-center gap-1.5">
        {/* búsqueda (decorativa por ahora — Cmd+K) */}
        <button
          className="flex items-center gap-2 rounded-md border border-input bg-background px-3 py-1.5 text-[12px] text-muted-foreground hover:border-primary/40"
          title="⌘K"
        >
          <Search className="size-3.5" />
          <span className="hidden sm:inline">{t("common.buscar")}</span>
          <kbd className="rounded border border-border bg-muted px-1 font-mono text-[10px]">⌘K</kbd>
        </button>

        {/* i18n toggle */}
        <button
          onClick={() => setLang(lang === "es" ? "en" : "es")}
          className="flex items-center gap-1 rounded-md px-2 py-1.5 text-[12px] font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
          title={lang === "es" ? "Switch to English" : "Cambiar a español"}
        >
          <Languages className="size-4" />
          <span className="uppercase">{lang}</span>
        </button>

        {/* dark/light */}
        <button
          onClick={toggleTheme}
          className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </button>

        {/* notificaciones */}
        <button className="relative rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground">
          <Bell className="size-4" />
          <span className="absolute right-1 top-1 size-1.5 rounded-full bg-red-500" />
        </button>

        {/* salir */}
        <button
          onClick={onSalir}
          className="rounded-md px-2.5 py-1.5 text-[12px] text-muted-foreground hover:bg-accent hover:text-red-500"
        >
          {t("common.salir")}
        </button>
      </div>
    </header>
  );
}

// ── Shell ──────────────────────────────────────────────────────────────────

export function StudioShell({
  page, onNavigate, titulo, subtitulo, firma, usuario,
  casoNombre, casoId, onNuevoCaso, onSalir, children,
}: {
  page: StudioPage;
  onNavigate: (p: StudioPage) => void;
  titulo: string;
  subtitulo?: string;
  firma: string;
  usuario: string;
  casoNombre?: string | null;
  casoId?: string | null;
  onNuevoCaso: () => void;
  onSalir: () => void;
  children: ReactNode;
}) {
  // aplicar theme al montar
  useEffect(() => {
    import("@/lib/theme").then(({ getTheme }) => getTheme());
  }, []);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background text-foreground">
      <Sidebar page={page} onNavigate={onNavigate} firma={firma} onNuevoCaso={onNuevoCaso} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar titulo={titulo} subtitulo={subtitulo} onNuevoCaso={onNuevoCaso} onSalir={onSalir} />
        <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
      </div>
      {/* IzelPanel flotante — se superpone al contenido, no lo empuja */}
      <IzelPanel casoNombre={casoNombre} casoId={casoId} />
    </div>
  );
}
