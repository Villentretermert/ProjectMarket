"""Photo bytes obey the same real PostgreSQL lifecycle and ACL as product content."""

from copy import deepcopy
from typing import Any

import pytest
from fastapi.testclient import TestClient
from marketob_api.config import Settings

from tests.test_channels import edit, path, publish
from tests.test_identity import client, register
from tests.test_identity import settings as settings
from tests.test_ingestion import gateway as gateway
from tests.test_product_images import product_message

pytestmark = pytest.mark.integration


def test_photo_ingest_replay_acl_update_remove(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    body = product_message()
    body["channel_id"] = source["channel_id"]
    body["resource_id"] = "item_one"
    first = bot.post("/v1/bot/messages", json=body)
    assert first.status_code == 200
    assert bot.post("/v1/bot/messages", json=body).json() == first.json()
    bad = deepcopy(body)
    bad["payload"]["image"]["data_base64"] = "AAAA"
    assert bot.post("/v1/bot/messages", json=bad).json()["code"] == "invalid_image"
    changed = deepcopy(body)
    changed["payload"]["image"]["alt"] = "Changed description"
    assert bot.post("/v1/bot/messages", json=changed).json()["code"] == "idempotency_conflict"
    layout = edit(source)
    layout["layout"]["blocks"][0].update(content_type="product", view="card")
    assert owner.put(path(source), json=layout).status_code == 200
    publish(owner, source)
    url = "/v1/channels/" + source["slug"]
    encoded = body["payload"]["image"]["data_base64"]
    with client(settings) as reader, client(settings) as anonymous:
        register(reader, "photo_reader")
        user_id = reader.get("/v1/auth/session").json()["user"]["user_id"]
        assert anonymous.get(url).status_code == 404
        assert reader.get(url).status_code == 404
        assert encoded not in reader.get(url).text
        grant = path(source, "/grants/" + user_id)
        assert owner.put(grant, json={}).status_code == 204
        snapshot = reader.get(url)
        assert snapshot.json()["records"][0]["content"]["image"] == body["payload"]["image"]
        assert snapshot.headers["cache-control"] == "no-store"
        assert owner.delete(grant).status_code == 204
        assert reader.get(url).status_code == 404
        assert encoded not in reader.get(url).text
    changed.update(message_id="photo_two", source_revision=2)
    assert bot.post("/v1/bot/messages", json=changed).status_code == 200
    assert owner.get(url).json()["records"][0]["content"]["image"]["alt"] == "Changed description"
    changed.update(message_id="photo_three", source_revision=3)
    del changed["payload"]["image"]
    assert bot.post("/v1/bot/messages", json=changed).status_code == 200
    assert "image" not in owner.get(url).json()["records"][0]["content"]
