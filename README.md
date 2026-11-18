# AI Justicia — aijusticia.mx

Asistente jurídico mexicano con dos capas: **Izel** (chat conversacional con
streaming) + **Bibliotecario** (recuperación de leyes verificadas), sobre un
corpus oficial de 473K documentos (DOF diario, SJF, leyes consolidadas de los
32 estados, sentencias, gacetas).

## Empezar aquí

1. [`docs/ARQUITECTURA-SISTEMA.md`](docs/ARQUITECTURA-SISTEMA.md) — **arquitectura completa**: subsistemas, módulos, servers, puertos
2. [`DEPLOYMENT.md`](DEPLOYMENT.md) — producción: operación, diagnóstico, crons
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
