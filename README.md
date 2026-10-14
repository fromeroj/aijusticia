# AI Justicia — aijusticia.mx

Asistente jurídico mexicano con dos capas: **Izel** (chat conversacional con
streaming) + **Bibliotecario** (recuperación de leyes verificadas), sobre un
corpus oficial de 473K documentos (DOF diario, SJF, leyes consolidadas de los
32 estados, sentencias, gacetas).

## Empezar aquí

1. [`DEPLOYMENT.md`](DEPLOYMENT.md) — producción: topología real, operación, diagnóstico
2. [`docs/arquitectura-corpus-rag.md`](docs/arquitectura-corpus-rag.md) — corpus y retrieval (§8 = estado actual)
3. [`docs/INDEX.md`](docs/INDEX.md) — índice completo de documentación con estado por documento

## Layout

```
engine/   FastAPI + ingestión + retrieval + scripts de cosecha
app/      Next.js (aijusticia.mx)
tohil/    Entrenamiento Tlamatini (Soup CLI: CPT, merge, eval)
docs/     Diseño, specs, recon de portales, historial
pilot/    Piloto Nextcloud para bufetes
www/      Sitio tlamatini.live
deck/     Pitch deck
```
