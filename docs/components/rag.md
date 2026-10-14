# Componente: RAG (recuperación)

**Qué es**: convierte una pregunta en pasajes de ley verificables.
**Vive en**: `engine/ai_justicia/retrieval/` (busqueda_fts) + `engine/ai_justicia/api/routes/chat_stream.py::_buscar_en_ley` (usada por el chat).

## Pipeline del chat (el que importa)
1. **Fase 1 (barata)**: pool de ≤1500 docs por `titulo_search` (FTS), filtro de título `^(ley|código|reglamento|constitución|decreto|acuerdo)`.
2. **Fase 2**: chunks del pool; ORDER BY `cobertura` (frases del usuario) DESC, luego `rank × (es_articulo?1.5:1) × recencia` — recencia `1+1.2·e^(−edad/180d)`.
3. **Rama determinística de recientes** (`_buscar_recientes`): SIEMPRE busca en DOF ≤150 días; solo instrumentos normativos; boost ×2.2 a decretos de reforma; alias número↔palabra; limpia el nav del DOF conservando `DOF: fecha DECRETO…`; fecha de publicación explícita en cada pasaje; recientes van PRIMEROS.
4. Límites de payload: 6 pasajes, título 140 chars, fragmento 260 (para el panel); Izel ve 400 chars/pasaje.

## Por qué así (hallazgos medidos)
- Sin pre-corte por título: statement timeout (el filtro de decretos multiplicó candidatos ×10).
- El anti-boilerplate viejo (`DECRETO+reform` → ×0.05) mataba los decretos de reforma — hoy solo aplica a chunks cortos (<300 chars).
- `ts_rank_cd` premia repetición densa; sin boost de título/recencia, leyes estatales densas tumban al decreto correcto.

## Contrato de calidad
`python3 engine/scripts/eval_bateria_prod.py --guardar` — 8 casos con claves del corpus.
**Gate**: ningún cambio al retrieval sin batería antes/después.

## Conocido
- B3/B5 ocasionalmente fallan por atención de M3 (el pasaje llega, el modelo lo ignora).
- LeysesBiblio consolidadas: 14 canónicas con texto vigente (`LB:<code>`); 11 códigos 404.
