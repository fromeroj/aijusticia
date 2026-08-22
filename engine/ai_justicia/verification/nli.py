"""Etapa 5(b): prueba de implicación (NLI) pasaje⇒oración.

Verifica que el pasaje recuperado realmente implica la oración que lo cita.
Etiquetas (preservar exactas del plan):
  - entails: el pasaje sostiene la oración
  - contradice: el pasaje contradice la oración
  - desconocido: el pasaje no da info suficiente

Detecta "fuga de citas": el LLM cita un documento pero usa hechos que no están en él.

Implementación dual:
  1. LLM (Qwen3.6-35B-A3B) por defecto — entiende español jurídico nativamente y
     captura inferencias legales que un modelo NLI monolingüe (inglés) pierde.
     Es el mismo modelo que generó la respuesta, así que el criterio de
     "sustento" es coherente con el razonamiento jurídico.
  2. Modelo NLI ligero (transformers, DeBERTa-NLI) como alternativa rápida —
     útil para pre-filtrado o cuando el LLM no está disponible. Nota: los modelos
     DeBERTa-NLI estándar son monolingües (inglés); para español se recomienda
     un modelo multilingüe o el modo LLM.

El umbral NLI_ENTAILMENT_THRESHOLD define la probabilidad mínima de "entails"
para dar por buena una cita (solo aplica en modo transformers; en modo LLM
la decisión es categórica).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ai_justicia.config import settings

logger = logging.getLogger(__name__)

# Etiquetas exactas del plan (sección 7.5 etapa 5)
LABEL_ENTAILS = "entails"
LABEL_CONTRADICE = "contradice"
LABEL_DESCONOCIDO = "desconocido"

# Cache del modelo NLI (carga perezosa)
_nli_pipeline = None
_nli_mode: str | None = None  # "transformers" | "llm" | None


@dataclass
class ResultadoNLI:
    etiqueta: str           # entails | contradice | desconocido
    score: float            # probabilidad (si aplica) o 1.0/0.0
    modo: str               # "transformers" o "llm"


def probar_implicacion(pasaje: str, oracion: str) -> ResultadoNLI:
    """Prueba si el pasaje implica la oración.

    Devuelve ResultadoNLI con la etiqueta y score.
    """
    global _nli_mode
    if _nli_mode is None:
        _nli_mode = _detectar_modo()

    if _nli_mode == "transformers":
        return _nli_transformers(pasaje, oracion)
    return _nli_llm(pasaje, oracion)


def _detectar_modo() -> str:
    """Detecta el modo de NLI.

    Por defecto usa el LLM (mejor para español jurídico). El modo transformers
    se activa si la variable de entorno NLI_MODE=transformers está presente.
    """
    import os
    modo = os.environ.get("NLI_MODE", "llm").lower()
    if modo == "transformers":
        try:
            import transformers  # noqa: F401
            logger.info("NLI: modo transformers (forzado por NLI_MODE)")
            return "transformers"
        except ImportError:
            logger.warning("NLI_MODE=transformers pero transformers no instalado; usando LLM")
    logger.info("NLI: modo LLM (default, mejor para español jurídico)")
    return "llm"


def _nli_transformers(pasaje: str, oracion: str) -> ResultadoNLI:
    """NLI con modelo DeBERTa-v3 ligero via transformers (MPS en Mac)."""
    global _nli_pipeline
    if _nli_pipeline is None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        logger.info("Cargando modelo NLI (DeBERTa) en %s…", device)
        model_name = "cross-encoder/nli-deberta-v3-base"
        tok = AutoTokenizer.from_pretrained(model_name)
        mod = AutoModelForSequenceClassification.from_pretrained(model_name)
        _nli_pipeline = pipeline("text-classification", model=mod, tokenizer=tok, device=device)
        logger.info("Modelo NLI cargado")

    # Formato NLI: premisa [SEP] hipótesis
    resultado = _nli_pipeline(
        {"text": pasaje, "text_pair": oracion},
        top_k=None,
    )
    # Mapear etiquetas del modelo a nuestras etiquetas
    scores = {r["label"].lower(): r["score"] for r in resultado}
    # cross-encoder/nli-deberta usa labels: entailment, neutral, contradiction
    ent = scores.get("entailment", 0.0)
    contra = scores.get("contradiction", 0.0)
    neut = scores.get("neutral", 0.0)

    if ent >= contra and ent >= neut:
        return ResultadoNLI(etiqueta=LABEL_ENTAILS, score=float(ent), modo="transformers")
    if contra > neut:
        return ResultadoNLI(etiqueta=LABEL_CONTRADICE, score=float(contra), modo="transformers")
    return ResultadoNLI(etiqueta=LABEL_DESCONOCIDO, score=float(neut), modo="transformers")


def _nli_llm(pasaje: str, oracion: str) -> ResultadoNLI:
    """NLI usando el LLM (modo por defecto, mejor para español jurídico)."""
    from ai_justicia.llm.client import get_llm_client

    prompt = f"""\
Eres un verificador de citas jurídicas. Determina la relación entre el PASAJE
(fuente oficial) y la ORACIÓN (afirmación del asistente).

PASAJE:
{pasaje[:800]}

ORACIÓN:
{oracion[:400]}

Responde con EXACTAMENTE UNA de estas tres palabras, nada más:
- entails — el pasaje sostiene o implica directamente la oración
- contradice — el pasaje contradice la oración
- desconocido — el pasaje no da información suficiente sobre la oración

Sé estricto: si la oración afirma algo que el pasaje no dice explícitamente o
no se infiere claramente del pasaje, responde "desconocido".

Respuesta:"""

    client = get_llm_client()
    resp = client.chat(
        [{"role": "user", "content": prompt}],
        max_tokens=16384, temperature=0.0,
    )
    resp_lower = resp.strip().lower()
    if "entail" in resp_lower:
        return ResultadoNLI(etiqueta=LABEL_ENTAILS, score=1.0, modo="llm")
    if "contrad" in resp_lower:
        return ResultadoNLI(etiqueta=LABEL_CONTRADICE, score=0.0, modo="llm")
    return ResultadoNLI(etiqueta=LABEL_DESCONOCIDO, score=0.5, modo="llm")


def pasar_umbral(resultado: ResultadoNLI) -> bool:
    """True si el resultado NLI pasa el umbral de entailment."""
    return (
        resultado.etiqueta == LABEL_ENTAILS
        and resultado.score >= settings.nli_entailment_threshold
    )
