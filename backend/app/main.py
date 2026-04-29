"""FastAPI entry point.

Boots the app, runs adapter discovery once at startup so all in-tree adapters
under `app.adapters.sources` and any third-party plugins (entry_points group
'sourcing.adapters') are registered before the first request.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters import discover_all
from app.api.adapters_routes import router as adapters_router
from app.api.job_orders_routes import router as job_orders_router
from app.api.search_routes import router as search_router
from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("sourcing")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Register all adapters before serving traffic
    discover_all()
    logger.info("Adapter discovery complete")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Sourcing — Blue-Collar Candidate Sourcing",
        description="National US candidate sourcing for staffing agencies. Pluggable source adapters, internal DB, multi-poster, compliance tracker.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(adapters_router)
    app.include_router(search_router)
    app.include_router(job_orders_router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
