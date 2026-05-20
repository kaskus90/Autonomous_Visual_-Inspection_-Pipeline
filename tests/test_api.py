import os
import sys

# Must be set before importing anything that reads settings
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["MQTT_BROKER"] = "localhost"
os.environ["MQTT_PORT"] = "1883"
os.environ["MQTT_TOPIC"] = "test/detections"
os.environ["ALERT_DEFECT_RATE_THRESHOLD"] = "5"
os.environ["ALERT_WEBHOOK_URL"] = ""

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_detections_returns_list():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/detections")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_stats_returns_expected_shape():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/detections/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_detections" in data
    assert "defects_last_minute" in data
    assert "top_classes" in data


@pytest.mark.asyncio
async def test_alert_config_get_and_set():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/alerts/config")
        assert resp.status_code == 200

        resp = await client.post(
            "/alerts/config",
            json={"defect_rate_threshold": 10, "window_seconds": 120},
        )
        assert resp.status_code == 200
        assert resp.json()["defect_rate_threshold"] == 10


@pytest.mark.asyncio
async def test_alert_history_returns_list():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/alerts/history")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
