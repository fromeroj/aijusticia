# Componente: Eval (calidad — el árbitro)

**Qué es**: la medición que gobierna cambios. Sin verde aquí, no se deploya.
**Vive en**: `eval/` (batería de producción + corridas), `models/tlamatini/eval_bateria.py` (30 preguntas ciudadanas para checkpoints), `data/ingestion/source_health` (DB).

## Batería de producción
`python3 eval/eval_bateria_prod.py --guardar [--solo B1,B3] [--url …]`
- 8 casos B/C contra el chat vivo: patrones requeridos/prohibidos en la respuesta
  + títulos esperados en el panel de leyes + salud del stream.
- Claves construidas del propio corpus (decretos verificados texto en mano).
- Salida: `eval/runs/bateria_*.json` — historial para regresiones.
- Estado 13-oct: **6-7/8 estricto**, varianza ±1 = muestreo de M3 (los fallos
  residuales son de atención del modelo; el retrieval entrega los pasajes correctos).

## Uso como gate
- Cambio en retrieval/agents: correr antes y después — mismo score o mejor.
- Checkpoint de Tlamatini: `eval_bateria.py` (offline) + `eval_bateria_prod` apuntando
  al endpoint del checkpoint (`--url`) — A/B directo contra MiniMax.

## Fuente de los casos
Las preguntas B (recencia) nacieron como pruebas para distinguir competidores con
corpus anual vs diario — B1 jornada 40h (DOF 03-mar/01-may-2026), B2 nacionalidad
única (DOF 07-oct-2026), B3 El Buen Fin (DOF 30-sep-2026). Ver `VISION.md` §principios.
