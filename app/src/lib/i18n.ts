/**
 * i18n — soporte es/en para toda la app.
 * El idioma default es es (español).
 * Cambiar con setLang("en") — persiste en localStorage.
 */
import { useCallback, useEffect, useState } from "react";

export type Lang = "es" | "en";

const KEY = "aij_lang";
let currentLang: Lang = "es";
const listeners = new Set<(l: Lang) => void>();

// ── translations ───────────────────────────────────────────────────────────

const T: Record<string, { es: string; en: string }> = {
  // nav
  "nav.panel": { es: "Panel", en: "Dashboard" },
  "nav.casos": { es: "Casos", en: "Cases" },
  "nav.clientes": { es: "Clientes", en: "Clients" },
  "nav.biblioteca": { es: "Biblioteca", en: "Library" },
  "nav.agenda": { es: "Agenda y plazos", en: "Calendar & deadlines" },
  "nav.tiempo": { es: "Tiempo y honorarios", en: "Time & fees" },
  "nav.conflictos": { es: "Verificación de conflictos", en: "Conflict check" },
  "nav.ajustes": { es: "Ajustes", en: "Settings" },
  "nav.trabajo": { es: "Trabajo", en: "Work" },
  "nav.cumplimiento": { es: "Cumplimiento", en: "Compliance" },

  // cases
  "casos.titulo": { es: "Casos", en: "Cases" },
  "casos.subtitulo": { es: "El caso es el centro de todo", en: "The case is the center of everything" },
  "casos.buscar": { es: "Buscar por nombre, folio o cliente…", en: "Search by name, file no. or client…" },
  "casos.todos": { es: "todos", en: "all" },
  "casos.activos": { es: "activos", en: "active" },
  "casos.confidenciales": { es: "confidenciales", en: "confidential" },
  "casos.compartidos": { es: "compartidos", en: "shared" },
  "casos.selecciona": { es: "Selecciona un caso", en: "Select a case" },
  "casos.expediente_vive": { es: "El expediente completo vive dentro del caso.", en: "The full case file lives inside the case." },
  "casos.sin_resultados": { es: "Ningún caso coincide con el filtro.", en: "No cases match the filter." },
  "casos.nuevo": { es: "Nuevo caso", en: "New case" },
  "casos.confidencial": { es: "confidencial", en: "confidential" },

  // tabs
  "tab.resumen": { es: "Resumen", en: "Overview" },
  "tab.documentos": { es: "Documentos", en: "Documents" },
  "tab.notas": { es: "Notas", en: "Notes" },
  "tab.plazos": { es: "Plazos y tareas", en: "Deadlines & tasks" },
  "tab.timeline": { es: "Timeline", en: "Timeline" },
  "tab.equipo": { es: "Equipo", en: "Team" },

  // resumen
  "resumen.situacion": { es: "Situación actual", en: "Current status" },
  "resumen.etapa": { es: "Etapa procesal", en: "Procedural stage" },
  "resumen.generar_doc": { es: "Generar documento desde plantilla", en: "Generate document from template" },
  "resumen.sin_docs": { es: "Sin documentos aún", en: "No documents yet" },

  // documentos
  "docs.version": { es: "versión", en: "version" },
  "docs.subido_por": { es: "subido por", en: "uploaded by" },
  "docs.nueva_version": { es: "Nueva versión", en: "New version" },
  "docs.plantilla": { es: "→ plantilla", en: "→ template" },
  "docs.ocr": { es: "OCR", en: "OCR" },
  "docs.texto": { es: "texto", en: "text" },

  // notas
  "notas.placeholder": { es: "Escribe una nota del caso…", en: "Write a case note…" },
  "notas.anotar": { es: "Anotar", en: "Add note" },
  "notas.solo_autor": { es: "solo el autor puede borrar", en: "only the author can delete" },

  // equipo
  "equipo.asignar": { es: "Asignar miembro…", en: "Assign member…" },
  "equipo.vetar": { es: "Vetar (muro ético)", en: "Block (ethical wall)" },
  "equipo.marcar_confidencial": { es: "Marcar confidencial", en: "Mark confidential" },

  // izel
  "izel.consulta": { es: "consulta jurídica", en: "legal query" },
  "izel.placeholder": { es: "Pregunta sobre este caso o el derecho mexicano…", en: "Ask about this case or Mexican law…" },
  "izel.contexto": { es: "con contexto del caso", en: "with case context" },
  "izel.investigando": { es: "Investigando…", en: "Researching…" },
  "izel.hola": { es: "Hola, soy Izel", en: "Hi, I'm Izel" },
  "izel.descripcion": { es: "Tu asistente legal. Pregunta sobre derecho mexicano: cada respuesta viene con citas verificadas.", en: "Your legal assistant. Ask about Mexican law: every answer comes with verified citations." },

  // dashboard
  "dash.casos_activos": { es: "Casos activos", en: "Active cases" },
  "dash.plazos_semana": { es: "Plazos esta semana", en: "Deadlines this week" },
  "dash.tareas_pend": { es: "Tareas pendientes", en: "Pending tasks" },
  "dash.clientes": { es: "Clientes", en: "Clients" },
  "dash.proximos": { es: "Próximos plazos", en: "Upcoming deadlines" },
  "dash.actividad": { es: "Actividad reciente", en: "Recent activity" },

  // common
  "common.crear": { es: "Crear", en: "Create" },
  "common.cancelar": { es: "Cancelar", en: "Cancel" },
  "common.guardar": { es: "Guardar", en: "Save" },
  "common.borrar": { es: "borrar", en: "delete" },
  "common.salir": { es: "Salir", en: "Sign out" },
  "common.entrar": { es: "Entrar", en: "Sign in" },
  "common.refrescar": { es: "Refrescar", en: "Refresh" },
  "common.buscar": { es: "Buscar…", en: "Search…" },
  "common.notificaciones": { es: "Notificaciones", en: "Notifications" },
  "common.despacho": { es: "Despacho", en: "Firm" },
  "common.abogado": { es: "Abogado", en: "Lawyer" },
  "common.usuario": { es: "Usuario", en: "User" },
  "common.contrasena": { es: "Contraseña", en: "Password" },
  "common.frase": { es: "Frase de acceso profesional", en: "Professional access phrase" },
  "common.cargando": { es: "Cargando…", en: "Loading…" },
  "common.sin_datos": { es: "Sin datos aún", en: "No data yet" },
  "common.disclaimer": {
    es: "AI Justicia e Izel ofrecen información jurídica general verificada. No son abogados ni sustituyen asesoría legal profesional.",
    en: "AI Justicia and Izel provide verified general legal information. They are not lawyers nor a substitute for professional legal advice."
  },

  // materias
  "materia.civil": { es: "Civil", en: "Civil" },
  "materia.mercantil": { es: "Mercantil", en: "Commercial" },
  "materia.laboral": { es: "Laboral", en: "Labor" },
  "materia.familiar": { es: "Familiar", en: "Family" },
  "materia.penal": { es: "Penal", en: "Criminal" },
  "materia.amparo": { es: "Amparo", en: "Amparo" },
  "materia.administrativo": { es: "Administrativo", en: "Administrative" },
  "materia.fiscal": { es: "Fiscal", en: "Tax" },

  // estados
  "estado.activo": { es: "Activo", en: "Active" },
  "estado.en_espera": { es: "En espera", en: "On hold" },
  "estado.suspendido": { es: "Suspendido", en: "Suspended" },
  "estado.concluido": { es: "Concluido", en: "Closed" },
  "estado.archivado": { es: "Archivado", en: "Archived" },
};

