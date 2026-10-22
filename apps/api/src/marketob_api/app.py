"""Application factory; no credentials or database connection required on import."""

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from marketob_api import __version__
from marketob_api.actions import router as action_router
from marketob_api.auth_routes import router as auth_router
from marketob_api.bot_routes import router as bot_router
from marketob_api.channels import router as channel_router
from marketob_api.config import Settings
from marketob_api.errors import install_error_handlers
from marketob_api.health import LiveStatus, ReadyStatus, database_status
from marketob_api.ingestion import router as ingestion_router
from marketob_api.transport import ProtocolMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings if settings is not None else Settings()
    application = FastAPI(
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
        ],
        expose_headers=["ETag", "X-Request-ID", "Retry-After"],
    )
    application.include_router(auth_router(configuration))
    application.include_router(bot_router(configuration))
    application.include_router(ingestion_router(configuration))
    application.include_router(channel_router(configuration))
    application.include_router(action_router(configuration))

    @application.get("/", include_in_schema=False)
    def index() -> dict[str, str]:
        return {
            "service": "MarkeTOB",
            "stage": "actions",
            "liveness": "/health/live",
            "readiness": "/health/ready",
            "implemented_api": "/openapi.json",
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
