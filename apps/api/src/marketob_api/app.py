"""Application factory; no credentials or database connection required on import."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from marketob_api import __version__
from marketob_api.actions import router as action_router
from marketob_api.auth_routes import router as auth_router
from marketob_api.bot_routes import router as bot_router
from marketob_api.channels import router as channel_router
from marketob_api.config import Settings
from marketob_api.database import Pools
from marketob_api.errors import install_error_handlers
from marketob_api.favorites import router as favorites_router
from marketob_api.health import LiveStatus, ReadyStatus, database_status
from marketob_api.ingestion import router as ingestion_router
from marketob_api.observability import ObservationMiddleware
from marketob_api.personal_pages import router as pages_router
from marketob_api.privacy import router as privacy_router
from marketob_api.sharing import router as sharing_router
from marketob_api.teams import router as team_router
from marketob_api.transport import ProtocolMiddleware
from marketob_api.updates import router as updates_router
from marketob_api.web_routes import router as web_router


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = (settings if settings is not None else Settings()).model_copy()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        pools = Pools(configuration) if configuration.database_url is not None else None
        configuration._database_pools = pools
        try:
            yield
        finally:
            configuration._database_pools = None
            if pools:
                pools.close()

    application = FastAPI(
        lifespan=lifespan,
        title="MarkeTOB local API",
        version=__version__,
        description=(
            "Health, local identity, bots, ingestion, channels and durable request delivery. "
            "Runtime OpenAPI lists implemented routes only."
        ),
        docs_url=None,
        redoc_url=None,
    )
    install_error_handlers(application)
    application.add_middleware(ProtocolMiddleware)
    application.add_middleware(ObservationMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configuration.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "X-CSRF-Token",
            "Authorization",
            "Idempotency-Key",
            "If-None-Match",
            "X-Workspace-ID",
        ],
        expose_headers=["ETag", "X-Request-ID", "Retry-After"],
    )
    application.include_router(auth_router(configuration))
    application.include_router(bot_router(configuration))
    application.include_router(ingestion_router(configuration))
    application.include_router(channel_router(configuration))
    application.include_router(action_router(configuration))
    application.include_router(web_router())
    application.include_router(team_router(configuration))
    application.include_router(favorites_router(configuration))
    application.include_router(pages_router(configuration))
    application.include_router(sharing_router(configuration))
    application.include_router(updates_router(configuration))
    application.include_router(privacy_router(configuration))

    @application.get("/", include_in_schema=False)
    def index() -> dict[str, str]:
        return {
            "service": "MarkeTOB",
            "stage": "actions",
            "liveness": "/health/live",
            "readiness": "/health/ready",
            "implemented_api": "/openapi.json",
            "web": "/app/",
        }

    @application.get("/health/live", tags=["operations"])
    def liveness(response: Response) -> LiveStatus:
        response.headers["Cache-Control"] = "no-store"
        return LiveStatus(version=__version__)

    @application.get("/health/ready", tags=["operations"], responses={503: {"model": ReadyStatus}})
    def readiness(response: Response) -> ReadyStatus:
        database = database_status(configuration)
        response.headers["Cache-Control"] = "no-store"
        response.status_code = 200 if database == "ok" else 503
        return ReadyStatus(status="ready" if database == "ok" else "not_ready", database=database)

    return application
