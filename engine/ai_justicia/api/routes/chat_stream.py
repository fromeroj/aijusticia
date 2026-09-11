"""Chat conversacional con 2 agentes: Izel + Bibliotecario.

Izel: conversa con el usuario — empática, streaming inmediato (1-2s al
primer token). Sin RAG bloqueante delante.
Bibliotecario (subagente): corre EN PARALELO, identifica la ley aplicable,
busca pasajes en el corpus y los emite como evento "laws". El frontend los
muestra como "Referencias legales verificadas" y los devuelve en el
siguiente turno (`leyes_previas`) para que Izel cite con fundamento.

Flow por turno:
  1. Llega mensaje → lanza Bibliotecario (task async, no bloquea)
  2. Izel responde en streaming con las leyes_previas del turno anterior
  3. Cuando el Bibliotecario termina → evento "laws"
  4. done incluye los pasajes encontrados (para la tarjeta de referencias)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid as _uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ai_justicia.auth.deps import actor_opcional
from ai_justicia.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat_stream"])

# ── Prompts ────────────────────────────────────────────────────────────────

IZEL_CIUDADANO = """\
Eres Izel, asistente jurídica mexicana de AI Justicia. Hablas con un ciudadano.

FORMA DE TRABAJAR — conversación, no formulario:
- Empatía primero: reconoce la situación en una frase, sin dramatizar.
- Si falta contexto clave (tipo de contrato, monto, fecha, entidad, qué te respondieron),
  responde con lo que ya sabes Y haz 1-3 preguntas naturales, como un abogado en su
  despacho. Nunca interrogatorios.
- Si tienes información suficiente y PASAJES DE LEYES en tu contexto, da la respuesta
  completa: qué dice la ley, qué artículo te ampara, y los pasos concretos a seguir.
- Siempre respondes algo útil. Nunca te abstienes ni dices "no puedo ayudar".

CITAS:
- Cuando uses un PASAJE DE LEYES de tu contexto, cítalo inline como [1], [2]…
- Si una parte viene de tu conocimiento general (sin pasaje que la respalde),
  NO le pongas número de cita. Sé honesta con lo que es ley textual y lo que es orientación.

ESTILO: lenguaje simple, de tú, español mexicano. Markdown para estructurar (negritas,
listas cortas). Máximo 2 oraciones de disclaimer al final solo si el caso es grave.
"""

IZEL_ABOGADO = """\
Eres Izel, asistente jurídica para un despacho mexicano (AI Justicia). El usuario es
un abogado o personal del bufete.

- Directo y técnico. Sin disclaimers de "consulta a un abogado".
- Usa el contexto del caso (expediente, documentos de la bóveda, notas del equipo) cuando
  sea relevante — el equipo comparte este chat.
- Si hay PASAJES DE LEYES en tu contexto, cítalos inline como [1], [2]… y precisa
  artículo. Sin pasaje de respaldo, sin número de cita.
- Respuestas accionables: peticiones, plazos, artículos, estrategias. Markdown.
"""

BIBLIOTECARIO_PROMPT = """\
Eres el bibliotecario jurídico de AI Justicia. Dada la conversación entre un usuario
e Izel, identifica las normas mexicanas aplicables (máximo 3, la más relevante primero).
Cada nombre debe ser el nombre oficial de UNA ley o código — nunca combines dos.

Los "terminos_busqueda" deben ser palabras y frases que aparecerían TEXTUALMENTE en los
artículos aplicables de esas leyes: sustantivos del procedimiento y de la institución
(p. ej. "reclamación", "aclaración", "dictamen", "operaciones no reconocidas",
"devolución", la autoridad competente…). No repitas las palabras del usuario tal cual.

CONVERSACIÓN (la más reciente al final):
{conversacion}

Responde SOLO con JSON válido, sin explicaciones:
{{"leyes": ["Ley o Código 1", "Ley o Código 2"],
  "ley": "Ley o Código 1 (la principal, misma que la primera de la lista)",
  "institucion": "autoridad competente (CONDUSEF, PROFECO, juzgado laboral, etc.)",
  "terminos_busqueda": ["5 a 8 términos que aparecerían en los artículos aplicables"],
  "resumen_situacion": "una frase con la situación jurídica"}}
