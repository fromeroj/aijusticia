"use client";

/**
 * Panel del expediente: lo que el sistema YA sabe del caso del usuario.
 * Drawer lateral — transparencia del estado interno del pipeline.
 * F3: sección Documentos — bóveda del caso con subida, OCR y versiones.
 */
import { useEffect, useRef, useState } from "react";
import { ClipboardList, X, FileText, Upload, Loader2, History, ScanLine, Share2, UserCheck, ShieldOff, QrCode, Copy, Check, Clock, UserPlus, XCircle, Building2, MessageSquare } from "lucide-react";
import type { Expediente } from "@/lib/streamQuery";
import { listarDocumentos, subirDocumento, abrirDocumento, type DocBoveda } from "@/lib/boveda";
import { authFetch } from "@/lib/auth";
import { listarAccesos, revocarAcceso, type Acceso } from "@/lib/accesos";
import {
  crearInvitacion, estadoInvitaciones, revocarInvitacion,
  aceptarSolicitud, rechazarSolicitud, qrDataUrl, linkWhatsApp,
  type InvitacionCreada, type InvitacionViva, type SolicitudPendiente,
} from "@/lib/invitaciones";

// Campos legibles del expediente que produce el engine
const ETIQUETAS: Record<string, string> = {
  materia: "Materia",
  jurisdiccion: "Jurisdicción",
  entidad: "Entidad",
  tipo_procedimiento: "Tipo de procedimiento",
  fecha_hechos: "Fecha de los hechos",
  cuantia: "Cuantía",
  partes: "Partes involucradas",
  empleador: "Empleador",
  institucion: "Institución",
  contrato: "Contrato",
  plazo: "Plazo",
  documentos: "Documentos disponibles",
  hechos: "Hechos relevantes",
  // cualquier otra clave se muestra con su nombre humanizado
};

