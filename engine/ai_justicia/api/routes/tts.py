"""TTS — Text-to-Speech de Izel vía MiniMax (speech-2.8-hd, voz ale-castilla-es)."""
from __future__ import annotations

import json
import logging
import urllib.request

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ai_justicia.auth.deps import actor_actual
from ai_justicia.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tts", tags=["tts"])

MINIMAX_API = "https://api.minimax.io/v1/t2a_v2"


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)


@router.post("")
def text_to_speech(req: TTSRequest, actor: dict = Depends(actor_actual)):
    """Texto → audio mp3 (voz de Izel). Retorna audio/mpeg como StreamingResponse."""
    key = settings.minimax_api_key
    if not key:
        raise HTTPException(503, "TTS no configurado (MINIMAX_API_KEY)")

    payload = json.dumps({
        "model": settings.tts_model,
        "text": req.text[:5000],
        "stream": False,
        "voice_setting": {
            "voice_id": settings.tts_voice,
            "speed": settings.tts_speed,
            "vol": 1.0,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
        "language_boost": "Spanish",
    }).encode()

    http_req = urllib.request.Request(MINIMAX_API, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
        "User-Agent": "AIJusticia/1.0",
    })

    try:
        with urllib.request.urlopen(http_req, timeout=60) as resp:
            result = json.loads(resp.read())
    except Exception as e:
        logger.error("TTS MiniMax error: %s", str(e)[:200])
        raise HTTPException(502, "Error de TTS")

    code = (result.get("base_resp") or {}).get("status_code", 0)
    audio_hex = (result.get("data") or {}).get("audio", "")
    if code != 0 or not audio_hex:
        msg = (result.get("base_resp") or {}).get("status_msg", "sin audio")
        logger.error("TTS MiniMax: code=%s msg=%s", code, msg)
        raise HTTPException(502, f"TTS error: {msg}")

    import io
    audio_bytes = bytes.fromhex(audio_hex)
    logger.info("TTS OK: %d chars → %d bytes mp3", len(req.text), len(audio_bytes))

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        io.BytesIO(audio_bytes),
        media_type="audio/mpeg",
        headers={"Content-Disposition": "inline; filename=izel.mp3"},
    )