"""

_ART_RE = re.compile(r"[Aa]rt[íi]culo\s+(\d+[A-Z0-9]*(?:\s*(?:bis|ter|quater))?)")


def _clave_cita(texto: str) -> str:
    m = _ART_RE.search(texto or "")
    return f"art. {m.group(1)}" if m else "fragmento"


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class ChatStreamRequest(BaseModel):
    consulta: str = Field(..., min_length=1, max_length=8000)
    nivel: str = Field("Nivel0")
    dossier_id: str | None = Field(None, max_length=64)
    caso_id: str | None = Field(None, max_length=64)  # alias usado por Studio
    historial: list[dict] | None = None
    # Resultados del Bibliotecario de turnos anteriores (el frontend los devuelve)
    leyes_previas: list[dict] | None = None
    triage_previo: dict | None = None


# ── Contexto del caso (bloqueante — correr vía to_thread) ─────────────────

def _contexto_caso(dossier_id: str, actor: dict) -> tuple[str, str | None, list[dict]]:
    """(contexto_texto, error, historial_db). error != None si no hay acceso."""
    try:
        did = _uuid.UUID(dossier_id)
    except ValueError:
        return "", "dossier inválido", []

    try:
        from ai_justicia.dossiers import store as dstore

        aid = _uuid.UUID(actor["sub"])
        bid = _uuid.UUID(actor["bufete"]) if actor.get("bufete") else None
        if not dstore.tiene_acceso(did, aid, bid):
            return "", "sin acceso al caso", []
    except Exception as e:
        logger.warning("contexto acceso: %s", str(e)[:200])
        return "", "sin acceso al caso", []

    ctx = ""
    try:
        from ai_justicia.dossiers import boveda, gestion

        d = dstore.obtener_dossier(did)
        if d:
            exp = d.get("expediente") or {}
            nombre = exp.get("nombre") or d.get("titulo") or ""
            if nombre:
                ctx += f"CASO: {nombre} ({d.get('materia') or 'materia general'})\n"
            hechos = exp.get("hechos") or {}
            if hechos:
                txt = "; ".join(f"{k}: {v}" for k, v in hechos.items() if v)
                ctx += f"HECHOS: {txt[:800]}\n"
            docs = boveda.textos_para_contexto(did, max_chars=5000)
            if docs:
                ctx += f"DOCUMENTOS DE LA BÓVEDA:\n{docs}\n"
            notas = gestion.listar_notas(did)
            if notas:
                ctx += "NOTAS DEL EQUIPO:\n" + "\n".join(
                    f"- [{n.get('autor', '?')}] {n['texto'][:200]}" for n in notas[-4:]
                ) + "\n"
    except Exception as e:
        logger.warning("contexto cuerpo: %s", str(e)[:200])

    historial: list[dict] = []
    try:
        from ai_justicia.dossiers import chat as chat_store

        for m in chat_store.listar(did, limit=12):
            historial.append({"rol": m.get("rol", "user"), "texto": m.get("texto", "")})
    except Exception as e:
        logger.warning("contexto chat: %s", str(e)[:200])

    return ctx, None, historial


def _persistir(dossier_id: str, actor: dict, user_txt: str, izel_txt: str) -> None:
    try:
        from ai_justicia.dossiers import store as dstore, chat as chat_store

        did = _uuid.UUID(dossier_id)
        aid = _uuid.UUID(actor["sub"])
        bid = _uuid.UUID(actor["bufete"]) if actor.get("bufete") else None
        if not dstore.tiene_acceso(did, aid, bid):
            return
        chat_store.guardar(did, "user", user_txt, aid)
        chat_store.guardar(did, "izel", izel_txt)
    except Exception as e:
        logger.warning("persistir chat: %s", str(e)[:200])


# ── Bibliotecario (subagente) ──────────────────────────────────────────────

_STOP_LEY = {
    "ley", "del", "las", "los", "para", "por", "general", "federal",
    "mexico", "méxico", "estados", "unidos", "codigo", "código",
    "reglamento", "constitucion", "constitución", "ultima", "última",
    "nueva", "vigente", "reformada",
}


def _frase_a_tsquery(frase: str) -> str:
    """'operaciones no reconocidas' → '(operación<->no<->reconocida) | (operacion<->no<->reconocida)'."""
    palabras = [p for p in re.findall(r"[a-záéíóúñü0-9]+", frase.lower()) if len(p) > 1]
    if not palabras:
        return ""
    _MAPA = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n"}
    planas = [re.sub(r"[áéíóúüñ]", lambda m: _MAPA[m.group()], p) for p in palabras]
    con = "<->".join(palabras)
    sin = "<->".join(planas)
    return con if planas == palabras else f"({con}) | ({sin})"


def _buscar_en_ley(ley: str, terminos: list[str], top_k: int = 6) -> list[dict]:
    """Busca los artículos más relevantes DENTRO de la ley identificada.

    Ranking: cobertura (cuántas frases distintas toca el chunk) + ts_rank,
    con boost a chunks que INICIAN un artículo (el texto canónico).
    """
    palabras = [w for w in re.findall(r"[a-záéíóúñü]+", ley.lower())
                if w not in _STOP_LEY and len(w) > 3]
    if not palabras or not terminos:
        return []
    ley_q = " & ".join(palabras[:4])

    frases: list[str] = []
    for t in terminos[:7]:
        tq = _frase_a_tsquery(t)
        if tq and tq not in frases:
            frases.append(tq)
    if not frases:
        return []

    # relajación graduada: todas las frases → 3 → 1
    variantes = [frases, frases[:3], frases[:1]]

    filas: list = []
    try:
        from ai_justicia.corpus.store import get_conn

        with get_conn() as conn:
            cur = conn.cursor()
            for grupo in variantes:
                cobertura = " + ".join(
                    "(CASE WHEN c.texto_search @@ to_tsquery('spanish', %s) THEN 1 ELSE 0 END)"
                    for _ in grupo
                )
                sql = f"""
                    SELECT d.fuente, d.titulo, c.articulo_num, c.texto,
                           d.jerarquia, d.vinculante,
                           ({cobertura}) AS cobertura,
                           ts_rank_cd(c.texto_search, to_tsquery('spanish', %s)) AS rank,
                           (left(regexp_replace(c.texto, '\\s+', ' ', 'g'), 24)
                            ~ '^(Artículo|ARTÍCULO) ') AS es_articulo
                    FROM documentos_chunks c
                    JOIN documentos d ON c.documento_id = d.id
                    WHERE NOT d.derogado
                      AND d.fuente IN ('LeyesBiblio', 'LexMX', 'DOF')
                      AND left(d.titulo, 40) ~* '^(ley|código|codigo|reglamento|constitución|constitucion)'
                      AND d.titulo_search @@ to_tsquery('spanish', %s)
                      AND c.texto_search @@ to_tsquery('spanish', %s)
                    ORDER BY es_articulo DESC, cobertura DESC, rank DESC
                    LIMIT 24
                """
                params = [*grupo, " | ".join(grupo), ley_q, " | ".join(grupo)]
                cur.execute(sql, params)
                filas = cur.fetchall()
                if len(filas) >= 2:
                    break
    except Exception as e:
        logger.warning("buscar_en_ley: %s", str(e)[:200])
        return []

    # dedup por (título normalizado, artículo) — el corpus tiene versiones duplicadas
    vistos: set = set()
    out: list[dict] = []
    for fuente, titulo, articulo, texto, jerarquia, vinculante, _cob, _rank, _es_art in filas:
        clave = ((titulo or "").lower().strip()[:60], articulo or texto[:40])
        if clave in vistos:
            continue
        vistos.add(clave)
        out.append({
            "titulo": (titulo or ley)[:80],
            "fuente": fuente or "LeyesBiblio",
            "clave_cita": f"art. {articulo}" if articulo else _clave_cita(texto),
            "vinculante": bool(vinculante),
            "fragmento": (texto or "")[:350],
            "jerarquia": jerarquia if jerarquia is not None else 100,
        })
        if len(out) >= top_k:
            break
    return out


async def _bibliotecario(client, consulta: str, historial: list[dict]) -> dict | None:
    """Identifica ley aplicable + busca pasajes. None si no encuentra nada."""
    lineas = [
        f"{'U' if (h.get('rol') or h.get('role')) == 'user' else 'I'}: "
        f"{(h.get('texto') or h.get('text') or '')[:200]}"
        for h in historial[-4:]
    ]
    lineas.append(f"U: {consulta[:500]}")
    conv = "\n".join(lineas)

    try:
        # MiniMax-M3 razona dentro de <think> en content: darle presupuesto
        # para terminar de pensar y escribir el JSON
        r = await client.chat.completions.create(
            model=settings.lmstudio_llm_model,
            messages=[{"role": "user", "content": BIBLIOTECARIO_PROMPT.format(conversacion=conv[:2500])}],
            temperature=0.0,
            max_tokens=1500,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        raw = r.choices[0].message.content or ""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        triage = json.loads(m.group())
    except Exception as e:
        logger.warning("bibliotecario LLM: %s", str(e)[:200])
        return None

    ley = (triage.get("ley") or "").strip()
    leyes_lista = [l.strip() for l in (triage.get("leyes") or []) if isinstance(l, str) and l.strip()]
    if ley and ley not in leyes_lista:
        leyes_lista.insert(0, ley)
    leyes_lista = leyes_lista[:3] or ([ley] if ley else [])
    terminos = [t for t in (triage.get("terminos_busqueda") or []) if isinstance(t, str) and t]
    if not leyes_lista or not terminos:
        return None

    institucion = (triage.get("institucion") or "").strip()
    resumen = (triage.get("resumen_situacion") or "").strip()

    # Buscar DENTRO de cada ley identificada — el gesto del bibliotecario:
    # ya sabe qué libros son; busca en esos libros. Cuota por ley para que
    # la principal no aplaste a las demás.
    encontrados: list[dict] = []
    for ley_i in leyes_lista:
        encontrados += await asyncio.to_thread(_buscar_en_ley, ley_i, terminos, 3)
        if len(encontrados) >= 6:
            break
    pasajes = encontrados

    return {
        "ley": ley,
        "institucion": institucion,
        "resumen": resumen,
        "pasajes": [
            {"fuente": p["fuente"], "titulo": p["titulo"][:60],
             "texto": p["fragmento"][:160], "articulo": p["clave_cita"]}
            for p in pasajes[:4]
        ],
        "encontrados": encontrados,
    }


# ── Endpoint ───────────────────────────────────────────────────────────────

@router.post("/chat/stream")
async def chat_stream(req: ChatStreamRequest, actor=Depends(actor_opcional)):
    """Chat anónimo permitido: sin token responde igual (el Bibliotecario no
    necesita identidad); con dossier se verifican los accesos como siempre."""
    dossier_id = req.dossier_id or req.caso_id
    es_abogado = bool(actor) and actor.get("tier") in ("abogado", "despacho")

    # contexto del caso + historial persistido (fuera del event loop)
    contexto, err_acceso, historial_db = ("", None, [])
    if dossier_id and actor:
        contexto, err_acceso, historial_db = await asyncio.to_thread(
            _contexto_caso, dossier_id, actor
        )

    # historial: DB primero (más antiguo), luego el que mande el frontend
    historial = list(historial_db)
    for h in (req.historial or [])[-8:]:
        rol = h.get("rol") or h.get("role") or "user"
        txt = h.get("texto") or h.get("text") or ""
        if txt:
            historial.append({"rol": "user" if rol == "user" else "izel", "texto": txt})
    historial = historial[-12:]

    leyes_previas = req.leyes_previas or []
    triage_previo = req.triage_previo or {}

    async def generate():
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            base_url=settings.lmstudio_base_url,
            api_key=settings.lmstudio_api_key,
            timeout=150.0,
        )

        # 1) Bibliotecario en paralelo — no bloquea el primer token de Izel
        biblio_task = asyncio.create_task(
            _bibliotecario(client, req.consulta, historial)
        )

        # 2) Prompt de Izel
        system = IZEL_ABOGADO if es_abogado else IZEL_CIUDADANO
        if contexto:
            system += f"\n\nCONTEXTO DEL CASO:\n{contexto[:7000]}"
        nota_norma = ""
        if triage_previo.get("ley"):
            nota_norma = f" — norma: {triage_previo['ley']}"
        if leyes_previas:
            pasajes_txt = "\n".join(
                f"[{i}] ({p.get('fuente', '')} | {p.get('titulo', '')[:70]}) "
                f"{(p.get('fragmento') or p.get('texto') or '')[:400]}"
                for i, p in enumerate(leyes_previas[:6], 1)
            )
            system += (
                "\n\nPASAJES DE LEYES (verificados por el bibliotecario"
                f"{nota_norma}):\n{pasajes_txt[:6000]}"
            )

        messages = [{"role": "system", "content": system}]
        for h in historial:
            messages.append({
                "role": "user" if h["rol"] == "user" else "assistant",
                "content": h["texto"],
            })
        messages.append({"role": "user", "content": req.consulta})

        # 3) Izel en streaming — primer token ~1-2s.
        #    MiniMax-M3 emite <think>…</think> al inicio de content: suprimirlo
        #    del stream sin retener el resto. Si decae en repetición degenerada
        #    (glitch de muestreo de M3), se reintenta una vez.
        degenerado_re = re.compile(r"(.{1,8})\1{11,}$")

        def _degenerado(txt: str) -> bool:
            return bool(degenerado_re.search(txt[-120:])) if len(txt) > 60 else False

        async def _un_intento(temp: float, estado: dict):
            """Un intento de stream. Escribe texto/degenerado en `estado`."""
            full = ""
            pend = ""
            suprimiendo = False
            resuelto = False
            stream = await client.chat.completions.create(
                model=settings.lmstudio_llm_model,
                messages=messages,
                temperature=temp,
                frequency_penalty=0.1,
                max_tokens=3000,
                stream=True,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            try:
                async for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if not (delta and delta.content):
                        continue
                    t = delta.content
                    full += t
                    if resuelto:
                        yield t
                    else:
                        pend += t
                        if not suprimiendo:
                            if "<think>" in pend:
                                suprimiendo = True
                                pend = pend.split("<think>", 1)[1]
                            elif not "<think>".startswith(pend.lstrip()):
                                resuelto = True
                                if pend.strip():
                                    yield pend
                        else:
                            if "</think>" in pend:
                                rest = pend.split("</think>", 1)[1]
                                resuelto = True
                                if rest:
                                    yield rest
                    if _degenerado(full):
                        estado.update(texto=full, degenerado=True)
                        return
            finally:
                try:
                    await stream.close()
                except Exception:
                    pass
            estado.update(texto=full, degenerado=False)

        intentos = [0.3, 0.2] if not es_abogado else [0.2, 0.2]
        for i, temp in enumerate(intentos):
            estado: dict = {"texto": "", "degenerado": False}
            try:
                async for t in _un_intento(temp, estado):
                    yield _sse("token", t)
            except Exception as e:
                logger.error("izel stream: %s", str(e)[:300])
                if not estado["texto"] and i == len(intentos) - 1:
                    yield _sse("error", {"mensaje": f"Izel no pudo responder: {str(e)[:150]}"})
                break
            if not estado["degenerado"] and estado["texto"].strip():
                break
            if i < len(intentos) - 1:
                logger.warning("izel degenerado — reintentando (temp %s)", temp)
                yield _sse("reset", {})
        full_text = estado["texto"]

        clean = re.sub(r"<think>.*?</think>", "", full_text, flags=re.S).strip()
        # M3 a veces desliza caracteres CJK en texto español — nunca son válidos
        clean = re.sub(r"[\u3040-\u30ff\u4e00-\u9fff]+", "", clean)
        # colapsar cola repetida si ambos intentos degeneraron
        clean = re.sub(r"(.{1,8})\1{5,}$", r"\1", clean)

        # 4) Esperar al bibliotecario y emitir sus resultados
        leyes_nuevas = None
        try:
            leyes_nuevas = await asyncio.wait_for(biblio_task, timeout=120)
        except Exception as e:
            logger.warning("bibliotecario await: %s", str(e)[:200])
            biblio_task.cancel()

        if leyes_nuevas:
            yield _sse("laws", {
                "ley": leyes_nuevas["ley"],
                "institucion": leyes_nuevas["institucion"],
                "resumen": leyes_nuevas["resumen"],
                "pasajes": leyes_nuevas["pasajes"],
            })

        # 5) done — pasajes para la tarjeta de referencias
        #    prioridad: los del turno actual; si aún no hay, los previos
        encontrados = (leyes_nuevas or {}).get("encontrados") or leyes_previas
        encontrados = (encontrados or [])[:5]
        yield _sse("done", {
            "respuesta": clean,
            "abstenido": False,
            "ley": (leyes_nuevas or {}).get("ley") or triage_previo.get("ley"),
            "institucion": (leyes_nuevas or {}).get("institucion") or triage_previo.get("institucion"),
            "modo_verificacion": "bibliotecario",
            "n_oraciones": len(encontrados),
            "n_sustentadas": len(encontrados),
            "pasajes": encontrados,
            "dossier_id": dossier_id,
        })

        # 6) persistir (nunca guardar basura degenerada; sin actor no hay dueño)
        if dossier_id and actor and not err_acceso and clean and not _degenerado(clean):
            await asyncio.to_thread(_persistir, dossier_id, actor, req.consulta, clean)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
