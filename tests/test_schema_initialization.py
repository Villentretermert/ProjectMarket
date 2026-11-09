"""Schema construction must not race warning contexts or serialize HTTP requests."""

import threading
import warnings
from concurrent.futures import ThreadPoolExecutor
from typing import Any, get_args

import pytest
from fastapi._compat import v2
from fastapi.testclient import TestClient
from marketob_api.app import create_app
from marketob_api.config import Settings
from pydantic import TypeAdapter
from pydantic.warnings import UnsupportedFieldAttributeWarning


def test_parallel_factories_restore_filters_and_preserve_parameter_schemas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_inside = threading.Event()
    second_inside = threading.Event()
    first_finished = threading.Event()
    local = threading.local()
    adapter, post_init = TypeAdapter, v2.ModelField.__post_init__

    def delayed_adapter(annotation: Any, **kwargs: Any) -> Any:
        metadata = get_args(annotation)
        if metadata and getattr(metadata[-1], "alias", None) == "limit" and not local.gated:
            local.gated = True
            if local.role == "first":
                first_inside.set()
                # Allow the second factory to overlap if startup is unguarded.
                second_inside.wait(0.1)
                local.finish_field = True
            else:
                second_inside.set()
                assert first_finished.wait(10), "First field never completed"
        return adapter(annotation, **kwargs)

    def finish_field(field: v2.ModelField) -> None:
        post_init(field)
        if getattr(local, "finish_field", False):
            local.finish_field = False
            first_finished.set()

    def build(role: str) -> dict[str, Any]:
        local.role, local.gated = role, False
        if role == "second":
            assert first_inside.wait(10), "First factory never reached its query fields"
        return dict(create_app(Settings(_env_file=None)).openapi())

    # Instrument only scheduling in the pinned FastAPI adapter, not validation behavior.
    monkeypatch.setattr(v2, "TypeAdapter", delayed_adapter)
    monkeypatch.setattr(v2.ModelField, "__post_init__", finish_field)
    with warnings.catch_warnings():
        warnings.simplefilter("error", UnsupportedFieldAttributeWarning)
        before = list(warnings.filters)
        with ThreadPoolExecutor(max_workers=2) as executor:
            specs = list(executor.map(build, ("first", "second")))
        assert warnings.filters == before
    assert specs[0] == specs[1]
    parameters = specs[0]["paths"]["/v1/bot/events"]["get"]["parameters"]
    limit = next(p for p in parameters if p["name"] == "limit")
    assert limit["in"] == "query"
    assert limit["schema"]["minimum"] == 1 and limit["schema"]["maximum"] == 100


def test_initialized_app_serves_concurrent_requests_and_validates_query_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    together = threading.Barrier(4, timeout=10)

    def readiness(_settings: Settings) -> str:
        # All four handlers must be running before any may complete.
        together.wait()
        return "not_configured"

    monkeypatch.setattr("marketob_api.app.database_status", readiness)
    with warnings.catch_warnings():
        warnings.simplefilter("error", UnsupportedFieldAttributeWarning)
        with TestClient(create_app(Settings(_env_file=None))) as http:
            with ThreadPoolExecutor(max_workers=4) as executor:
                replies = list(executor.map(lambda _: http.get("/health/ready"), range(4)))
                assert all(r.status_code == 503 for r in replies)
                assert all(r.json()["database"] == "not_configured" for r in replies)
                codes = list(
                    executor.map(
                        lambda limit: (
                            http.get("/v1/bot/events", params={"limit": limit}).status_code
                        ),
                        ("1", "100", "0", "101", "bad"),
                    )
                )
                assert codes == [503, 503, 422, 422, 422]
