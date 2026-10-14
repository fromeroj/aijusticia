# AI Justicia — aijusticia.mx

Asistente jurídico mexicano con dos capas: **Izel** (chat conversacional con
streaming) + **Bibliotecario** (recuperación de leyes verificadas), sobre un
corpus oficial de 473K documentos (DOF diario, SJF, leyes consolidadas de los
32 estados, sentencias, gacetas).

## Empezar aquí

1. [`DEPLOYMENT.md`](DEPLOYMENT.md) — producción: topología real, operación, diagnóstico
2. [`docs/arquitectura-corpus-rag.md`](docs/arquitectura-corpus-rag.md) — corpus y retrieval (§8 = estado actual)
3. [`docs/INDEX.md`](docs/INDEX.md) — índice completo de documentación con estado por documento

## Layout (por subsistema — reordenado 14-oct)

```
engine/       API producto + agents (Izel) + retrieval (RAG)  [deploy: 162 /opt/aijusticia/engine]
apps/web/     Next.js aijusticia.mx                            [deploy: 162 /opt/aijusticia/app]
data/         Data consumer: harvesters/, ingestion/, quality/, prep/
models/tlamatini/  Entrenamiento Soup (CPT, merge, eval, GGUF) [ex tohil/]
eval/         Batería de evaluación + corridas
office/       Piloto Nextcloud/Collabora (migrándose a 162)    [ex pilot/]
brand/        deck + www (tlamatini.live)
infra/        deploy, crons, nginx
docs/         VISION.md (intent+colaboración), INDEX.md, components/, diseño
```

Mapa completo: [`docs/INDEX.md`](docs/INDEX.md)
