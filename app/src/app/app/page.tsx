"use client";

/**
 * /app — la app de trabajo para abogados y despachos (M2: una sola app).
 *
 * Dos formas de entrar, mismas funciones tras el login:
 *  - Despacho: usuario+contraseña de Nextcloud → /auth/token via=nc
 *  - Abogado individual: frase de recuperación → /auth/token via=frase
 *
 * Todo pasa por el API /bufetes/* del engine con JWT (RLS por bufete):
 * casos, plantillas, generación de documentos (job queue) e Izel (consulta).
 */
import { useEffect, useState, useCallback, useRef } from "react";
import {
  Scale, FileText, FolderOpen, MessageSquareText, Send, Loader2,
  CheckCircle2, AlertCircle, LogIn, Sparkles, RefreshCw, FolderPlus, ExternalLink, KeyRound, Building2,
  Users, ShieldAlert, Lock, UserMinus, UserPlus,
} from "lucide-react";

const API = ""; // same-origin: nginx enruta /auth/* y /bufetes/* al engine
const NC_FILES = "https://oficina.konen.guru/index.php/apps/files?dir=";

type Tokens = { access: string; refresh: string };
type Caso = {
  id: string; nombre: string | null; materia: string | null; created_at: string;
  origen?: string;          // propio | compartido (F4)
  rol_acceso?: string;
  confidencial?: boolean;
};
type Plantilla = { nombre: string; categoria: string };

