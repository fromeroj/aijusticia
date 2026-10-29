# Componente: Izel (+ Bibliotecario)

**Qué es**: el agente conversacional del producto. Izel responde; el Bibliotecario
es su subagente de leyes (corre en paralelo, identifica ley+terminos, busca pasajes).
**Vive en**: `engine/ai_justicia/api/routes/chat_stream.py` (⚠️ 500+ líneas —
pendiente extraer a `agents/{izel,bibliotecario,guardas}.py`, gate: batería igual antes/después).

## Contrato con el frontend (SSE `POST /chat/stream`)
Eventos: `token` (texto), `laws` (panel de pasajes: fuente/título/texto/artículo/fecha),
`done`, `reset` (borrar y reintentar), `error`. Request: `{consulta, historial[]}`.

## Guardas de MiniMax-M3 (hard-won)
- Purga CJK por token (desliza chino en español).
- Stream 100% `<think>` = vacío → reintento (3 intentos; el 3º con 5000 tokens).
- Degeneración (repetición) → reset + reintento con temperatura distinta.
- Prompts: español mexicano de tú (nunca voseo), fechas SOLO del pasaje,
  "gana el pasaje fresco", pasajes irrelevantes se declaran, nunca inventar artículos.

## LLM
- Hoy: **MiniMax-M2.7** (desde 29-oct-2026). El 28-oct MiniMax cambió M3
  server-side: piensa SIEMPRE (ignora `enable_thinking:false`) → streams vacíos
  (el thinking quema el presupuesto antes del contenido). Sintomático: respuestas
  de 2-6 chars, silencios de 100-170s, sin paneles de leyes.
  Swap de emergencia a M2.7 vía `LMSTUDIO_LLM_MODEL` (una env var — el contrato
  OpenAI-compatible diseñado para esto). **M2.7: confiable pero más débil**
  (batería 3/8 vs 6-7/8 de M3 sano).
- Mañana: Tlamatini detrás del mismo contrato — la dependencia de un proveedor
  que cambia modelos debajo de ti quedó demostrada en producción.
