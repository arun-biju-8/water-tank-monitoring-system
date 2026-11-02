"""
Unit and integration tests for the FastAPI Water Tank Monitoring Backend.
Covers:
- Pydantic schema validation (boundary checks, required fields, defaults)
- FastAPI endpoints (HTTP status codes, payload validation, health checks)
- Database error handling (503 Service Unavailable on DB connection loss)
- Mocked DB happy path for API endpoints
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app
from app.database import get_db
from app.schemas import WaterReadingCreate
from app.models import WaterReading


client = TestClient(app)


# ==============================================================================
# 1. Pydantic Schema Validation Tests
# ==============================================================================

def test_water_reading_schema_valid():
    """Valid reading payload should pass validation successfully."""
    payload = {
        "water_level": 75,
        "probe_25": True,
        "probe_50": True,
        "probe_75": True,
        "probe_100": False,
        "alarm": False,
        "muted": False,
    }
    reading = WaterReadingCreate(**payload)
    assert reading.water_level == 75
    assert reading.probe_25 is True
    assert reading.probe_100 is False
    assert reading.alarm is False
    assert reading.muted is False


def test_water_reading_schema_defaults():
    """Alarm and muted fields should default to False if omitted."""
    payload = {
        "water_level": 50,
        "probe_25": True,
        "probe_50": True,
        "probe_75": False,
        "probe_100": False,
    }
    reading = WaterReadingCreate(**payload)
    assert reading.alarm is False
    assert reading.muted is False


def test_water_reading_schema_upper_bound_violation():
    """Water level > 100 must fail validation."""
    payload = {
        "water_level": 105,
        "probe_25": True,
        "probe_50": True,
        "probe_75": True,
        "probe_100": True,
    }
    with pytest.raises(ValidationError) as exc_info:
        WaterReadingCreate(**payload)
    assert "water_level" in str(exc_info.value)


def test_water_reading_schema_lower_bound_violation():
    """Water level < 0 must fail validation."""
    payload = {
        "water_level": -5,
        "probe_25": False,
        "probe_50": False,
        "probe_75": False,
        "probe_100": False,
    }
    with pytest.raises(ValidationError) as exc_info:
        WaterReadingCreate(**payload)
    assert "water_level" in str(exc_info.value)


def test_water_reading_schema_missing_fields():
    """Missing required probe status must fail validation."""
    payload = {
        "water_level": 25,
        # missing probe_25, probe_50, probe_75, probe_100
    }
    with pytest.raises(ValidationError) as exc_info:
        WaterReadingCreate(**payload)
    assert "probe_25" in str(exc_info.value)


# ==============================================================================
# 2. FastAPI Endpoints & App Liveness Tests
# ==============================================================================

def test_root_endpoint():
    """Root GET / should return 200 with service information."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "ESP32 IoT Water Tank Monitor API"
    assert data["status"] == "running"
    assert "/docs" in data["docs_url"]


