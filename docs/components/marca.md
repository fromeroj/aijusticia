# Componente: Marca / GTM

**Qué es**: los activos de venta y difusión. Solo LECTURA del producto.

## Piezas
- `brand/www/` — tlamatini.live (sitio standalone del modelo).
- `brand/deck/` — pitch deck (HTML + LaTeX/Beamer + PDF). **Fuente de verdad**: `brand/deck/latex/pitch-deck.tex` → `make` → copiar `pitch-deck.pdf` a `brand/deck/aijusticia-pitch-deck.pdf`.
- `docs/article-draft.md` — artículo técnico (corpus, metodología de cosecha).

## Cifras canónicas (14-oct — tomadas de /corpus/status, NO de memoria)
473,848 docs · 14.1M chunks · ~3.9B tokens · 32/32 estados con ley consolidada
(26,470 códigos) · DOF diario automatizado · batería de evaluación 8 casos.

## Regla
Al actualizar cifras: primero `curl https://aijusticia.mx/corpus/status`, luego editar
tex+html juntos, `make` en latex, verificar PDF, commit.