// ── API ────────────────────────────────────────────────────────────────────

export function getLang(): Lang {
  if (typeof window !== "undefined" && !currentLang) {
    currentLang = (localStorage.getItem(KEY) as Lang) || "es";
  }
  return currentLang;
}

export function setLang(l: Lang) {
  currentLang = l;
  if (typeof window !== "undefined") {
    localStorage.setItem(KEY, l);
  }
  document.documentElement.lang = l;
  listeners.forEach((fn) => fn(l));
}

export function t(key: string): string {
  const entry = T[key];
  if (!entry) return key;
  return entry[getLang()] ?? entry.es;
}

/** Hook para re-renderizar cuando cambia el idioma. */
export function useLang(): [Lang, (l: Lang) => void] {
  const [lang, setLangState] = useState<Lang>(getLang());
  useEffect(() => {
    const fn = (l: Lang) => setLangState(l);
    listeners.add(fn);
    return () => { listeners.delete(fn); };
  }, []);
  const change = useCallback((l: Lang) => {
    setLang(l);
    setLangState(l);
  }, []);
  return [lang, change];
}

/** Hook para usar t() reactivo. */
export function useT(): (key: string) => string {
  const [lang] = useLang();
  return useCallback((key: string) => {
    const entry = T[key];
    return entry ? (entry[lang] ?? entry.es) : key;
  }, [lang]);
}
