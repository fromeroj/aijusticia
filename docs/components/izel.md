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
- Hoy: MiniMax-M3 cloud (`https://api.minimax.io/v1`) vía env var.
- Mañana: Tlamatini detrás del mismo contrato OpenAI-compatible — swap sin tocar código.
