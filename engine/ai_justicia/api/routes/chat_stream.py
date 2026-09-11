"""Chat conversacional directo — streaming real del LLM.

Un solo prompt con TODO el contexto. Streaming token a token.
Sin pipeline de 7 etapas, sin NLI, sin micro-llamadas de preparación.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid as _uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ai_justicia.auth.deps import actor_actual
from ai_justicia.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat_stream"])

SYSTEM_PROMPT = """\
Eres Izel, asistente jurídica mexicana de AI Justicia.

CONOCIMIENTO: derecho mexicano — constitución, códigos federales y estatales, leyes, jurisprudencia del SJF, doctrina.

PERSONALIDAD:
- Empática primero: si el usuario tiene un problema, reconócelo.
- Conversacional: haz preguntas naturales como un abogado en su despacho, no formularios.
- Si necesitas más información, responde parcialmente con lo que sabes Y haz 2-3 preguntas naturales.
- Siempre respondes. Nunca te abstienes.
- Cuando el usuario responda, da la respuesta completa usando toda la información acumulada.
- Usa markdown para estructurar respuestas largas.

CITACIÓN OBLIGATORIA DE LEY:
- SIEMPRE identifica la ley específica por nombre: "Conforme al artículo 56 de la Ley Federal de Protección al Consumidor..."
- SIEMPRE menciona el artículo: art. 56 LFPC, art. 1914 CCF, art. 87 LFT, etc.
- NO digas solo "[1]" — di el nombre de la ley y el artículo EN TU RESPUESTA.
- Si los pasajes incluyen texto de una ley, busca DENTRO de ese texto el artículo relevante y cítalo.

