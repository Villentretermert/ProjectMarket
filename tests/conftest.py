"""Unit tests never inherit a developer's real service configuration."""

import os

import pytest


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in os.environ:
        if name.startswith("MARKETOB_") and name != "MARKETOB_TEST_DATABASE_URL":
            monkeypatch.delenv(name)