def test_openapi_schema_generation():
    """FastAPI OpenAPI schema must contain all expected paths."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema.get("paths", {})
    assert "/health" in paths
    assert "/api/readings" in paths
    assert "/api/readings/latest" in paths
    assert "/api/readings/history" in paths


def test_health_check_connected():
    """Health check when DB is connected should report status 'ok'."""
    mock_session = MagicMock()
    mock_session.execute.return_value = None

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"
    finally:
        app.dependency_overrides.clear()


def test_health_check_degraded_when_database_offline():
    """Health check should return status 'degraded' when database is unreachable."""
    mock_broken_session = MagicMock()
    mock_broken_session.execute.side_effect = OperationalError("connection failed", None, None)

    def override_get_db():
        yield mock_broken_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"] == "disconnected"
        assert "Database unreachable" in data["detail"]
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 3. HTTP Validation & Rejection Tests (No Database Required)
# ==============================================================================

def test_post_reading_validation_failure_exceeds_100():
    """API must reject water_level > 100 with 422 before touching the database."""
    invalid_payload = {
        "water_level": 150,
        "probe_25": True,
        "probe_50": True,
        "probe_75": True,
        "probe_100": True,
        "alarm": True,
        "muted": False,
    }
    response = client.post("/api/readings", json=invalid_payload)
    assert response.status_code == 422
    assert "water_level" in str(response.json())


def test_post_reading_validation_failure_negative():
    """API must reject negative water_level with 422 before touching the database."""
    invalid_payload = {
        "water_level": -10,
        "probe_25": False,
        "probe_50": False,
        "probe_75": False,
        "probe_100": False,
    }
    response = client.post("/api/readings", json=invalid_payload)
    assert response.status_code == 422
    assert "water_level" in str(response.json())


def test_post_reading_validation_failure_missing_body():
    """API must reject empty POST payload with 422."""
    response = client.post("/api/readings", json={})
    assert response.status_code == 422


# ==============================================================================
# 4. Database Connection Error Handling (503 Service Unavailable)
# ==============================================================================

def test_endpoints_return_503_when_database_offline():
    """
    When PostgreSQL is offline, endpoints must return 503 Service Unavailable
    with a clean error message, avoiding unhandled 500 crashes.
    """
    mock_broken_session = MagicMock()
    mock_broken_session.add.side_effect = OperationalError("connection lost", None, None)
    mock_broken_session.query.side_effect = OperationalError("connection lost", None, None)

    def override_get_db():
        yield mock_broken_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        valid_payload = {
            "water_level": 75,
            "probe_25": True,
            "probe_50": True,
            "probe_75": True,
            "probe_100": False,
            "alarm": False,
            "muted": False,
        }
        post_res = client.post("/api/readings", json=valid_payload)
        assert post_res.status_code == 503
        assert "Database connection error" in post_res.json()["detail"]

        latest_res = client.get("/api/readings/latest")
        assert latest_res.status_code == 503
        assert "Database connection error" in latest_res.json()["detail"]

        history_res = client.get("/api/readings/history")
        assert history_res.status_code == 503
        assert "Database connection error" in history_res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 5. Route Logic Tests with Mocked Session (Happy Path Verification)
# ==============================================================================

def test_mocked_db_post_reading_success():
    """Verify POST /api/readings serialization and response structure."""
    fake_reading = WaterReading(
        id=1,
        water_level=100,
        probe_25=True,
        probe_50=True,
        probe_75=True,
        probe_100=True,
        alarm=True,
        muted=False,
        created_at=datetime.now(timezone.utc)
    )

    mock_session = MagicMock()
    mock_session.add = MagicMock()
    mock_session.commit = MagicMock()

    def fake_refresh(instance):
        instance.id = fake_reading.id
        instance.created_at = fake_reading.created_at

    mock_session.refresh = MagicMock(side_effect=fake_refresh)

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        payload = {
            "water_level": 100,
            "probe_25": True,
            "probe_50": True,
            "probe_75": True,
            "probe_100": True,
            "alarm": True,
            "muted": False,
        }
        res = client.post("/api/readings", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["id"] == 1
        assert data["water_level"] == 100
        assert data["alarm"] is True
        assert "created_at" in data
    finally:
        app.dependency_overrides.clear()


def test_mocked_db_get_latest_reading_success():
    """Verify GET /api/readings/latest returns the most recent record."""
    fake_reading = WaterReading(
        id=42,
        water_level=50,
        probe_25=True,
        probe_50=True,
        probe_75=False,
        probe_100=False,
        alarm=False,
        muted=False,
        created_at=datetime.now(timezone.utc)
    )

    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.order_by.return_value.first.return_value = fake_reading

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        res = client.get("/api/readings/latest")
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == 42
        assert data["water_level"] == 50
        assert data["probe_50"] is True
        assert data["probe_75"] is False
    finally:
        app.dependency_overrides.clear()


def test_mocked_db_get_latest_reading_404_when_empty():
    """Verify GET /api/readings/latest returns 404 when table is empty."""
    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.order_by.return_value.first.return_value = None

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        res = client.get("/api/readings/latest")
        assert res.status_code == 404
        assert "No water level readings" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_mocked_db_get_history_success():
    """Verify GET /api/readings/history returns paginated readings array."""
    fake_readings = [
        WaterReading(
            id=i,
            water_level=i * 25,
            probe_25=True,
            probe_50=(i >= 2),
            probe_75=(i >= 3),
            probe_100=(i >= 4),
            alarm=(i == 0 or i == 4),
            muted=False,
            created_at=datetime.now(timezone.utc)
        )
        for i in range(1, 4)
    ]

    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = fake_readings

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        res = client.get("/api/readings/history?skip=0&limit=10")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 3
        assert data[0]["id"] == 1
        assert data[1]["id"] == 2
        assert data[2]["id"] == 3
    finally:
        app.dependency_overrides.clear()



# ==============================================================================
# 6. Indian Standard Time (IST, UTC+05:30) Serialization Tests
# ==============================================================================

def test_water_reading_response_serializes_ist_offset():
    """Verify WaterReadingResponse serializes UTC timestamps to IST (+05:30) with date rollover."""
    from app.schemas import WaterReadingResponse

    # Midnight rollover: 20:00 UTC on Nov 2 -> 01:30 IST on Nov 3
    utc_time = datetime(2026, 11, 2, 20, 0, 0, tzinfo=timezone.utc)
    reading_res = WaterReadingResponse(
        id=1,
        water_level=50,
        probe_25=True,
        probe_50=True,
        probe_75=False,
        probe_100=False,
        alarm=False,
        muted=False,
        created_at=utc_time
    )

    data = reading_res.model_dump()
    assert data["created_at"].isoformat() == "2026-11-03T01:30:00+05:30"

    json_str = reading_res.model_dump_json()
    assert "2026-11-03T01:30:00+05:30" in json_str


def test_api_latest_reading_returns_ist_timestamp():
    """Verify GET /api/readings/latest returns timestamp serialized in IST (+05:30)."""
    utc_time = datetime(2026, 11, 2, 10, 0, 0, tzinfo=timezone.utc)
    fake_reading = WaterReading(
        id=99,
        water_level=75,
        probe_25=True,
        probe_50=True,
        probe_75=True,
        probe_100=False,
        alarm=False,
        muted=False,
        created_at=utc_time
    )

    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.order_by.return_value.first.return_value = fake_reading

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        res = client.get("/api/readings/latest")
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == 99
        assert data["created_at"] == "2026-11-02T15:30:00+05:30"
        assert data["created_at"].endswith("+05:30")
    finally:
        app.dependency_overrides.clear()


def test_api_history_readings_return_ist_timestamps():
    """Verify GET /api/readings/history entries are serialized in IST (+05:30)."""
    fake_readings = [
        WaterReading(
            id=10,
            water_level=25,
            probe_25=True,
            probe_50=False,
            probe_75=False,
            probe_100=False,
            alarm=False,
            muted=False,
            created_at=datetime(2026, 11, 2, 23, 45, 0, tzinfo=timezone.utc)
        )
    ]

    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = fake_readings

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        res = client.get("/api/readings/history?limit=1")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        # UTC 23:45 + 5h30m = Next day 05:15 IST
        assert data[0]["created_at"] == "2026-11-03T05:15:00+05:30"
        assert data[0]["created_at"].endswith("+05:30")
    finally:
        app.dependency_overrides.clear()

def test_post_reading_returns_ist_timestamp():
    """Verify POST /api/readings returns timestamp serialized in IST (+05:30)."""
    utc_time = datetime(2026, 11, 2, 12, 0, 0, tzinfo=timezone.utc)
    fake_reading = WaterReading(
        id=7,
        water_level=25,
        probe_25=True,
        probe_50=False,
        probe_75=False,
        probe_100=False,
        alarm=False,
        muted=False,
        created_at=utc_time
    )

    mock_session = MagicMock()
    mock_session.add = MagicMock()
    mock_session.commit = MagicMock()

    def fake_refresh(instance):
        instance.id = fake_reading.id
        instance.created_at = fake_reading.created_at

    mock_session.refresh = MagicMock(side_effect=fake_refresh)

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        payload = {
            "water_level": 25,
            "probe_25": True,
            "probe_50": False,
            "probe_75": False,
            "probe_100": False,
            "alarm": False,
            "muted": False,
        }
        res = client.post("/api/readings", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["id"] == 7
        # 12:00 UTC + 5h30m = 17:30 IST
        assert data["created_at"] == "2026-11-02T17:30:00+05:30"
        assert data["created_at"].endswith("+05:30")
    finally:
        app.dependency_overrides.clear()



# ==============================================================================
# 7. Device Command & Remote Buzzer Control Tests
# ==============================================================================

def test_post_mute_command_success(monkeypatch):
    """Verify POST /api/commands/mute creates pending command with valid operator token."""
    from app.models import DeviceCommand
    monkeypatch.setenv("DASHBOARD_CONTROL_TOKEN", "valid_test_token_123")

    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.filter.return_value.all.return_value = []
    mock_query.filter.return_value.order_by.return_value.first.return_value = None

    def fake_refresh(cmd):
        cmd.id = 1
        cmd.created_at = datetime.now(timezone.utc)

    mock_session.add = MagicMock()
    mock_session.commit = MagicMock()
    mock_session.refresh = MagicMock(side_effect=fake_refresh)

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        res = client.post(
            "/api/commands/mute",
            json={"device_id": "esp32-tank-01"},
            headers={"X-Dashboard-Token": "valid_test_token_123"}
        )
        assert res.status_code == 201
        data = res.json()
        assert data["id"] == 1
        assert data["command_type"] == "MUTE_ALARM"
        assert data["command_status"] == "PENDING"
        assert "+05:30" in data["created_at"]
    finally:
        app.dependency_overrides.clear()


def test_dashboard_token_auth_enforcement(monkeypatch):
    """Verify X-Dashboard-Token header is required when DASHBOARD_CONTROL_TOKEN is set."""
    from app.models import DeviceCommand
    monkeypatch.setenv("DASHBOARD_CONTROL_TOKEN", "secure_secret_token_123")

    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.filter.return_value.all.return_value = []
    mock_query.filter.return_value.order_by.return_value.first.return_value = None

    def fake_refresh(cmd):
        cmd.id = 5
        cmd.created_at = datetime.now(timezone.utc)

    mock_session.refresh = MagicMock(side_effect=fake_refresh)

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        # 1. Missing header -> 401
        res = client.post("/api/commands/mute", json={"device_id": "esp32-tank-01"})
        assert res.status_code == 401
        assert "Unauthorized" in res.json()["detail"]

        # 2. Wrong header -> 401
        res_wrong = client.post(
            "/api/commands/mute",
            json={"device_id": "esp32-tank-01"},
            headers={"X-Dashboard-Token": "wrong_pin"}
        )
        assert res_wrong.status_code == 401

        # 3. Correct header -> 201
        res_ok = client.post(
            "/api/commands/mute",
            json={"device_id": "esp32-tank-01"},
            headers={"X-Dashboard-Token": "secure_secret_token_123"}
        )
        assert res_ok.status_code == 201
        assert res_ok.json()["command_type"] == "MUTE_ALARM"
    finally:
        app.dependency_overrides.clear()


def test_esp32_device_key_auth_enforcement(monkeypatch):
    """Verify X-Device-Key header is required when ESP32_API_KEY is set."""
    from app.models import DeviceCommand
    monkeypatch.setenv("ESP32_API_KEY", "hardware_secret_key_456")

    fake_cmd = DeviceCommand(
        id=8,
        device_id="esp32-tank-01",
        command_type="MUTE_ALARM",
        command_status="PENDING",
        created_at=datetime.now(timezone.utc)
    )

    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.filter.return_value.all.return_value = []
    mock_query.filter.return_value.order_by.return_value.first.return_value = fake_cmd

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        # 1. Without key -> 401
        res = client.get("/api/commands/pending?device_id=esp32-tank-01")
        assert res.status_code == 401

        # 2. With valid key -> 200
        res_ok = client.get(
            "/api/commands/pending?device_id=esp32-tank-01",
            headers={"X-Device-Key": "hardware_secret_key_456"}
        )
        assert res_ok.status_code == 200
        data = res_ok.json()
        assert data["command"]["id"] == 8
        assert data["command"]["command_type"] == "MUTE_ALARM"
    finally:
        app.dependency_overrides.clear()


def test_esp32_ack_command_success(monkeypatch):
    """Verify POST /api/commands/{id}/ack updates status to ACKNOWLEDGED with valid key."""
    from app.models import DeviceCommand
    monkeypatch.setenv("ESP32_API_KEY", "hardware_secret_key_456")

    fake_cmd = DeviceCommand(
        id=15,
        device_id="esp32-tank-01",
        command_type="MUTE_ALARM",
        command_status="PENDING",
        created_at=datetime.now(timezone.utc)
    )

    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = fake_cmd

    def fake_refresh(cmd):
        cmd.command_status = "ACKNOWLEDGED"
        cmd.acknowledged_at = datetime.now(timezone.utc)

    mock_session.commit = MagicMock()
    mock_session.refresh = MagicMock(side_effect=fake_refresh)

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        res = client.post(
            "/api/commands/15/ack",
            json={"device_id": "esp32-tank-01"},
            headers={"X-Device-Key": "hardware_secret_key_456"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == 15
        assert data["command_status"] == "ACKNOWLEDGED"
        assert "+05:30" in data["acknowledged_at"]
    finally:
        app.dependency_overrides.clear()


def test_get_command_status_and_history(monkeypatch):
    """Verify GET /api/commands/status/{id} and /api/commands/history enforce authentication."""
    from app.models import DeviceCommand
    monkeypatch.setenv("DASHBOARD_CONTROL_TOKEN", "valid_test_token_123")

    fake_cmd = DeviceCommand(
        id=20,
        device_id="esp32-tank-01",
        command_type="MUTE_ALARM",
        command_status="ACKNOWLEDGED",
        created_at=datetime.now(timezone.utc),
        acknowledged_at=datetime.now(timezone.utc)
    )

    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.filter.return_value.first.return_value = fake_cmd
    mock_query.order_by.return_value.limit.return_value.all.return_value = [fake_cmd]

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        # Unauthorized without header -> 401
        res_unauth = client.get("/api/commands/status/20")
        assert res_unauth.status_code == 401

        res_hist_unauth = client.get("/api/commands/history?limit=5")
        assert res_hist_unauth.status_code == 401

        # Authorized with valid header -> 200
        headers = {"X-Dashboard-Token": "valid_test_token_123"}
        res_status = client.get("/api/commands/status/20", headers=headers)
        assert res_status.status_code == 200
        assert res_status.json()["command_status"] == "ACKNOWLEDGED"

        res_hist = client.get("/api/commands/history?limit=5", headers=headers)
        assert res_hist.status_code == 200
        assert len(res_hist.json()) == 1
        assert res_hist.json()[0]["id"] == 20
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 8. Security Hardening & Edge Case Tests
# ==============================================================================

def test_server_missing_credentials_returns_503(monkeypatch):
    """Verify missing DASHBOARD_CONTROL_TOKEN or ESP32_API_KEY yields 503 Service Unavailable."""
    monkeypatch.delenv("DASHBOARD_CONTROL_TOKEN", raising=False)
    monkeypatch.delenv("ESP32_API_KEY", raising=False)
    monkeypatch.delenv("ALLOW_INSECURE_DEV_AUTH", raising=False)

    # 1. Mute command with unset server token -> 503
    res_mute = client.post("/api/commands/mute", json={"device_id": "esp32-tank-01"})
    assert res_mute.status_code == 503
    assert "DASHBOARD_CONTROL_TOKEN is not configured" in res_mute.json()["detail"]

    # 2. Polling with unset server key -> 503
    res_poll = client.get("/api/commands/pending?device_id=esp32-tank-01")
    assert res_poll.status_code == 503
    assert "ESP32_API_KEY is not configured" in res_poll.json()["detail"]

    # 3. Acknowledging with unset server key -> 503
    res_ack = client.post("/api/commands/1/ack", json={"device_id": "esp32-tank-01"})
    assert res_ack.status_code == 503
    assert "ESP32_API_KEY is not configured" in res_ack.json()["detail"]


def test_render_production_blocks_dev_bypass(monkeypatch):
    """Verify that on Render, ALLOW_INSECURE_DEV_AUTH=true is strictly ignored and blocked."""
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("ALLOW_INSECURE_DEV_AUTH", "true")
    monkeypatch.delenv("DASHBOARD_CONTROL_TOKEN", raising=False)
    monkeypatch.delenv("ESP32_API_KEY", raising=False)

    res = client.post("/api/commands/mute", json={"device_id": "esp32-tank-01"})
    assert res.status_code == 503
    assert "DASHBOARD_CONTROL_TOKEN is not configured" in res.json()["detail"]


def test_command_ownership_enforcement(monkeypatch):
    """Verify an ESP32 cannot acknowledge commands issued to another device ID (403 Forbidden)."""
    from app.models import DeviceCommand
    monkeypatch.setenv("ESP32_API_KEY", "hardware_secret_key_456")

    # Command was issued to 'esp32-tank-01'
    foreign_cmd = DeviceCommand(
        id=55,
        device_id="esp32-tank-01",
        command_type="MUTE_ALARM",
        command_status="PENDING",
        created_at=datetime.now(timezone.utc)
    )

    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.filter.return_value.first.return_value = foreign_cmd

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        # Rogue or different device 'esp32-tank-02' attempts to acknowledge it
        res = client.post(
            "/api/commands/55/ack",
            json={"device_id": "esp32-tank-02"},
            headers={"X-Device-Key": "hardware_secret_key_456"}
        )
        assert res.status_code == 403
        assert "Forbidden" in res.json()["detail"]
        assert "esp32-tank-01" in res.json()["detail"]
        assert "esp32-tank-02" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_stale_command_expiration(monkeypatch):
    """Verify stale commands exceeding TTL are transitioned to EXPIRED and not returned as pending."""
    from datetime import timedelta
    from app.models import DeviceCommand
    monkeypatch.setenv("ESP32_API_KEY", "hardware_secret_key_456")

    stale_cmd = DeviceCommand(
        id=60,
        device_id="esp32-tank-01",
        command_type="MUTE_ALARM",
        command_status="PENDING",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=10)
    )

    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_session.query.return_value = mock_query

    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = [stale_cmd]
    mock_query.order_by.return_value.first.return_value = None

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        res = client.get(
            "/api/commands/pending?device_id=esp32-tank-01",
            headers={"X-Device-Key": "hardware_secret_key_456"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["command"] is None
        assert stale_cmd.command_status == "EXPIRED"
        assert mock_session.commit.called
    finally:
        app.dependency_overrides.clear()


def test_expired_command_cannot_be_acknowledged(monkeypatch):
    """Verify attempting to acknowledge an already EXPIRED command returns 410 Gone."""
    from app.models import DeviceCommand
    monkeypatch.setenv("ESP32_API_KEY", "hardware_secret_key_456")

    expired_cmd = DeviceCommand(
        id=70,
        device_id="esp32-tank-01",
        command_type="MUTE_ALARM",
        command_status="EXPIRED",
        created_at=datetime.now(timezone.utc)
    )

    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.filter.return_value.first.return_value = expired_cmd

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        res = client.post(
            "/api/commands/70/ack",
            json={"device_id": "esp32-tank-01"},
            headers={"X-Device-Key": "hardware_secret_key_456"}
        )
        assert res.status_code == 410
        assert "expired" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_duplicate_mute_requests_deduplicated(monkeypatch):
    """Verify that duplicate mute requests reuse existing pending command without duplicate insertions."""
    from app.models import DeviceCommand
    monkeypatch.setenv("DASHBOARD_CONTROL_TOKEN", "valid_test_token_123")

    existing_pending = DeviceCommand(
        id=80,
        device_id="esp32-tank-01",
        command_type="MUTE_ALARM",
        command_status="PENDING",
        created_at=datetime.now(timezone.utc)
    )

    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.filter.return_value.all.return_value = []
    # Returns existing active command
    mock_query.filter.return_value.order_by.return_value.first.return_value = existing_pending

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        res = client.post(
            "/api/commands/mute",
            json={"device_id": "esp32-tank-01"},
            headers={"X-Dashboard-Token": "valid_test_token_123"}
        )
        assert res.status_code == 201
        data = res.json()
        assert data["id"] == 80
        # mock_session.add should NOT have been called because existing command was reused
        mock_session.add.assert_not_called()
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 9. Extended Production Validation & Regression Tests
# ==============================================================================

def test_crud_create_reading_returns_model_instance():
    """Verify crud.create_reading returns the created WaterReading model, not a count or scalar."""
    from app import crud
    from app.schemas import WaterReadingCreate
    from app.models import WaterReading

    payload = WaterReadingCreate(
        water_level=50,
        probe_25=True,
        probe_50=True,
        probe_75=False,
        probe_100=False,
        alarm=False,
        muted=False
    )

    mock_session = MagicMock()
    mock_session.add = MagicMock()
    mock_session.commit = MagicMock()

    def fake_refresh(instance):
        instance.id = 42

    mock_session.refresh = MagicMock(side_effect=fake_refresh)

    result = crud.create_reading(db=mock_session, reading_in=payload)
    assert isinstance(result, WaterReading)
    assert result.id == 42
    assert result.water_level == 50
    assert result.probe_50 is True
    assert mock_session.add.called
    assert mock_session.commit.called
    assert mock_session.refresh.called


def test_device_id_validation_rejects_empty_and_whitespace():
    """Verify empty, whitespace, or invalid device IDs are rejected by schemas."""
    from app.schemas import MuteCommandRequest, CommandAckRequest

    with pytest.raises(ValidationError):
        MuteCommandRequest(device_id="")

    with pytest.raises(ValidationError):
        MuteCommandRequest(device_id="   ")

    with pytest.raises(ValidationError):
        CommandAckRequest(device_id="")

    with pytest.raises(ValidationError):
        CommandAckRequest(device_id="invalid device!@#")


def test_invalid_ack_status_rejected():
    """Verify acknowledgement request rejects invalid status values."""
    from app.schemas import CommandAckRequest

    with pytest.raises(ValidationError):
        CommandAckRequest(device_id="esp32-tank-01", status="REJECTED")

    # Valid status
    valid = CommandAckRequest(device_id="esp32-tank-01", status="ACKNOWLEDGED")
    assert valid.status == "ACKNOWLEDGED"


def test_command_ttl_fallback_on_invalid_env(monkeypatch):
    """Verify get_command_ttl_seconds safely falls back to 120s on invalid env variables."""
    from app import crud

    # 1. Non-numeric
    monkeypatch.setenv("COMMAND_TTL_SECONDS", "invalid_string")
    assert crud.get_command_ttl_seconds() == 120

    # 2. Negative value
    monkeypatch.setenv("COMMAND_TTL_SECONDS", "-45")
    assert crud.get_command_ttl_seconds() == 120

    # 3. Valid value
    monkeypatch.setenv("COMMAND_TTL_SECONDS", "60")
    assert crud.get_command_ttl_seconds() == 60


def test_history_readings_limit_bounds():
    """Verify limit validation on /api/readings/history (1 <= limit <= 500)."""
    # limit = 0 -> 422
    res_zero = client.get("/api/readings/history?limit=0")
    assert res_zero.status_code == 422

    # limit = 501 -> 422
    res_over = client.get("/api/readings/history?limit=501")
    assert res_over.status_code == 422
