from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI

from common.http.errorHandler import addErrorHandlers


def createFastApiApp(title: str, registerRoutes: Callable[[FastAPI], None]) -> FastAPI:
    app = FastAPI(title=title, version="1.0.0")
    addErrorHandlers(app)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": title}

    registerRoutes(app)
    return app
