"""Application factory; no credentials or database connection required on import."""

from fastapi import FastAPI, Response

from marketob_api import __version__
from marketob_api.config import Settings
from marketob_api.health import LiveStatus, ReadyStatus, database_status


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings if settings is not None else Settings()
    application = FastAPI(
        title="MarkeTOB API foundation",
        version=__version__,
        description=(
            "PM-005 health endpoints only. Product API implementation follows in PM-006–018."
        ),
        docs_url=None,
        redoc_url=None,
    )

    @application.get("/", include_in_schema=False)
    def index() -> dict[str, str]:
        return {
            "service": "MarkeTOB",
            "stage": "foundation",
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
