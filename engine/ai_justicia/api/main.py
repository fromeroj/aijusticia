"""API REST del motor AI Justicia (FastAPI).

Assembly principal: crea la app, registra routers, middleware.
Los endpoints viven en ai_justicia.api.routes.*.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_justicia.api.routes import admin, archivos, auth, bufetes, dossiers, email, practica, query, tts
from ai_justicia.config import settings
from ai_justicia.llm.client import check_connection

logging.basicConfig(level=settings.log_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AI Justicia API iniciando — LLM: %s", settings.lmstudio_base_url)
    conn = check_connection()
    if conn["ok"]:
        logger.info("LLM OK: %s (llm=%s)", conn["base_url"], conn["llm_loaded"])
    else:
        logger.warning("LLM no disponible: %s", conn.get("error"))
    yield
    logger.info("AI Justicia API deteniéndose")


app = FastAPI(
    title="AI Justicia — Motor LLM + RAG",
    description="IA jurídica mexicana con citas verificadas contra fuentes oficiales.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router)
app.include_router(auth.router)
app.include_router(dossiers.router)
app.include_router(admin.router)
app.include_router(bufetes.router)
app.include_router(archivos.router)
app.include_router(email.router)
app.include_router(practica.router)
app.include_router(tts.router)


def run() -> None:
    """Arranque directo (sin uvicorn CLI) para desarrollo."""
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
