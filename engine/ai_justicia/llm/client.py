"""Cliente de inferencia LLM — adapter sobre la API OpenAI-compatible.

El motor nunca acopla lógica de negocio al backend de inferencia. Toda llamada
pasa por este cliente, que apunta a LM Studio en dev (localhost:1234/v1) y puede
swapearse a vLLM (producción Nivel 2, on-premise) o a un proveedor cloud
(Together / Fireworks / Groq) sin tocar el resto del código.

Modelos disponibles en LM Studio (verificado):
  - qwen3.6-35b-a3b                     (LLM base, generación)
  - text-embedding-nomic-embed-text-v1.5 (embeddings para el índice vectorial)
  - laguna-s-2.1-mlx                    (segundo modelo)
"""

from __future__ import annotations

import logging
from typing import Protocol

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from ai_justicia.config import settings

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Contrato del cliente de inferencia. Cualquier backend lo implementa."""

    def chat(self, messages: list[dict], *, temperature: float | None = None,
             max_tokens: int = 65536, stop: list[str] | None = None) -> str:
        """Generación chat. Devuelve el texto del primer choice."""
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embeddings de un lote de textos. Devuelve vectores."""
        ...


class LMStudioClient:
    """Cliente contra LM Studio (API OpenAI-compatible en localhost:1234/v1).

    Es el backend por defecto en desarrollo. En producción Nivel 2 se sustituye
    por vLLMClient apuntando a la URL del nodo on-premise; la interfaz es idéntica.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        llm_model: str | None = None,
        embed_model: str | None = None,
    ):
        self.llm_model = llm_model or settings.lmstudio_llm_model
        self.embed_model = embed_model or settings.lmstudio_embed_model
        self._client = OpenAI(
            base_url=base_url or settings.lmstudio_base_url,
            api_key=api_key or settings.lmstudio_api_key,
            timeout=settings.llm_timeout,
        )
        # Cliente separado para embeddings (siempre LM Studio)
        embed_url = getattr(settings, 'embed_base_url', None) or settings.lmstudio_base_url
        self._embed_client = OpenAI(
            base_url=embed_url,
            api_key=api_key or settings.lmstudio_api_key,
            timeout=60.0,
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    def chat(
        self,
        messages: list[dict],
        *,
        temperature: float | None = None,
        max_tokens: int = 65536,
        stop: list[str] | None = None,
    ) -> str:
        """Generación chat. Devuelve el texto del primer choice.

        Si el backend es mlx_lm.server (con LoRA adapter), pasa
        enable_thinking=False para respuesta directa sin razonamiento.
        Si es LM Studio, el modelo de razonamiento produce reasoning_content
        que se descarta.
        """
        temp = settings.llm_temperature if temperature is None else temperature
        logger.debug("LLM chat: model=%s, temp=%s, msgs=%d", self.llm_model, temp, len(messages))

        # Build kwargs - add chat_template_kwargs for mlx_lm.server (LoRA)
        kwargs = dict(
            model=self.llm_model,
            messages=messages,
            temperature=temp,
            max_tokens=max_tokens,
            stop=stop,
        )
        # If using LoRA server (non-empty adapter path), disable thinking
        # OpenAI SDK doesn't support chat_template_kwargs natively, so use extra_body
        # mlx_lm.server reads it from the request body
        if settings.lora_adapter_path:
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}

        resp = self._client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content or ""
        finish = resp.choices[0].finish_reason

        def _limpiar(texto: str) -> str:
            # Modelos de razonamiento (M3, Qwen thinking) meten <think> inline.
            import re as _re
            # bloque cerrado
            texto = _re.sub(r"<think>.*?</think>\s*", "", texto, flags=_re.DOTALL)
            # bloque TRUNCADO por max_tokens: <think> sin cierre — tirar todo
            if "<think>" in texto:
                texto = texto.split("<think>", 1)[0]
            return texto.strip()

        content = _limpiar(content)

        # Modelos de razonamiento con presupuesto corto: el <think> consumió
        # todo el cupo y el contenido quedó vacío o cortado a mitad de razonamiento.
        # Reintentar UNA vez con presupuesto ampliado — mínimo 10k: un thinking
        # model puede quemar 5-8k solo en razonamiento antes de la respuesta.
        # (fail-open: la etapa de arriba prefiere respuesta larga a respuesta vacía)
        if (not content or finish == "length") and max_tokens < 10240:
            kwargs["max_tokens"] = max(10240, max_tokens * 8)
            resp = self._client.chat.completions.create(**kwargs)
            content = _limpiar(resp.choices[0].message.content or "")

        # El modelo suele anteponer saltos de línea tras el bloque de razonamiento
        return content.strip()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not settings.embeddings_habilitados:
            logger.debug("Embeddings deshabilitados — devolviendo vacío")
            return []
        logger.debug("Embed: model=%s, n=%d", self.embed_model, len(texts))
        resp = self._embed_client.embeddings.create(model=self.embed_model, input=texts)
        # Ordenar por index por si el servidor reordena
        return [d.embedding for d in sorted(resp.data, key=lambda x: x.index)]


# --- Singleton perezoso ---
_default_client: LMStudioClient | None = None


def get_llm_client() -> LMStudioClient:
    """Devuelve el cliente LLM por defecto (LM Studio). Singleton perezoso."""
    global _default_client
    if _default_client is None:
        _default_client = LMStudioClient()
    return _default_client


def check_connection() -> dict:
    """Verifica la conexión con el servidor de inferencia y los modelos disponibles.

    Útil para el endpoint /health y para diagnostics. Devuelve:
      {"ok": bool, "base_url": str, "models": [str], "llm_loaded": bool, "embed_loaded": bool}
    """
    try:
        client = OpenAI(
            base_url=settings.lmstudio_base_url,
            api_key=settings.lmstudio_api_key,
            timeout=10.0,
        )
        models = client.models.list()
        model_ids = [m.id for m in models.data]
        return {
            "ok": True,
            "base_url": settings.lmstudio_base_url,
            "models": model_ids,
            "llm_loaded": settings.lmstudio_llm_model in model_ids,
            "embed_loaded": settings.lmstudio_embed_model in model_ids,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "base_url": settings.lmstudio_base_url,
            "error": str(e),
            "models": [],
            "llm_loaded": False,
            "embed_loaded": False,
        }
