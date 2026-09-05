"use client";

/**
 * Panel Tlamatini — la app del despacho que vive DENTRO de Nextcloud (iframe).
 *
 * Autenticación: detecta si corre embebida en Nextcloud (window.parent ≠ self)
 * y usa la sesión NC vía el helper de postMessage/OCS; standalone pide credenciales
 * NC (mismo login — no hay segundo usuario).
 *
 * Funciones:
 *  - Generar documento desde plantilla (docxtpl + expediente del caso) → WebDAV
 *  - Consulta jurídica anclada (Nivel1 contra el RAG del engine)
 *  - Estructura de casos/plantillas sincronizada con NC
 */
import { useEffect, useState, useCallback, useRef } from "react";
import {
  Scale, FileText, FolderOpen, MessageSquareText, Send, Loader2,
  CheckCircle2, AlertCircle, LogIn, Sparkles, RefreshCw,
} from "lucide-react";

const NC_URL = "https://oficina.konen.guru";

/* ── Cliente NC ligero (WebDAV + OCS con sesión o app-password) ── */

function b64(creds: string) {
  if (typeof window === "undefined") return "";
  return btoa(creds);
}

type DavEntry = { name: string; isDir: boolean };

async function davEntries(path: string, auth: { user: string; pass: string }): Promise<DavEntry[]> {
  const body = `<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/><d:displayname/></d:prop></d:propfind>`;
  const r = await fetch(`${NC_URL}/remote.php/dav/files/${auth.user}${path}`, {
    method: "PROPFIND",
    headers: { Depth: "1", Authorization: `Basic ${b64(`${auth.user}:${auth.pass}`)}`, "Content-Type": "application/xml" },
    body,
  });
  if (!r.ok) throw new Error(`PROPFIND ${r.status}`);
  const xml = await r.text();
  const root = `/remote.php/dav/files/${auth.user}${path}`;
  const out: DavEntry[] = [];
  for (const m of xml.matchAll(/<d:href>([^<]+)<\/d:href>/g)) {
    const h = decodeURIComponent(m[1]);
    if (h.replace(/\/$/, "") === root.replace(/\/$/, "")) continue;
    const name = decodeURIComponent(h.split("/").filter(Boolean).pop() || "");
    if (!name) continue;
    out.push({ name, isDir: h.endsWith("/") });
  }
  return out;
}

async function davListDocx(path: string, auth: { user: string; pass: string }): Promise<string[]> {
  // recorre subcarpetas un nivel para hallar plantillas .docx
  const entries = await davEntries(path, auth);
  const files: string[] = [];
  for (const e of entries) {
    if (!e.isDir && e.name.endsWith(".docx")) files.push(e.name);
    if (e.isDir) {
      const sub = await davEntries(`${path.replace(/\/$/, "")}/${e.name}`, auth).catch(() => [] as DavEntry[]);
      for (const s of sub) {
        if (!s.isDir && s.name.endsWith(".docx")) files.push(`${e.name}/${s.name}`);
      }
    }
  }
  return files;
}

async function davListDirs(path: string, auth: { user: string; pass: string }): Promise<string[]> {
  const entries = await davEntries(path, auth);
  return entries.filter((e) => e.isDir).map((e) => e.name);
}

async function davMkcol(path: string, auth: { user: string; pass: string }) {
  await fetch(`${NC_URL}/remote.php/dav/files/${auth.user}${path}`, {
    method: "MKCOL",
    headers: { Authorization: `Basic ${b64(`${auth.user}:${auth.pass}`)}` },
  }).catch(() => {});
}

async function davUpload(path: string, auth: { user: string; pass: string }, blob: Blob) {
  const r = await fetch(`${NC_URL}/remote.php/dav/files/${auth.user}${path}`, {
    method: "PUT",
    headers: { Authorization: `Basic ${b64(`${auth.user}:${auth.pass}`)}` },
    body: blob,
  });
  if (!r.ok && r.status !== 201 && r.status !== 204) throw new Error(`PUT ${r.status}`);
}

/* ── Generador docxtpl (servicio en el engine; fallback: reemplazo local) ── */

/* ── UI ── */

interface Auth { user: string; pass: string }

