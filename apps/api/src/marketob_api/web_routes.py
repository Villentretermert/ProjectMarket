"""Ship the same-origin Web client inside the API wheel and Docker image."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

ASSETS = Path(__file__).with_name("web")
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
    "form-action 'self'"
)


def router() -> APIRouter:
    api = APIRouter(include_in_schema=False)

    @api.get("/app/")
    def index() -> FileResponse:
        return asset("index.html")

    @api.get("/app/{filename}")
    def asset(filename: str) -> FileResponse:
        # An explicit list also prevents accidentally shipping source or private files.
        if filename not in {
            "index.html",
            "styles.css",
            "app.js",
            "api.js",
            "dom.js",
            "render.js",
            "actions.js",
            "studio.js",
            "studio-editor.js",
            "favorites.js",
            "space.js",
            "sharing.js",
        }:
            from marketob_api.errors import ApiError

            raise ApiError(404, "object_not_found", "Asset not found.")
        return FileResponse(
            ASSETS / filename,
            headers={
                "Content-Security-Policy": CSP,
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            },
        )

    return api
