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
