import logging

from fastapi import FastAPI

from apps.settings import load_settings
from apps.diet.api import build_diet_router
from apps.keep.api import build_keep_router


def create_app() -> FastAPI:
    settings = load_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    app = FastAPI(title="Backend", version="0.1.0")

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "service": "backend",
            "gemini_model": settings.gemini_model_name,
            "internal_auth_enabled": bool(settings.internal_token),
        }

    app.include_router(build_diet_router(settings))
    app.include_router(build_keep_router(settings))
    return app


app = create_app()