ESTILO:
- Lenguaje simple ("tú") para ciudadanos, técnico para abogados.
- Máximo 2 oraciones de disclaimer al final.
- Si el monto es alto o el caso es grave, sugiere consultar un abogado.
"""


class ChatStreamRequest(BaseModel):
    consulta: str = Field(..., min_length=1, max_length=4000)
    nivel: str = Field("Nivel0")
    dossier_id: str | None = Field(None, max_length=64)
    historial: list[dict] | None = None


@router.post("/chat/stream")
async def chat_stream(req: ChatStreamRequest, request=Depends(actor_actual)):
    """Chat conversacional con streaming real. actor = JWT claims."""
    actor = request

    # cargar contexto del caso
    contexto = ""
    dossier_id = None
    if req.dossier_id:
        try:
            did = _uuid.UUID(req.dossier_id)
            aid = _uuid.UUID(actor["sub"])
            bid = _uuid.UUID(actor["bufete"]) if actor.get("bufete") else None
            from ai_justicia.dossiers import store as dstore, boveda, gestion
            nivel = dstore.tiene_acceso(did, aid, bid)
            if nivel:
                dossier_id = did
                d = dstore.obtener_dossier(did)
                if d and d.get("expediente"):
                    exp = d["expediente"]
                    nombre = exp.get("nombre", "")
                    hechos = "; ".join(
                        f"{k}: {v}" for k, v in (exp.get("hechos") or {}).items() if v
                    )
                    contexto += f"\nCASO: {nombre} ({d.get('materia', '')})\n"
                    if hechos:
                        contexto += f"HECHOS: {hechos[:800]}\n"
                docs = boveda.textos_para_contexto(did, max_chars=6000)
                if docs:
                    contexto += f"\nDOCUMENTOS DEL CASO:\n{docs}\n"
                notas = gestion.listar_notas(did)
                if notas:
                    notas_text = "\n".join(
                        f"[{n.get('autor', '?')}]: {n['texto'][:200]}" for n in notas[-5:]
                    )
                    contexto += f"\nNOTAS:\n{notas_text}\n"
        except Exception:
            pass

    # ── TRIAGE jurídico: identifica ley/institución/términos antes de buscar ──
    triage = {}
    try:
        from ai_justicia.tools.triage import identificar_dominio
        triage = identificar_dominio(req.consulta)
    except Exception:
        pass

    # RAG retrieval — usa términos legales del triage para mejor matching
    pasajes_text = ""
    pasajes = []
    try:
        from ai_justicia.retrieval.fts_index import busqueda_fts

        query_legal = req.consulta
        if triage.get("terminos_busqueda"):
            query_legal = " ".join(triage["terminos_busqueda"][:5])
        if triage.get("ley"):
            query_legal += f" {triage['ley']}"

        pasajes = busqueda_fts(query_legal, None, top_k=12)
        if not pasajes:
            pasajes = busqueda_fts(req.consulta, None, top_k=12)

        # Para ciudadanos (Nivel0): leyes primero, jurisprudencia después
        if req.nivel in ("Nivel0", None):
            leyes = [p for p in pasajes if p.fuente in ("LeyesBiblio", "LexMX")]
            otros = [p for p in pasajes if p.fuente not in ("LeyesBiblio", "LexMX")]
            pasajes = leyes + otros[:max(0, 8 - len(leyes))]

        if pasajes:
            pasajes_text = "\n".join(
                f"[{i}] FUENTE: {p.fuente} | LEY: {p.titulo[:80]} | TEXTO: {p.texto[:400]}"
                for i, p in enumerate(pasajes, 1)
            )
    except Exception:
        pass

    # construir messages
    system = SYSTEM_PROMPT

    # inyectar triage jurídico: Izel sabe qué ley/institución aplica
    if triage.get("ley"):
        system += f"\n\nTRIAGE JURÍDICO IDENTIFICADO:"
        system += f"\n- Ley probable: {triage['ley']}"
        if triage.get("institucion"):
            system += f"\n- Institución: {triage['institucion']}"
        system += "\n- USA esta información para enfocar tu respuesta. Cita los artículos de esta ley si los pasajes los contienen."

    if req.nivel in ("Nivel0", None) or req.nivel == "Nivel0":
        system += "\n\nFUENTE PRIORITARIA: Base tus respuestas en LEYES Y CÓDIGOS vigentes (LeyesBiblio, LexMX), NO en jurisprudencia específica (SJF) ni en casos concretos. El ciudadano necesita saber qué dice la LEY, no qué resolvió un juez en otro caso."

    if req.nivel in ("Nivel1", "Nivel2"):
        system += "\n\nEl usuario es un abogado: usa lenguaje técnico, responde directo, sin disclaimers de 'consulta a un abogado'."

    if contexto:
        system += f"\n\nCONTEXTO DEL CASO:\n{contexto[:8000]}"

    if pasajes_text:
        system += f"\n\nPASAJES DEL CORPUS (cítalos como [n] donde apoyen tu respuesta):\n{pasajes_text[:6000]}"

    messages = [{"role": "system", "content": system}]

    # historial (últimos 10 turnos)
    for h in (req.historial or [])[-10:]:
        rol = "user" if h.get("rol", "user") == "user" else "assistant"
        texto = h.get("texto", "")
        if texto:
            messages.append({"role": rol, "content": texto})

    messages.append({"role": "user", "content": req.consulta})

    # ── streaming generator ──
    async def generate():
        from openai import OpenAI
        client = OpenAI(
            base_url=settings.lmstudio_base_url,
            api_key=settings.lmstudio_api_key,
            timeout=120.0,
        )
        full_text = ""
        in_think = False
        try:
            stream = client.chat.completions.create(
                model=settings.lmstudio_llm_model,
                messages=messages,
                temperature=0.2,
                max_tokens=4096,
                stream=True,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            async for chunk in _iter_async(stream):
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    token = delta.content
                    full_text += token
                    # filtrar <think> blocks durante streaming
                    if "<think>" in full_text and "</think>" not in full_text:
                        continue
                    if "</think>" in full_text:
                        token = token.split("</think>")[-1]
                        if not token:
                            continue
                    yield _sse("token", token)

            # limpiar thinking si existe
            import re
            clean = re.sub(r"<think>.*?</think>", "", full_text, flags=re.S).strip()
            if clean != full_text:
                full_text = clean

            yield _sse("done", {
                "respuesta": full_text,
                "abstenido": False,
                "pasajes": [],
                "traza_id": None,
                "n_oraciones": 0,
                "n_sustentadas": 0,
                "citas": [],
                "dossier_id": str(dossier_id) if dossier_id else None,
            })

            # persistir mensajes en caso_chat
            if dossier_id:
                try:
                    from ai_justicia.dossiers import chat as chat_store
                    chat_store.guardar(dossier_id, "user", req.consulta, _uuid.UUID(actor["sub"]))
                    chat_store.guardar(dossier_id, "izel", full_text)
                except Exception:
                    pass

        except Exception as e:
            logger.error("chat_stream: %s", str(e)[:300])
            yield _sse("error", {"mensaje": str(e)[:200]})

    async def _iter_async(sync_iter):
        """Wraps sync iterator for async context."""
        while True:
            try:
                chunk = next(sync_iter)
                yield chunk
                await asyncio.sleep(0)
            except StopIteration:
                break

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
