// Cosecha de tocas de Jalisco — corre en el MAIN world de la página
// (acceso a grecaptcha y a tu sesión real). Envía los PDFs en base64
// al receptor local (127.0.0.1:8765), que los guarda en data/jalisco/pdfs.

const BACK = "https://publica-sentencias-backend.stjjalisco.gob.mx";
const KEY = "6LeVK48tAAAAABtfSIPLusp-4cMthtofl497dZvX";
const RECEPTOR = "http://127.0.0.1:8765";
const LOTE = 25;          // tocas por ronda
const PAUSA_ENTRE = 1500; // ms entre descargas
const PAUSA_RONDA = 30000; // ms entre rondas
const ENFRIAMIENTO = 60000; // ms cuando el captcha rechaza

let corriendo = false;

function esperar(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function descargarUno(tocaId) {
  const token = await grecaptcha.execute(KEY, { action: "visitor_verify" });
  const r = await fetch(`${BACK}/toca/${tocaId}/file?modo=descargar`, {
    headers: { "X-Recaptcha-Token": token },
  });
  const j = await r.json();
  if (r.status !== 200 || !j.data || !j.data.url) {
    throw new Error(JSON.stringify(j).slice(0, 120));
  }
  const rp = await fetch(j.data.url);
  const b = await rp.arrayBuffer();
  let bin = "";
  const u8 = new Uint8Array(b);
  const CH = 32768;
  for (let i = 0; i < u8.length; i += CH) {
    bin += String.fromCharCode.apply(null, u8.subarray(i, i + CH));
  }
  return btoa(bin);
}

async function entregar(tocaId, file, b64) {
  const r = await fetch(`${RECEPTOR}/recibe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: tocaId, file, b64 }),
  });
  if (!r.ok) throw new Error("receptor " + r.status);
}

async function lote() {
  let pend;
  try {
    pend = await (await fetch(`${RECEPTOR}/pendientes?n=${LOTE}`)).json();
  } catch (e) {
    console.log("[AIJ] receptor no disponible");
    return;
  }
  if (!pend.length) {
    console.log("[AIJ] sin pendientes ✓");
    return;
  }
  console.log(`[AIJ] ronda de ${pend.length} tocas`);
  let fallos = 0;
  for (const t of pend) {
    try {
      const b64 = await descargarUno(t.id);
      await entregar(t.id, t.file, b64);
      console.log("[AIJ] ok", t.file);
      fallos = 0;
    } catch (e) {
      fallos++;
      console.log("[AIJ] fallo", t.file, String(e).slice(0, 90));
      await esperar(ENFRIAMIENTO);
      if (fallos >= 5) {
        console.log("[AIJ] 5 fallos seguidos — deteniendo ronda; recarga la página para reintentar");
        return;
      }
    }
    await esperar(PAUSA_ENTRE);
  }
}

async function bucle() {
  if (corriendo) return;
  corriendo = true;
  console.log("[AIJ] cosecha Jalisco activa — deja esta pestaña abierta");
  // eslint-disable-next-line no-constant-condition
  while (true) {
    try {
      await lote();
    } catch (e) {
      console.log("[AIJ]", String(e).slice(0, 120));
    }
    await esperar(PAUSA_RONDA);
  }
}

// arrancar cuando grecaptcha esté listo
(function t() {
  if (window.grecaptcha && window.grecaptcha.execute) {
    grecaptcha.ready(() => bucle());
  } else {
    setTimeout(t, 1000);
  }
})();