function cargarTokens(): Tokens | null {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem("aij_tokens");
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

function guardarTokens(t: Tokens) { sessionStorage.setItem("aij_tokens", JSON.stringify(t)); }

export default function AppPage() {
  const [tokens, setTokens] = useState<Tokens | null>(null);
  const [usuario, setUsuario] = useState("");
  const [modoLogin, setModoLogin] = useState<"despacho" | "abogado">("despacho");
  const [loginForm, setLoginForm] = useState({ user: "", pass: "", frase: "" });
  const [loginError, setLoginError] = useState("");
  const [logueando, setLogueando] = useState(false);
  const [plantillas, setPlantillas] = useState<Plantilla[]>([]);
  const [casos, setCasos] = useState<Caso[]>([]);
  const [selPlantilla, setSelPlantilla] = useState("");
  const [selCaso, setSelCaso] = useState("");
  const [vars, setVars] = useState<Record<string, string>>({});
  const [generando, setGenerando] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; texto: string; nc?: string } | null>(null);
  const [consulta, setConsulta] = useState("");
  const [respuesta, setRespuesta] = useState("");
  const [abstenido, setAbstenido] = useState(false);
  const [consultando, setConsultando] = useState(false);
  const [nuevoCaso, setNuevoCaso] = useState({ nombre: "", materia: "" });
  const [creandoCaso, setCreandoCaso] = useState(false);
  const [esAdmin, setEsAdmin] = useState(false);
  const [miembros, setMiembros] = useState<{ actor_id: string; rol: string; nc_login: string | null; email: string | null }[]>([]);
  const [asignaciones, setAsignaciones] = useState<{ id: string; actor_id: string; rol_en_caso: string; rol_firma: string }[]>([]);
  const [asignarA, setAsignarA] = useState("");
  const [asignarRol, setAsignarRol] = useState("abogado");
  const [tab, setTab] = useState<"timeline" | "documentos" | "notas" | "equipo">("timeline");
  const [timeline, setTimeline] = useState<{ tipo: string; cuando: string; quien: string | null; detalle: string }[]>([]);
  const [notas, setNotas] = useState<{ id: string; texto: string; creado_en: string; autor: string }[]>([]);
  const [nuevaNota, setNuevaNota] = useState("");
  const [docsCaso, setDocsCaso] = useState<{ id: number; nombre: string; metodo_texto: string | null; tamano_bytes: number; creado_en: string; version: number }[]>([]);
  const [msgPromover, setMsgPromover] = useState<string | null>(null);
  const [codMiembro, setCodMiembro] = useState<{ codigo: string; rol: string } | null>(null);

  const invitarMiembro = async (rol: string) => {
    const r = await apiFetch("/bufetes/miembros/invitacion", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rol }),
    }).catch(() => null);
    if (r?.ok) setCodMiembro(await r.json());
  };
  const embedido = useRef(false);

  useEffect(() => {
    embedido.current = typeof window !== "undefined" && window.parent !== window;
    const t = cargarTokens();
    if (t) {
      setTokens(t);
      setUsuario(sessionStorage.getItem("aij_usuario") || "");
    }
  }, []);

  /* ── API fetch con Bearer + auto-refresh ── */
  const apiFetch = useCallback(async (path: string, init: RequestInit = {}, retry = true): Promise<Response> => {
    if (!tokens) throw new Error("sin sesión");
    const r = await fetch(`${API}${path}`, {
      ...init,
      headers: { ...init.headers, Authorization: `Bearer ${tokens.access}` },
    });
    if (r.status === 401 && retry) {
      const rr = await fetch(`${API}/auth/token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ via: "refresh", credential: tokens.refresh }),
      });
      if (rr.ok) {
        const d = await rr.json();
        const nuevo: Tokens = { access: d.access_token, refresh: d.refresh_token };
        guardarTokens(nuevo);
        setTokens(nuevo);
        return apiFetch(path, init, false);
      }
      salir();
      throw new Error("Sesión expirada — entra de nuevo");
    }
    return r;
  }, [tokens]);

  const salir = useCallback(() => {
    sessionStorage.removeItem("aij_tokens");
    sessionStorage.removeItem("aij_usuario");
    setTokens(null);
    setCasos([]); setPlantillas([]); setVars({}); setMsg(null);
  }, []);

  const cargar = useCallback(async () => {
    if (!tokens) return;
    const [rc, rp] = await Promise.all([
      apiFetch("/bufetes/casos").catch(() => null),
      apiFetch("/bufetes/plantillas").catch(() => null),
    ]);
    if (rc?.ok) {
      const d = await rc.json();
      setCasos(d.casos ?? []);
      setEsAdmin(Boolean(d.es_admin));
    }
    const rm = await apiFetch("/bufetes/miembros").catch(() => null);
    if (rm?.ok) setMiembros((await rm.json()).miembros ?? []);
    if (rp?.ok) setPlantillas((await rp.json()).plantillas ?? []);
  }, [apiFetch, tokens]);

  useEffect(() => { if (tokens) cargar(); }, [tokens, cargar]);

  useEffect(() => {
    if (!tokens || !selCaso) { setAsignaciones([]); setTimeline([]); setNotas([]); setDocsCaso([]); return; }
    apiFetch(`/dossiers/${selCaso}/equipo`)
      .then((r) => (r.ok ? r.json() : { asignaciones: [] }))
      .then((d) => setAsignaciones(d.asignaciones ?? []))
      .catch(() => setAsignaciones([]));
  }, [tokens, selCaso, apiFetch]);

  useEffect(() => {
    if (!tokens || !selCaso) return;
    const carga = {
      timeline: () => apiFetch(`/bufetes/casos/${selCaso}/timeline`)
        .then((r) => (r.ok ? r.json() : { eventos: [] })).then((d) => setTimeline(d.eventos ?? [])),
      notas: () => apiFetch(`/bufetes/casos/${selCaso}/notas`)
        .then((r) => (r.ok ? r.json() : { notas: [] })).then((d) => setNotas(d.notas ?? [])),
      documentos: () => apiFetch(`/bufetes/casos/${selCaso}/documentos`)
        .then((r) => (r.ok ? r.json() : { documentos: [] })).then((d) => setDocsCaso(d.documentos ?? [])),
      equipo: () => Promise.resolve(),
    };
    carga[tab]().catch(() => {});
  }, [tokens, selCaso, tab, apiFetch]);

  const agregarNota = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selCaso || !nuevaNota.trim()) return;
    const r = await apiFetch(`/bufetes/casos/${selCaso}/notas`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texto: nuevaNota.trim() }),
    }).catch(() => null);
    if (r?.ok) {
      setNuevaNota("");
      apiFetch(`/bufetes/casos/${selCaso}/notas`)
        .then((x) => x.json()).then((d) => setNotas(d.notas ?? [])).catch(() => {});
    }
  };

  const borrarNota = async (id: string) => {
    if (!selCaso) return;
    await apiFetch(`/bufetes/casos/${selCaso}/notas/${id}`, { method: "DELETE" }).catch(() => null);
    setNotas((prev) => prev.filter((n) => n.id !== id));
  };

  const promover = async (docId: number) => {
    if (!selCaso) return;
    setMsgPromover("Promoviendo… (PII-scan + anonimización)");
    const r = await apiFetch(`/bufetes/casos/${selCaso}/documentos/${docId}/promover`, {
      method: "POST",
    }).catch(() => null);
    if (r?.ok) {
      const { job_id } = await r.json();
      for (let i = 0; i < 20; i++) {
        await new Promise((res) => setTimeout(res, 1500));
        const jr = await apiFetch(`/bufetes/jobs/${job_id}`).catch(() => null);
        if (!jr || !jr.ok) continue;
        const j = await jr.json();
        if (j.estado === "completado") {
          setMsgPromover(`✓ Plantilla creada: ${j.resultado?.plantilla} (${j.resultado?.pii_anonimizada} datos anonimizados)`);
          return;
        }
        if (j.estado === "fallido") { setMsgPromover(`✗ ${j.error ?? "falló"}`); return; }
      }
      setMsgPromover("En proceso — revisa /Plantillas/Importadas en unos minutos.");
    } else {
      setMsgPromover("✗ No se pudo encolar la promoción");
    }
  };

  const asignar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selCaso || !asignarA) return;
    const r = await apiFetch(`/bufetes/casos/${selCaso}/asignaciones`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor_id: asignarA, rol_en_caso: asignarRol }),
    }).catch(() => null);
    if (r?.ok) {
      setAsignarA("");
      apiFetch(`/dossiers/${selCaso}/equipo`)
        .then((x) => x.json()).then((d) => setAsignaciones(d.asignaciones ?? [])).catch(() => {});
    } else if (r) {
      setMsg({ ok: false, texto: (await r.json().catch(() => ({}))).detail || "No se pudo asignar" });
    }
  };

  const quitarAsign = async (asigId: string) => {
    if (!selCaso) return;
    await apiFetch(`/bufetes/casos/${selCaso}/asignaciones/${asigId}`, { method: "DELETE" }).catch(() => null);
    setAsignaciones((prev) => prev.filter((a) => a.id !== asigId));
  };

  const vetar = async (actorId: string) => {
    if (!selCaso) return;
    const razon = prompt("Razón del veto (muro ético — conflicto de interés):") || "";
    const r = await apiFetch(`/bufetes/casos/${selCaso}/vetos`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor_id: actorId, razon }),
    }).catch(() => null);
    if (r?.ok) {
      setAsignaciones((prev) => prev.filter((a) => a.actor_id !== actorId));
      setMsg({ ok: true, texto: "Veto aplicado — esa persona no puede ver ni ser asignada a este caso." });
    }
  };

  const toggleConfidencial = async () => {
    if (!selCaso) return;
    const c = casos.find((x) => x.id === selCaso);
    const nuevo = !c?.confidencial;
    const r = await apiFetch(`/bufetes/casos/${selCaso}/confidencial`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ valor: nuevo }),
    }).catch(() => null);
    if (r?.ok) {
      setCasos((prev) => prev.map((x) => x.id === selCaso ? { ...x, confidencial: nuevo } : x));
    }
  };

  async function login(e: React.FormEvent) {
    e.preventDefault();
    setLogueando(true); setLoginError("");
    try {
      let body: string;
      if (modoLogin === "despacho") {
        const user = loginForm.user.trim();
        if (!user || !loginForm.pass) return;
        body = JSON.stringify({ via: "nc", user, credential: loginForm.pass });
      } else {
        if (loginForm.frase.trim().split(/\s+/).length < 8) {
          setLoginError("Escribe tu frase completa (12 palabras).");
          return;
        }
        body = JSON.stringify({ via: "frase", credential: loginForm.frase.trim() });
      }
      const r = await fetch(`${API}/auth/token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        setLoginError(d.detail || "No se pudo iniciar sesión");
        return;
      }
      const d = await r.json();
      const t: Tokens = { access: d.access_token, refresh: d.refresh_token };
      guardarTokens(t);
      sessionStorage.setItem("aij_usuario",
        modoLogin === "despacho" ? loginForm.user.trim() : (d.tipo === "abogado" ? "abogado" : d.tipo));
      setUsuario(modoLogin === "despacho" ? loginForm.user.trim() : "abogado");
      setLoginForm({ user: "", pass: "", frase: "" });
      setTokens(t);
      // retorno desde /reclamar (canje de invitación) tras login
      const volver = new URLSearchParams(window.location.search).get("volver");
      if (volver?.startsWith("/")) {
        window.location.href = volver;
      }
    } catch {
      setLoginError("Error de conexión con el motor");
    } finally {
      setLogueando(false);
    }
  }

  async function crearCaso(e: React.FormEvent) {
    e.preventDefault();
    if (!nuevoCaso.nombre.trim()) return;
    setCreandoCaso(true);
    try {
      const r = await apiFetch("/bufetes/casos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nombre: nuevoCaso.nombre.trim(),
          materia: nuevoCaso.materia.trim() || null,
        }),
      });
      if (r.ok) {
        setNuevoCaso({ nombre: "", materia: "" });
        await cargar();
      }
    } catch { /* sesión gestionada en apiFetch */ } finally {
      setCreandoCaso(false);
    }
  }

  async function detectarVars(ruta: string) {
    setSelPlantilla(ruta);
    setVars({});
    if (!ruta) return;
    try {
      const r = await apiFetch(`/bufetes/plantillas/variables?nombre=${encodeURIComponent(ruta)}`);
      if (!r.ok) return;
      const d = await r.json();
      const ini: Record<string, string> = {};
      (d.variables ?? []).forEach((v: string) => (ini[v] = ""));
      setVars(ini);
    } catch { /* plantilla sin vars detectables */ }
  }

  async function generar(e: React.FormEvent) {
    e.preventDefault();
    if (!selPlantilla || !selCaso) return;
    setGenerando(true);
    setMsg(null);
    try {
      const r = await apiFetch("/bufetes/documentos/generar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plantilla: selPlantilla, caso_id: selCaso, variables: vars }),
      });
      if (!r.ok) throw new Error(`encolar falló (${r.status})`);
      const { job_id } = await r.json();
      for (let i = 0; i < 40; i++) {
        await new Promise((res) => setTimeout(res, 1500));
        const jr = await apiFetch(`/bufetes/jobs/${job_id}`);
        if (!jr.ok) continue;
        const j = await jr.json();
        if (j.estado === "completado") {
          const res = j.resultado ?? {};
          const pii = res.pii_detectada
            ? ` · ⚠ ${res.pii_detectada} dato(s) personal(es) detectado(s): ${(res.pii_tipos ?? []).join(", ")}`
            : "";
          setMsg({
            ok: true,
            texto: `${res.archivo ?? "Documento"} generado en ${res.ruta ?? "el caso"}${pii}`,
            nc: `${NC_FILES}/Casos/${selCaso}`,
          });
          return;
        }
        if (j.estado === "fallido") {
          setMsg({ ok: false, texto: `El job falló: ${j.error ?? "error desconocido"}` });
          return;
        }
      }
      setMsg({ ok: true, texto: "Generación en curso — revisa la carpeta del caso en un momento." });
    } catch (err) {
      setMsg({ ok: false, texto: `Error: ${err instanceof Error ? err.message : "desconocido"}` });
    } finally {
      setGenerando(false);
    }
  }

  async function preguntar(e: React.FormEvent) {
    e.preventDefault();
    if (!consulta.trim()) return;
    setConsultando(true);
    setRespuesta("");
    setAbstenido(false);
    try {
      const r = await apiFetch("/bufetes/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ consulta, caso_id: selCaso || null }),
      });
      if (!r.ok) throw new Error(`${r.status}`);
      const d = await r.json();
      setAbstenido(Boolean(d.abstenido));
      setRespuesta(d.respuesta || "(sin respuesta)");
    } catch {
      setRespuesta("Error de conexión con el motor jurídico.");
    } finally {
      setConsultando(false);
    }
  }

  /* ── Login screen ── */
  if (!tokens) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 p-6">
        <form onSubmit={login} className="w-full max-w-sm rounded-2xl border border-gray-100 bg-white p-8 shadow-sm">
          <div className="mb-6 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#047857]">
              <Scale className="h-6 w-6 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-gray-900">AI Justicia</h1>
              <p className="text-xs text-gray-400">Abogados y despachos</p>
            </div>
          </div>

          {/* Selector de modo */}
          <div className="mb-5 grid grid-cols-2 gap-1 rounded-xl bg-gray-100 p-1">
            <button
              type="button"
              onClick={() => { setModoLogin("despacho"); setLoginError(""); }}
              className={`flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition ${modoLogin === "despacho" ? "bg-white text-gray-900 shadow-sm" : "text-gray-500"}`}
            >
              <Building2 className="h-3.5 w-3.5" /> Despacho
            </button>
            <button
              type="button"
              onClick={() => { setModoLogin("abogado"); setLoginError(""); }}
              className={`flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition ${modoLogin === "abogado" ? "bg-white text-gray-900 shadow-sm" : "text-gray-500"}`}
            >
              <KeyRound className="h-3.5 w-3.5" /> Abogado
            </button>
          </div>

          {modoLogin === "despacho" ? (
            <>
              <label className="mb-1 block text-xs font-medium text-gray-600">Usuario de Nextcloud</label>
              <input
                value={loginForm.user}
                onChange={(e) => setLoginForm({ ...loginForm, user: e.target.value })}
                className="mb-3 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-[#047857] focus:outline-none"
                placeholder="usuario"
                autoComplete="username"
              />
              <label className="mb-1 block text-xs font-medium text-gray-600">Contraseña</label>
              <input
                type="password"
                value={loginForm.pass}
                onChange={(e) => setLoginForm({ ...loginForm, pass: e.target.value })}
                className="mb-4 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-[#047857] focus:outline-none"
                autoComplete="current-password"
              />
              <p className="mb-4 text-[10px] leading-relaxed text-gray-400">
                La contraseña se usa una sola vez para emitir tu token de sesión. No se guarda.
              </p>
            </>
          ) : (
            <>
              <label className="mb-1 block text-xs font-medium text-gray-600">Frase de acceso profesional</label>
              <textarea
                value={loginForm.frase}
                onChange={(e) => setLoginForm({ ...loginForm, frase: e.target.value })}
                className="mb-4 w-full resize-none rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-[#047857] focus:outline-none"
                placeholder="Las 12 palabras de tu registro…"
                rows={2}
                autoCapitalize="none"
                autoCorrect="off"
              />
              <p className="mb-4 text-[10px] leading-relaxed text-gray-400">
                La frase que recibiste al registrarte como abogado. Si llevas casos de ciudadanos,
                aparecerán aquí.
              </p>
            </>
          )}

          {loginError && (
            <p className="mb-3 flex items-center gap-1.5 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" /> {loginError}
            </p>
          )}
          <button
            type="submit"
            disabled={logueando}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#047857] py-2.5 text-sm font-semibold text-white hover:bg-[#036c4c] disabled:opacity-40"
          >
            {logueando ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogIn className="h-4 w-4" />} Entrar
          </button>
        </form>
      </div>
    );
  }

  /* ── Panel ── */
  return (
    <div className="min-h-screen bg-gray-50 p-4 sm:p-6">
      <header className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-[#047857] to-[#0d9488]">
          <Scale className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="text-base font-bold text-gray-900">AI Justicia · Trabajo</h1>
          <p className="text-[11px] text-gray-400">
            {usuario || "sesión"} · {embedido.current ? "integrado en Nextcloud" : "sesión JWT"}
          </p>
        </div>
        {esAdmin && (
          <button
            onClick={() => invitarMiembro("abogado")}
            className="ml-auto rounded-lg bg-[#047857]/10 px-2.5 py-1.5 text-[10px] font-semibold text-[#047857] hover:bg-[#047857]/20"
            title="Generar código para que un abogado se una a la firma"
          >
            + Invitar miembro
          </button>
        )}
        <button onClick={salir} className={`${esAdmin ? "" : "ml-auto "}text-xs text-gray-400 hover:text-gray-600`}>
          Salir
        </button>
        <button onClick={cargar} className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100" title="Refrescar">
          <RefreshCw className="h-4 w-4" />
        </button>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Generador */}
        <section className="rounded-2xl border border-gray-100 bg-white p-6">
          <div className="mb-4 flex items-center gap-2">
            <FileText className="h-5 w-5 text-[#047857]" />
            <h2 className="text-sm font-semibold text-gray-900">Generar documento</h2>
          </div>
          <form onSubmit={generar} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-[11px] font-medium text-gray-500">Plantilla</label>
                <select
                  value={selPlantilla}
                  onChange={(e) => detectarVars(e.target.value)}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-xs"
                >
                  <option value="">Seleccionar…</option>
                  {plantillas.map((p) => (
                    <option key={`${p.categoria}/${p.nombre}`} value={p.categoria ? `${p.categoria}/${p.nombre}` : p.nombre}>
                      {p.categoria ? `${p.categoria} · ${p.nombre}` : p.nombre}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-[11px] font-medium text-gray-500">Caso destino</label>
                <select
                  value={selCaso}
                  onChange={(e) => setSelCaso(e.target.value)}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-xs"
                >
                  <option value="">Seleccionar…</option>
                  {casos.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.origen === "compartido" ? "📂 " : ""}
                      {c.nombre ?? c.id.slice(0, 8)}{c.materia ? ` (${c.materia})` : ""}
                      {c.origen === "compartido" ? " — compartido" : ""}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {(() => {
              const c = casos.find((x) => x.id === selCaso);
              if (!c || c.origen !== "compartido") return null;
              return (
                <div className="rounded-xl border border-[#047857]/25 bg-[#ecfdf5]/60 px-3 py-2 text-[11px] text-gray-700">
                  Caso compartido por un ciudadano · tu acceso: <strong>{c.rol_acceso ?? "lectura"}</strong>.
                  Izel responde con el expediente y los documentos del caso.
                </div>
              );
            })()}
            {Object.keys(vars).length > 0 && (
              <div className="max-h-48 space-y-2 overflow-y-auto rounded-xl bg-gray-50 p-3">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-[#047857]">
                  Variables detectadas ({Object.keys(vars).length})
                </p>
                {Object.entries(vars).map(([k, v]) => (
                  <div key={k} className="flex items-center gap-2">
                    <span className="w-32 shrink-0 truncate font-mono text-[10px] text-gray-400">{k}</span>
                    <input
                      value={v}
                      onChange={(e) => setVars({ ...vars, [k]: e.target.value })}
                      placeholder={k}
                      className="flex-1 rounded-md border border-gray-200 bg-white px-2 py-1.5 text-xs"
                    />
                  </div>
                ))}
              </div>
            )}
            <button
              type="submit"
              disabled={!selPlantilla || !selCaso || generando}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#047857] py-2.5 text-sm font-semibold text-white hover:bg-[#036c4c] disabled:opacity-40"
            >
              {generando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {generando ? "Generando…" : "Generar y subir al caso"}
            </button>
          </form>
          {msg && (
            <div className={`mt-3 flex items-start gap-2 rounded-xl px-3 py-2 text-xs ${msg.ok ? "bg-[#ecfdf5] text-[#047857]" : "bg-red-50 text-red-600"}`}>
              {msg.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> : <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />}
              <span className="flex-1">
                {msg.texto}
                {msg.nc && (
                  <a href={msg.nc} target="_blank" rel="noreferrer" className="ml-1 inline-flex items-center gap-0.5 underline">
                    Abrir en Nextcloud <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </span>
            </div>
          )}

          {/* Nuevo caso */}
          <form onSubmit={crearCaso} className="mt-5 border-t border-gray-100 pt-4">
            <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold text-gray-500">
              <FolderPlus className="h-3.5 w-3.5" /> Nuevo caso
            </p>
            <div className="flex gap-2">
              <input
                value={nuevoCaso.nombre}
                onChange={(e) => setNuevoCaso({ ...nuevoCaso, nombre: e.target.value })}
                placeholder="Nombre del caso"
                className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-xs"
              />
              <input
                value={nuevoCaso.materia}
                onChange={(e) => setNuevoCaso({ ...nuevoCaso, materia: e.target.value })}
                placeholder="Materia"
                className="w-28 rounded-lg border border-gray-200 px-3 py-2 text-xs"
              />
              <button
                type="submit"
                disabled={creandoCaso || !nuevoCaso.nombre.trim()}
                className="rounded-lg bg-gray-100 px-3 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-200 disabled:opacity-40"
              >
                {creandoCaso ? "…" : "Crear"}
              </button>
            </div>
            {casos.length === 0 && (
              <p className="mt-3 flex items-center gap-1.5 text-[11px] text-gray-400">
                <FolderOpen className="h-3.5 w-3.5" /> Crea tu primer caso para generar documentos
              </p>
            )}
          </form>

          {/* Vista de caso: tabs Timeline/Documentos/Notas/Equipo */}
          {selCaso && (
            <div className="mt-5 border-t border-gray-100 pt-4">
              <div className="mb-3 flex gap-1 rounded-xl bg-gray-100 p-1">
                {([["timeline", "Timeline"], ["documentos", "Documentos"], ["notas", "Notas"], ["equipo", "Equipo"]] as const).map(([v, label]) => (
                  <button
                    key={v}
                    onClick={() => setTab(v)}
                    className={`flex-1 rounded-lg px-2 py-1.5 text-[11px] font-semibold transition ${tab === v ? "bg-white text-gray-900 shadow-sm" : "text-gray-500"}`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {tab === "timeline" && (
                <div className="max-h-72 space-y-1.5 overflow-y-auto">
                  {timeline.length === 0 ? (
                    <p className="text-[11px] text-gray-400">Sin eventos aún.</p>
                  ) : timeline.map((e, i) => (
                    <div key={i} className="flex gap-2.5 rounded-lg border border-gray-100 px-3 py-1.5">
                      <div className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[#047857]" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[11px] text-gray-800">
                          {e.detalle}
                        </p>
                        <p className="text-[9px] text-gray-400">
                          {new Date(e.cuando).toLocaleString("es-MX", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                          {e.quien ? ` · ${e.quien}` : ""} · {e.tipo.replace("_", " ")}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {tab === "documentos" && (
                <div className="max-h-72 space-y-1.5 overflow-y-auto">
                  {docsCaso.length === 0 ? (
                    <p className="text-[11px] text-gray-400">Sin documentos en la bóveda del caso.</p>
                  ) : docsCaso.map((d) => (
                    <div key={d.id} className="flex items-center gap-2 rounded-lg border border-gray-100 px-3 py-1.5">
                      <FileText className="h-3.5 w-3.5 shrink-0 text-gray-400" />
                      <span className="min-w-0 flex-1 truncate text-[11px] text-gray-800">
                        {d.nombre}{d.version > 1 && <span className="text-gray-400"> v{d.version}</span>}
                        <span className="ml-1 text-[9px] text-gray-400">
                          {(d.tamano_bytes / 1024).toFixed(0)} KB {d.metodo_texto === "ocr" ? "· OCR" : d.metodo_texto === "pdf_digital" ? "· texto" : ""}
                        </span>
                      </span>
                      {d.nombre.toLowerCase().endsWith(".docx") && (
                        <button
                          onClick={() => promover(d.id)}
                          className="rounded-md bg-[#047857]/10 px-2 py-1 text-[9px] font-semibold text-[#047857] hover:bg-[#047857]/20"
                          title="Convertir en plantilla (PII-scan + anonimización)"
                        >
                          → plantilla
                        </button>
                      )}
                    </div>
                  ))}
                  {msgPromover && <p className="rounded-lg bg-gray-50 px-3 py-2 text-[10px] text-gray-600">{msgPromover}</p>}
                </div>
              )}

              {tab === "notas" && (
                <div className="max-h-72 space-y-2 overflow-y-auto">
                  <form onSubmit={agregarNota} className="flex gap-2">
                    <input
                      value={nuevaNota}
                      onChange={(e) => setNuevaNota(e.target.value)}
                      placeholder="Nota del caso (visible para quien tiene acceso)…"
                      className="min-w-0 flex-1 rounded-lg border border-gray-200 px-3 py-2 text-[11px]"
                    />
                    <button type="submit" disabled={!nuevaNota.trim()} className="rounded-lg bg-[#047857] px-3 py-2 text-[10px] font-semibold text-white disabled:opacity-40">
                      Anotar
                    </button>
                  </form>
                  {notas.map((n) => (
                    <div key={n.id} className="group rounded-lg bg-amber-50/60 px-3 py-2">
                      <p className="whitespace-pre-wrap text-[11px] text-gray-800">{n.texto}</p>
                      <p className="mt-1 text-[9px] text-gray-400">
                        {n.autor} · {new Date(n.creado_en).toLocaleString("es-MX", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                        <button onClick={() => borrarNota(n.id)} className="ml-2 text-gray-300 opacity-0 transition hover:text-red-500 group-hover:opacity-100">borrar</button>
                      </p>
                    </div>
                  ))}
                </div>
              )}

              {tab === "equipo" && esAdmin && (
                <EquipoTab
                  selCaso={selCaso}
                  esAdmin={esAdmin}
                  miembros={miembros}
                  asignaciones={asignaciones}
                  confidencial={casos.find((x) => x.id === selCaso)?.confidencial}
                  apiFetch={apiFetch}
                  onCambios={async () => {
                    const r = await apiFetch(`/dossiers/${selCaso}/equipo`).catch(() => null);
                    if (r?.ok) setAsignaciones((await r.json()).asignaciones ?? []);
                    await cargar();
                  }}
                  setCasos={setCasos}
                  casos={casos}
                  setMsg={setMsg}
                />
              )}
              {tab === "equipo" && !esAdmin && (
                <p className="text-[11px] text-gray-400">Solo los socios/admins gestionan el equipo del caso.</p>
              )}
            </div>
          )}
        </section>

        {/* Izel — consulta jurídica */}
        <section className="rounded-2xl border border-gray-100 bg-white p-6">
          <div className="mb-4 flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br from-[#047857] to-[#0d9488] text-[10px] font-bold text-white">
              I
            </div>
            <h2 className="text-sm font-semibold text-gray-900">Izel · consulta jurídica</h2>
            {selCaso && (
              <span className="ml-auto rounded-full bg-gray-100 px-2 py-0.5 text-[10px] text-gray-500">
                con contexto del caso
              </span>
            )}
          </div>
          <form onSubmit={preguntar}>
            <textarea
              value={consulta}
              onChange={(e) => setConsulta(e.target.value)}
              rows={3}
              placeholder="¿Qué dice el art. 87 LFT sobre el aguinaldo? ¿Cómo ha resuelto la SCJN el despido por embarazo?"
              className="w-full resize-none rounded-xl border border-gray-200 px-3 py-2.5 text-sm focus:border-[#047857] focus:outline-none"
            />
            <button
              type="submit"
              disabled={consultando}
              className="mt-3 flex items-center gap-2 rounded-xl bg-[#047857] px-4 py-2 text-sm font-semibold text-white hover:bg-[#036c4c] disabled:opacity-40"
            >
              {consultando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              {consultando ? "Investigando…" : "Consultar con citas"}
            </button>
          </form>
          {respuesta && (
            <div className={`mt-4 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-xl p-4 text-xs leading-relaxed ${abstenido ? "bg-amber-50 text-amber-800" : "bg-gray-50 text-gray-700"}`}>
              {respuesta}
            </div>
          )}
        </section>
      </div>

      {codMiembro && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-6" onClick={() => setCodMiembro(null)}>
          <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">
              Código de membresía (rol: {codMiembro.rol})
            </p>
            <p className="my-3 text-center font-mono text-2xl font-bold tracking-[0.25em] text-gray-900">
              {codMiembro.codigo}
            </p>
            <p className="text-[11px] text-gray-500">
              Compártelo con el abogado: entra a{" "}
              <span className="font-mono">aijusticia.mx/unirse?c={codMiembro.codigo}</span>{" "}
              y queda en la firma.
            </p>
            <button onClick={() => setCodMiembro(null)} className="mt-4 w-full rounded-xl bg-[#047857] py-2 text-sm font-semibold text-white">
              Listo
            </button>
          </div>
        </div>
      )}

      <footer className="mt-8 text-center text-[10px] text-gray-300">
        Izel · anclada en fuentes oficiales · si no sabe, lo dice
      </footer>
    </div>
  );
}

/* ── Tab Equipo: asignaciones, vetos, confidencial ── */
function EquipoTab({ selCaso, esAdmin, miembros, asignaciones, confidencial,
                     apiFetch, onCambios, setCasos, casos, setMsg }: {
  selCaso: string; esAdmin: boolean;
  miembros: { actor_id: string; rol: string; nc_login: string | null; email: string | null }[];
  asignaciones: { id: string; actor_id: string; rol_en_caso: string; rol_firma: string }[];
  confidencial?: boolean;
  apiFetch: (p: string, i?: RequestInit) => Promise<Response>;
  onCambios: () => Promise<void>;
  setCasos: React.Dispatch<React.SetStateAction<Caso[]>>;
  casos: Caso[];
  setMsg: (m: { ok: boolean; texto: string } | null) => void;
}) {
  const [asignarA, setAsignarA] = useState("");
  const [asignarRol, setAsignarRol] = useState("abogado");

  const asignar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!asignarA) return;
    const r = await apiFetch(`/bufetes/casos/${selCaso}/asignaciones`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor_id: asignarA, rol_en_caso: asignarRol }),
    }).catch(() => null);
    if (r?.ok) { setAsignarA(""); await onCambios(); }
    else if (r) setMsg({ ok: false, texto: (await r.json().catch(() => ({}))).detail || "No se pudo asignar" });
  };

  const quitarAsign = async (asigId: string) => {
    await apiFetch(`/bufetes/casos/${selCaso}/asignaciones/${asigId}`, { method: "DELETE" }).catch(() => null);
    await onCambios();
  };

  const vetar = async (actorId: string) => {
    const razon = prompt("Razón del veto (muro ético — conflicto de interés):") || "";
    const r = await apiFetch(`/bufetes/casos/${selCaso}/vetos`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor_id: actorId, razon }),
    }).catch(() => null);
    if (r?.ok) {
      setMsg({ ok: true, texto: "Veto aplicado — esa persona no puede ver ni ser asignada a este caso." });
      await onCambios();
    }
  };

  const toggleConfidencial = async () => {
    const nuevo = !confidencial;
    const r = await apiFetch(`/bufetes/casos/${selCaso}/confidencial`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ valor: nuevo }),
    }).catch(() => null);
    if (r?.ok) setCasos(casos.map((x) => x.id === selCaso ? { ...x, confidencial: nuevo } : x));
  };

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <p className="flex items-center gap-1.5 text-[11px] font-semibold text-gray-500">
          <Users className="h-3.5 w-3.5" /> Asignaciones del caso
        </p>
        <button
          onClick={toggleConfidencial}
          className={`flex items-center gap-1 rounded-full px-2 py-1 text-[10px] font-semibold ${confidencial ? "bg-amber-100 text-amber-700" : "bg-gray-100 text-gray-500 hover:bg-gray-200"}`}
          title="Confidencial: solo los asignados ven este caso (ni el resto de admins)"
        >
          <Lock className="h-3 w-3" />
          {confidencial ? "Confidencial" : "Marcar confidencial"}
        </button>
      </div>
      {asignaciones.length === 0 ? (
        <p className="text-[11px] text-gray-400">Sin asignaciones — solo admins ven este caso.</p>
      ) : (
        <ul className="mb-2 space-y-1">
          {asignaciones.map((a) => {
            const m = miembros.find((x) => x.actor_id === a.actor_id);
            return (
              <li key={a.id} className="flex items-center gap-2 rounded-lg border border-gray-100 px-3 py-1.5 text-[11px]">
                <span className="min-w-0 flex-1 truncate">
                  <span className="font-medium text-gray-800">
                    {m?.nc_login || m?.email || `miembro ${a.actor_id.slice(0, 8)}`}
                  </span>
                  <span className="ml-1.5 rounded-full bg-[#047857]/10 px-1.5 py-0.5 text-[9px] font-semibold text-[#047857]">
                    {a.rol_en_caso}
                  </span>
                  <span className="ml-1 text-gray-400">({a.rol_firma})</span>
                </span>
                <button onClick={() => quitarAsign(a.id)} className="text-gray-300 hover:text-gray-600" title="Quitar del caso">
                  <UserMinus className="h-3.5 w-3.5" />
                </button>
                <button onClick={() => vetar(a.actor_id)} className="text-gray-300 hover:text-red-500" title="Vetar (muro ético)">
                  <ShieldAlert className="h-3.5 w-3.5" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <form onSubmit={asignar} className="flex gap-2">
        <select value={asignarA} onChange={(e) => setAsignarA(e.target.value)} className="min-w-0 flex-1 rounded-lg border border-gray-200 px-2 py-1.5 text-[11px]">
          <option value="">Asignar miembro…</option>
          {miembros.map((m) => (
            <option key={m.actor_id} value={m.actor_id}>
              {m.nc_login || m.email || m.actor_id.slice(0, 8)} ({m.rol})
            </option>
          ))}
        </select>
        <select value={asignarRol} onChange={(e) => setAsignarRol(e.target.value)} className="w-28 rounded-lg border border-gray-200 px-2 py-1.5 text-[11px]">
          <option value="responsable">responsable</option>
          <option value="abogado">abogado</option>
          <option value="pasante">pasante</option>
        </select>
        <button type="submit" disabled={!asignarA} className="rounded-lg bg-gray-100 px-3 py-1.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-200 disabled:opacity-40">
          <UserPlus className="h-3.5 w-3.5" />
        </button>
      </form>
    </div>
  );
}