function humanizar(k: string): string {
  if (ETIQUETAS[k]) return ETIQUETAS[k];
  return k.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

function valorLegible(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return v.map(valorLegible).filter(Boolean).join(" · ");
  if (typeof v === "object") {
    return Object.entries(v as Record<string, unknown>)
      .map(([k, vv]) => `${humanizar(k)}: ${valorLegible(vv)}`)
      .join(" · ");
  }
  return "";
}

function tamanoLegible(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ExpedientePanel({
  expediente,
  abierto,
  onClose,
  dossierId,
  refresco,
  onDocumentoSubido,
  puedeCompartir,
}: {
  expediente: Expediente | null;
  abierto: boolean;
  onClose: () => void;
  dossierId?: string;
  refresco?: number;              // bump para recargar (subida desde el chat)
  onDocumentoSubido?: (nombre: string, metodo: string) => void;
  puedeCompartir?: boolean;       // ciudadano dueño del caso
}) {
  const [documentos, setDocumentos] = useState<DocBoveda[]>([]);
  const [subiendo, setSubiendo] = useState(false);
  const [errorSubida, setErrorSubida] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const versionDeRef = useRef<number | undefined>(undefined);

  // compartir (E1: invitaciones tipadas — parte/asesor, persona/firma)
  const [accesos, setAccesos] = useState<Acceso[]>([]);
  const [invitaciones, setInvitaciones] = useState<InvitacionViva[]>([]);
  const [solicitudes, setSolicitudes] = useState<SolicitudPendiente[]>([]);
  const [nuevaInvitacion, setNuevaInvitacion] = useState<InvitacionCreada | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [creandoInv, setCreandoInv] = useState(false);
  const [copiado, setCopiado] = useState(false);
  const [errorInv, setErrorInv] = useState<string | null>(null);
  const [invTipo, setInvTipo] = useState<{ relacion: "asesor" | "parte"; para_bufete: boolean; rol: "lectura" | "edicion" }>(
    { relacion: "asesor", para_bufete: false, rol: "lectura" });
  const [notas, setNotas] = useState<{ id: string; texto: string; creado_en: string; autor: string }[]>([]);

  const cargarCompartir = (dId: string) => {
    listarAccesos(dId).then(setAccesos).catch(() => setAccesos([]));
    estadoInvitaciones(dId)
      .then((d) => {
        setInvitaciones(d?.invitaciones ?? []);
        setSolicitudes(d?.solicitudes ?? []);
      })
      .catch(() => { setInvitaciones([]); setSolicitudes([]); });
  };

  useEffect(() => {
    if (abierto && dossierId) {
      listarDocumentos(dossierId).then(setDocumentos).catch(() => setDocumentos([]));
      if (puedeCompartir) cargarCompartir(dossierId);
      authFetch(`/bufetes/casos/${dossierId}/notas`)
        .then((r) => (r.ok ? r.json() : { notas: [] }))
        .then((d) => setNotas(d.notas ?? []))
        .catch(() => setNotas([]));
      setNuevaInvitacion(null);
      setQr(null);
    }
  }, [abierto, dossierId, refresco, puedeCompartir]);

  const invitar = async () => {
    if (!dossierId) return;
    setCreandoInv(true);
    setErrorInv(null);
    try {
      const inv = await crearInvitacion(dossierId, invTipo);
      if (!inv) throw new Error("No se pudo crear la invitación");
      setNuevaInvitacion(inv);
      setQr(await qrDataUrl(inv.url));
      cargarCompartir(dossierId);
    } catch (e) {
      setErrorInv(e instanceof Error ? e.message : "Error al crear invitación");
    } finally {
      setCreandoInv(false);
    }
  };

  const copiarCodigo = async () => {
    if (!nuevaInvitacion) return;
    await navigator.clipboard?.writeText(nuevaInvitacion.codigo).catch(() => {});
    setCopiado(true);
    setTimeout(() => setCopiado(false), 2000);
  };

  const quitarAcceso = async (accesoId: number) => {
    if (!dossierId) return;
    await revocarAcceso(dossierId, accesoId).catch(() => false);
    cargarCompartir(dossierId);
  };

  const resolverSolicitud = async (invId: string, acepta: boolean) => {
    if (!dossierId) return;
    await (acepta ? aceptarSolicitud(dossierId, invId) : rechazarSolicitud(dossierId, invId))
      .catch(() => false);
    cargarCompartir(dossierId);
  };

  const elegirArchivo = (versionDe?: number) => {
    versionDeRef.current = versionDe;
    inputRef.current?.click();
  };

  const subir = async (file: File) => {
    if (!dossierId) return;
    setSubiendo(true);
    setErrorSubida(null);
    try {
      await subirDocumento(dossierId, file, versionDeRef.current);
      setDocumentos(await listarDocumentos(dossierId));
      onDocumentoSubido?.(file.name, "");
    } catch (e) {
      setErrorSubida(e instanceof Error ? e.message : "No se pudo subir");
    } finally {
      setSubiendo(false);
      versionDeRef.current = undefined;
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  if (!abierto) return null;

  const entradas = expediente
    ? Object.entries(expediente as unknown as Record<string, unknown>)
        .map(([k, v]) => [k, valorLegible(v)] as const)
        .filter(([, v]) => v && v.length > 1 && v !== "null")
    : [];

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/30" onClick={onClose}>
      <div
        className="h-full w-full max-w-sm overflow-y-auto bg-white p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ClipboardList className="h-5 w-5 text-[#047857]" />
            <h3 className="text-sm font-semibold text-gray-900">Tu expediente</h3>
          </div>
          <button onClick={onClose} className="rounded-lg p-1 text-gray-400 hover:bg-gray-100">
            <X className="h-5 w-5" />
          </button>
        </div>

        <p className="mb-4 text-xs leading-relaxed text-gray-500">
          Esto es lo que el sistema ha entendido de tu caso a partir de tus respuestas. Se acumula
          con cada pregunta — no necesitas repetir nada.
        </p>

        {entradas.length === 0 ? (
          <div className="rounded-xl border border-dashed border-gray-200 p-6 text-center">
            <p className="text-sm text-gray-400">
              Aún no hay datos.
              <br />
              Cuéntanos tu situación y el expediente se irá construyendo.
            </p>
          </div>
        ) : (
          <dl className="space-y-3">
            {entradas.map(([k, v]) => (
              <div key={k} className="rounded-lg bg-gray-50 px-3 py-2.5">
                <dt className="text-[11px] font-medium uppercase tracking-wide text-gray-400">
                  {humanizar(k)}
                </dt>
                <dd className="mt-0.5 text-sm text-gray-800">{v}</dd>
              </div>
            ))}
          </dl>
        )}

        {/* ── Documentos (bóveda) ── */}
        {dossierId && (
          <div className="mt-6 border-t border-gray-100 pt-5">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-[#047857]" />
                <h4 className="text-xs font-semibold text-gray-900">Documentos del caso</h4>
              </div>
              <button
                onClick={() => elegirArchivo()}
                disabled={subiendo}
                className="flex items-center gap-1 rounded-lg bg-[#047857]/10 px-2.5 py-1.5 text-[11px] font-semibold text-[#047857] hover:bg-[#047857]/20 disabled:opacity-40"
              >
                {subiendo ? <Loader2 className="h-3 w-3 animate-spin" /> : <Upload className="h-3 w-3" />}
                Subir
              </button>
              <input
                ref={inputRef}
                type="file"
                className="hidden"
                accept=".pdf,.jpg,.jpeg,.png,.webp,.tif,.tiff,.bmp"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) subir(f);
                }}
              />
            </div>
            <p className="mb-3 text-[11px] leading-relaxed text-gray-400">
              Contratos, recibos, fotos… Se extrae el texto (OCR si es escaneado) e
              Izel puede citarlos al responder.
            </p>
            {errorSubida && (
              <p className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-[11px] text-red-600">{errorSubida}</p>
            )}
            {documentos.length === 0 ? (
              <p className="rounded-xl border border-dashed border-gray-200 px-3 py-4 text-center text-[11px] text-gray-400">
                Sin documentos aún
              </p>
            ) : (
              <ul className="space-y-1.5">
                {documentos.map((d) => (
                  <li key={d.id} className="group rounded-lg border border-gray-100 px-3 py-2 hover:border-gray-200">
                    <button
                      onClick={() => abrirDocumento(d)}
                      className="flex w-full items-center gap-2 text-left"
                      title="Abrir / descargar"
                    >
                      <FileText className="h-3.5 w-3.5 shrink-0 text-gray-400" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-xs font-medium text-gray-800">
                          {d.nombre}
                          {d.version > 1 && <span className="ml-1 text-gray-400">v{d.version}</span>}
                        </span>
                        <span className="block text-[10px] text-gray-400">
                          {tamanoLegible(d.tamano_bytes)}
                          {d.metodo_texto === "ocr" && (
                            <span className="ml-1 inline-flex items-center gap-0.5 text-[#047857]">
                              <ScanLine className="h-2.5 w-2.5" /> OCR
                            </span>
                          )}
                          {d.metodo_texto === "pdf_digital" && <span className="ml-1 text-[#047857]">texto ✓</span>}
                        </span>
                      </span>
                    </button>
                    <button
                      onClick={() => elegirArchivo(d.id)}
                      disabled={subiendo}
                      className="mt-1 hidden items-center gap-1 text-[10px] text-gray-400 hover:text-[#047857] group-hover:flex"
                      title="Subir una versión nueva de este documento"
                    >
                      <History className="h-3 w-3" /> versión nueva
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* ── Notas del caso ── */}
        {dossierId && notas.length > 0 && (
          <div className="mt-6 border-t border-gray-100 pt-5">
            <div className="mb-2 flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-[#047857]" />
              <h4 className="text-xs font-semibold text-gray-900">Notas del caso</h4>
            </div>
            <div className="max-h-48 space-y-2 overflow-y-auto">
              {notas.map((n) => (
                <div key={n.id} className="rounded-lg bg-amber-50/60 px-3 py-2">
                  <p className="whitespace-pre-wrap text-[11px] text-gray-800">{n.texto}</p>
                  <p className="mt-1 text-[9px] text-gray-400">
                    {n.autor} · {new Date(n.creado_en).toLocaleString("es-MX", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Compartir con abogado (F4b: código + QR + handshake) ── */}
        {dossierId && puedeCompartir && (
          <div className="mt-6 border-t border-gray-100 pt-5">
            <div className="mb-2 flex items-center gap-2">
              <Share2 className="h-4 w-4 text-[#047857]" />
              <h4 className="text-xs font-semibold text-gray-900">Invitar a mi abogado</h4>
            </div>
            <p className="mb-3 text-[11px] leading-relaxed text-gray-400">
              Genera un código y pásaselo a tu abogado (WhatsApp o en persona). Él lo
              canjea, tú aceptas con un click — y puedes revocar cuando quieras.
              El caso siempre es tuyo.
            </p>
            {errorInv && (
              <p className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-[11px] text-red-600">{errorInv}</p>
            )}

            {/* solicitudes pendientes: el abogado ya canjeó, falta tu click */}
            {solicitudes.map((s) => (
              <div key={s.id} className="mb-2 rounded-xl border border-[#047857]/30 bg-[#ecfdf5] px-3 py-2.5">
                <div className="flex items-center gap-1.5 text-xs font-medium text-gray-900">
                  <UserPlus className="h-3.5 w-3.5 text-[#047857]" />
                  {s.firma || "Un abogado"} {s.verificado && (
                    <span className="rounded-full bg-[#047857]/10 px-1.5 py-0.5 text-[9px] font-semibold text-[#047857]">✓ verificado</span>
                  )}
                  <span className="font-normal text-gray-400">solicita acceso</span>
                </div>
                <p className="mt-0.5 text-[10px] text-gray-400">
                  {(s.especialidades ?? []).join(" · ") || "práctica general"}
                </p>
                <div className="mt-2 flex gap-2">
                  <button
                    onClick={() => resolverSolicitud(s.id, true)}
                    className="flex-1 rounded-lg bg-[#047857] px-2 py-1.5 text-[11px] font-semibold text-white hover:bg-[#036c4c]"
                  >
                    Aceptar
                  </button>
                  <button
                    onClick={() => resolverSolicitud(s.id, false)}
                    className="flex-1 rounded-lg border border-gray-200 px-2 py-1.5 text-[11px] font-medium text-gray-500 hover:bg-gray-50"
                  >
                    Rechazar
                  </button>
                </div>
              </div>
            ))}

            {/* invitación recién creada: código grande + QR + compartir */}
            {nuevaInvitacion && (
              <div className="mb-3 rounded-xl border border-gray-200 bg-gray-50 p-4 text-center">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">
                  Código de invitación (vence en {nuevaInvitacion.ttl_horas} h)
                </p>
                <p className="my-2 font-mono text-xl font-bold tracking-[0.2em] text-gray-900">
                  {nuevaInvitacion.codigo}
                </p>
                {qr && (
                  <img src={qr} alt="QR de invitación" className="mx-auto h-36 w-36 rounded-lg border border-gray-200 bg-white" />
                )}
                <div className="mt-3 flex gap-2">
                  <button
                    onClick={copiarCodigo}
                    className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-white px-2 py-2 text-[11px] font-semibold text-gray-700 ring-1 ring-gray-200 hover:bg-gray-100"
                  >
                    {copiado ? <Check className="h-3.5 w-3.5 text-[#047857]" /> : <Copy className="h-3.5 w-3.5" />}
                    {copiado ? "Copiado" : "Copiar código"}
                  </button>
                  <a
                    href={linkWhatsApp(nuevaInvitacion.url)}
                    target="_blank"
                    rel="noreferrer"
                    className="flex flex-1 items-center justify-center rounded-lg bg-[#25D366]/15 px-2 py-2 text-[11px] font-semibold text-[#128C4A] hover:bg-[#25D366]/25"
                  >
                    WhatsApp
                  </a>
                </div>
                <p className="mt-2 text-[10px] text-gray-400">
                  Muestra el QR en persona o comparte el enlace — el abogado entra y lo canjea.
                </p>
              </div>
            )}

            {/* accesos activos */}
            {accesos.filter((a) => !a.revocado_en).map((a) => (
              <div key={a.id} className="mb-1.5 flex items-center gap-2 rounded-lg border border-[#047857]/25 bg-[#ecfdf5] px-3 py-2">
                <UserCheck className="h-3.5 w-3.5 shrink-0 text-[#047857]" />
                <span className="min-w-0 flex-1 truncate text-xs text-gray-800">
                  {a.beneficiario || "Abogado"} · {a.rol}
                </span>
                <button
                  onClick={() => quitarAcceso(a.id)}
                  className="flex items-center gap-1 text-[10px] text-gray-400 hover:text-red-500"
                  title="Revocar acceso"
                >
                  <ShieldOff className="h-3 w-3" /> revocar
                </button>
              </div>
            ))}

            {/* invitaciones vivas (sin código — solo estado) */}
            {invitaciones.filter((i) => i.estado === "activa").map((i) => (
              <div key={i.id} className="mb-1.5 flex items-center gap-2 rounded-lg border border-dashed border-gray-200 px-3 py-2 text-[11px] text-gray-400">
                <Clock className="h-3 w-3" />
                <span className="flex-1">Invitación activa · vence {new Date(i.expira_en).toLocaleString("es-MX", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
                <button
                  onClick={() => revocarInvitacion(dossierId!, i.id).then(() => cargarCompartir(dossierId!))}
                  className="flex items-center gap-1 text-[10px] hover:text-red-500"
                >
                  <XCircle className="h-3 w-3" /> cancelar
                </button>
              </div>
            ))}
            {invitaciones.some((i) => i.estado === "solicitada") && (
              <p className="mb-1.5 flex items-center gap-1.5 rounded-lg bg-amber-50 px-3 py-2 text-[11px] text-amber-700">
                <QrCode className="h-3 w-3" /> Tu código fue canjeado — revisa la solicitud arriba.
              </p>
            )}

            {/* opciones de la invitación antes de generar */}
            {!nuevaInvitacion && (
              <div className="mb-2 space-y-2 rounded-xl bg-gray-50 px-3 py-2.5">
                <div className="flex items-center gap-2 text-[11px]">
                  <span className="w-16 text-gray-500">Invitar a</span>
                  {([["asesor", "Asesor"], ["parte", "Contraparte"]] as const).map(([v, label]) => (
                    <button
                      key={v}
                      onClick={() => setInvTipo({ ...invTipo, relacion: v, rol: v === "parte" ? "edicion" : "lectura" })}
                      className={`rounded-full px-2.5 py-1 font-semibold transition ${invTipo.relacion === v ? "bg-[#047857] text-white" : "bg-white text-gray-500 ring-1 ring-gray-200"}`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <div className="flex items-center gap-2 text-[11px]">
                  <span className="w-16 text-gray-500">Destino</span>
                  <button
                    onClick={() => setInvTipo({ ...invTipo, para_bufete: !invTipo.para_bufete })}
                    className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 font-semibold transition ${invTipo.para_bufete ? "bg-[#047857] text-white" : "bg-white text-gray-500 ring-1 ring-gray-200"}`}
                  >
                    <Building2 className="h-3 w-3" />
                    {invTipo.para_bufete ? "Despacho (la firma asigna a sus abogados)" : "Persona"}
                  </button>
                </div>
                {invTipo.relacion === "parte" && !invTipo.para_bufete && (
                  <p className="text-[10px] text-gray-400">
                    La contraparte podrá ver el expediente y subir documentos (edición) para
                    colaborar, p. ej. en un contrato.
                  </p>
                )}
              </div>
            )}

            <button
              onClick={invitar}
              disabled={creandoInv}
              className="w-full rounded-xl bg-[#047857]/10 px-3 py-2 text-[11px] font-semibold text-[#047857] hover:bg-[#047857]/20 disabled:opacity-40"
            >
              {creandoInv ? "Generando…" : "Generar código de invitación"}
            </button>

            {accesos.some((a) => a.revocado_en) && (
              <p className="mt-2 text-[10px] text-gray-300">
                {accesos.filter((a) => a.revocado_en).length} acceso(s) revocado(s) en el historial
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