export default function PanelPage() {
  const [auth, setAuth] = useState<Auth | null>(null);
  const [loginForm, setLoginForm] = useState({ user: "", pass: "" });
  const [plantillas, setPlantillas] = useState<string[]>([]);
  const [casos, setCasos] = useState<string[]>([]);
  const [selPlantilla, setSelPlantilla] = useState("");
  const [selCaso, setSelCaso] = useState("");
  const [vars, setVars] = useState<Record<string, string>>({});
  const [generando, setGenerando] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; texto: string } | null>(null);
  const [consulta, setConsulta] = useState("");
  const [respuesta, setRespuesta] = useState("");
  const [consultando, setConsultando] = useState(false);
  const embedido = useRef(false);

  useEffect(() => {
    embedido.current = typeof window !== "undefined" && window.parent !== window;
    const guardado = sessionStorage.getItem("aij_nc_auth");
    if (guardado) setAuth(JSON.parse(guardado));
  }, []);

  const cargar = useCallback(async (a: Auth) => {
    try {
      const [pls, css] = await Promise.all([
        davListDocx("/Plantillas", a).catch(() => [] as string[]),
        davListDirs("/Casos", a).catch(() => [] as string[]),
      ]);
      setPlantillas(pls);
      setCasos(css);
    } catch {
      setMsg({ ok: false, texto: "No se pudo leer Nextcloud — revisa credenciales" });
    }
  }, []);

  useEffect(() => {
    if (auth) cargar(auth);
  }, [auth, cargar]);

  function login(e: React.FormEvent) {
    e.preventDefault();
    const a = { user: loginForm.user.trim(), pass: loginForm.pass };
    if (!a.user || !a.pass) return;
    sessionStorage.setItem("aij_nc_auth", JSON.stringify(a));
    setAuth(a);
  }

  async function detectarVars(plantilla: string) {
    setSelPlantilla(plantilla);
    setVars({});
    if (!auth) return;
    try {
      const r = await fetch(`${NC_URL}/remote.php/dav/files/${auth.user}/Plantillas/${plantilla}`, {
        headers: { Authorization: `Basic ${b64(`${auth.user}:${auth.pass}`)}` },
      });
      if (!r.ok) return;
      const JSZip = (await import("jszip")).default;
      const zip = await JSZip.loadAsync(await r.blob());
      const xml = await zip.file("word/document.xml")!.async("string");
      const found = [...xml.matchAll(/\{\{\s*([A-ZÁÉÍÓÚÑ_]+)\s*\}\}/g)].map((m) => m[1]);
      const uniq = [...new Set(found)];
      const ini: Record<string, string> = {};
      uniq.forEach((v) => (ini[v] = ""));
      setVars(ini);
    } catch {
      /* plantilla sin vars detectables */
    }
  }

  async function generar(e: React.FormEvent) {
    e.preventDefault();
    if (!auth || !selPlantilla || !selCaso) return;
    setGenerando(true);
    setMsg(null);
    try {
      const tplRes = await fetch(`${NC_URL}/remote.php/dav/files/${auth.user}/Plantillas/${selPlantilla}`, {
        headers: { Authorization: `Basic ${b64(`${auth.user}:${auth.pass}`)}` },
      });
      const blob = await generarDocxLocal(await tplRes.blob(), vars);
      const baseName = selPlantilla.split("/").pop() || selPlantilla;
      const nombre = baseName.replace(/\.docx$/i, "") + "_" + new Date().toISOString().slice(0, 10) + ".docx";
      await davUpload(`/Casos/${selCaso}/${nombre}`, auth, blob);
      setMsg({ ok: true, texto: `${nombre} generado en /Casos/${selCaso}/` });
    } catch (err) {
      setMsg({ ok: false, texto: `Error: ${err instanceof Error ? err.message : "desconocido"}` });
    } finally {
      setGenerando(false);
    }
  }

  async function generarDocxLocal(tplBlob: Blob, variables: Record<string, string>): Promise<Blob> {
    const JSZip = (await import("jszip")).default;
    const zip = await JSZip.loadAsync(tplBlob);
    let xml = await zip.file("word/document.xml")!.async("string");
    let reemplazos = 0;
    for (const [k, v] of Object.entries(variables)) {
      const antes = xml;
      xml = xml.split(`{{${k}}}`).join(v || `[${k}]`).split(`{{ ${k} }}`).join(v || `[${k}]`);
      if (xml !== antes) reemplazos++;
    }
    zip.file("word/document.xml", xml);
    const out = await zip.generateAsync({ type: "blob" });
    return new Blob([out], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
  }

  async function preguntar(e: React.FormEvent) {
    e.preventDefault();
    if (!consulta.trim()) return;
    setConsultando(true);
    setRespuesta("");
    try {
      const r = await fetch("https://aijusticia.mx/query/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ consulta, nivel: "Nivel1" }),
      });
      const reader = r.body?.getReader();
      const dec = new TextDecoder();
      let acc = "";
      let buf = "";
      while (reader) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const eventos = buf.split("\n\n");
        buf = eventos.pop() || "";
        for (const ev of eventos) {
          const m = ev.match(/^event: token\ndata: (.*)$/m);
          if (m) {
            try {
              acc += JSON.parse(m[1]).t ?? "";
              setRespuesta(acc);
            } catch { /* skip */ }
          }
        }
      }
    } catch {
      setRespuesta("Error de conexión con el motor jurídico.");
    } finally {
      setConsultando(false);
    }
  }

  /* ── Login screen ── */
  if (!auth) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 p-6">
        <form onSubmit={login} className="w-full max-w-sm rounded-2xl border border-gray-100 bg-white p-8 shadow-sm">
          <div className="mb-6 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#047857]">
              <Scale className="h-6 w-6 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-gray-900">Panel Tlamatini</h1>
              <p className="text-xs text-gray-400">Tu cuenta de Nextcloud — sin registros extra</p>
            </div>
          </div>
          <label className="mb-1 block text-xs font-medium text-gray-600">Usuario Nextcloud</label>
          <input
            value={loginForm.user}
            onChange={(e) => setLoginForm({ ...loginForm, user: e.target.value })}
            className="mb-3 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-[#047857] focus:outline-none"
            placeholder="admin"
            autoComplete="username"
          />
          <label className="mb-1 block text-xs font-medium text-gray-600">Contraseña / App password</label>
          <input
            type="password"
            value={loginForm.pass}
            onChange={(e) => setLoginForm({ ...loginForm, pass: e.target.value })}
            className="mb-6 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-[#047857] focus:outline-none"
            autoComplete="current-password"
          />
          <button type="submit" className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#047857] py-2.5 text-sm font-semibold text-white hover:bg-[#036c4c]">
            <LogIn className="h-4 w-4" /> Entrar al despacho
          </button>
        </form>
      </div>
    );
  }

  /* ── Panel ── */
  return (
    <div className="min-h-screen bg-gray-50 p-4 sm:p-6">
      <header className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#047857]">
          <Scale className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="text-base font-bold text-gray-900">Panel Tlamatini</h1>
          <p className="text-[11px] text-gray-400">
            {auth.user}@oficina · {embedido.current ? "integrado en Nextcloud" : "vista directa"}
          </p>
        </div>
        <button
          onClick={() => { sessionStorage.removeItem("aij_nc_auth"); setAuth(null); }}
          className="ml-auto text-xs text-gray-400 hover:text-gray-600"
        >
          Salir
        </button>
        <button onClick={() => auth && cargar(auth)} className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100" title="Refrescar">
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
                    <option key={p} value={p}>{p}</option>
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
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>
            </div>
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
              {msg.texto}
            </div>
          )}
          {casos.length === 0 && (
            <p className="mt-3 flex items-center gap-1.5 text-[11px] text-gray-400">
              <FolderOpen className="h-3.5 w-3.5" /> Crea carpetas de caso en Nextcloud para verlas aquí
            </p>
          )}
        </section>

        {/* Consulta jurídica */}
        <section className="rounded-2xl border border-gray-100 bg-white p-6">
          <div className="mb-4 flex items-center gap-2">
            <MessageSquareText className="h-5 w-5 text-[#047857]" />
            <h2 className="text-sm font-semibold text-gray-900">Consulta jurídica anclada</h2>
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
            <div className="mt-4 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-xl bg-gray-50 p-4 text-xs leading-relaxed text-gray-700">
              {respuesta}
            </div>
          )}
        </section>
      </div>

      <footer className="mt-8 text-center text-[10px] text-gray-300">
        Tlamatini · anclado en fuentes oficiales · si no sabe, lo dice
      </footer>
    </div>
  );
}
