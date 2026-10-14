/**
 * Cliente de la bóveda de documentos del dossier (F3).
 * Subida (con opción de versión nueva), listado y descarga — todo con JWT.
 */
import { authFetch, API_URL } from "./auth";

export interface DocBoveda {
  id: number;
  nombre: string;
  version: number;
  version_de: number | null;
  tipo_mime: string | null;
  tamano_bytes: number;
  metodo_texto: string | null;   // pdf_digital | ocr | sin_texto
  creado_en: string;
  length: number;                 // chars de texto extraído
  es_abogado: boolean;
}

export async function subirDocumento(
  dossierId: string,
  archivo: File,
  versionDe?: number,
): Promise<DocBoveda> {
  const form = new FormData();
  form.append("archivo", archivo);
  if (versionDe) form.append("version_de", String(versionDe));
  const r = await authFetch(`/dossiers/${dossierId}/documentos`, {
    method: "POST",
    body: form,
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(d.detail || `Error ${r.status}`);
  }
  return r.json();
}

export async function listarDocumentos(dossierId: string): Promise<DocBoveda[]> {
  const r = await authFetch(`/dossiers/${dossierId}/documentos`);
  if (!r.ok) return [];
  const d = await r.json();
  return d.documentos ?? [];
}

export function urlDescargar(docId: number): string {
  return `${API_URL}/documentos/${docId}/descargar`;
}

/** Click en un archivo respetando la preferencia del usuario (M4). */
export function abrirDocumento(doc: DocBoveda) {
  const pref = window.localStorage.getItem("aij_pref_archivo") ?? "descargar_y_abrir";
  const url = urlDescargar(doc.id);
  // editor: los documentos del ciudadano no viven en NC — por ahora descarga
  // (cuando el caso se comparte a un despacho con NC, ahí sí hay editor).
  const a = document.createElement("a");
  a.href = url;
  a.download = doc.nombre; // attachment: el SO decide si abrir con la app
  if (pref === "editor") {
    a.target = "_blank"; // intenta vista inline del navegador (PDF/imagen)
    a.download = "";
  }
  document.body.appendChild(a);
  a.click();
  a.remove();
}
