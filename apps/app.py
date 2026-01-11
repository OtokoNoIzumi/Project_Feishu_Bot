"""
Main Application Entry Point.

Configures and initializes the FastAPI application, including logging,
routers, and health checks.
"""

import logging

from fastapi import FastAPI

from apps.settings import load_settings
from apps.diet.api import build_diet_router
from apps.keep.api import build_keep_router
from apps.common.storage_api import build_storage_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    settings = load_settings()
    # Configure logging: info level for app, warning for noisy refs
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    # Silence httpx/httpcore (used by google-genai)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("google.genai").setLevel(logging.WARNING)

    fastapi_app = FastAPI(title="Backend", version="0.1.0")

    @fastapi_app.get("/health")
    async def health():
        return {
            "status": "ok",
            "service": "backend",
            "gemini_model": settings.gemini_model_name,
            "internal_auth_enabled": bool(settings.internal_token),
        }

    fastapi_app.include_router(build_diet_router(settings))
    fastapi_app.include_router(build_keep_router(settings))
    fastapi_app.include_router(build_storage_router(settings))
    return fastapi_app


app = create_app()
