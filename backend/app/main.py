"""
Main application module for the ESP32 Water Tank Monitoring Backend.
Initializes FastAPI, registers CORS, handles health checks, and mounts routes.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from .database import engine, Base, get_db
from .routes import readings_router, commands_router
from .schemas import HealthResponse

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("water_tank_backend")


def init_db() -> bool:
    """
    Attempts to create database tables defined in models.py (water_readings and device_commands).
    Fails gracefully if PostgreSQL is unreachable during initial startup.
    Never prints connection strings or passwords to logs.
    """
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized successfully.")
        return True
    except Exception as exc:
        logger.warning(
            "Could not connect to PostgreSQL on startup (%s). "
            "Tables will be initialized once database connection is active.",
            type(exc).__name__
        )
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager for startup and shutdown events.
    """
    logger.info("Starting ESP32 Water Tank Monitoring Backend...")
    init_db()
    yield
    logger.info("Shutting down ESP32 Water Tank Monitoring Backend...")


# Initialize FastAPI application
app = FastAPI(
    title="ESP32 IoT Water Tank Monitor API",
    description=(
        "REST API backend for real-time water tank monitoring and remote buzzer control. "
        "Receives sensor telemetry from ESP32 microcontrollers, processes remote mute commands, "
        "and serves data to web dashboards."
    ),
    version="1.1.0",
    lifespan=lifespan
)

# Configure Cross-Origin Resource Sharing (CORS) for local and cloud dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(readings_router)
app.include_router(commands_router)


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Health check",
    description="Returns backend process status and tests PostgreSQL database connectivity."
)
def health_check(db: Session = Depends(get_db)):
    """
    Verifies API liveness and database connection status.
    """
    now = datetime.now(timezone.utc)
    try:
        # Perform a lightweight query to verify active database connectivity
        db.execute(text("SELECT 1"))
        return HealthResponse(
            status="ok",
            database="connected",
            timestamp=now
        )
    except SQLAlchemyError as exc:
        logger.warning("Database health probe failed: %s", type(exc).__name__)
        return HealthResponse(
            status="degraded",
            database="disconnected",
            timestamp=now,
            detail=f"Database unreachable: {type(exc).__name__}"
        )


@app.get(
    "/",
    tags=["Root"],
    summary="Root service info"
)
def root():
    """
    Root landing response with links to documentation and health check.
    """
    return {
        "service": "ESP32 IoT Water Tank Monitor API",
        "version": "1.1.0",
        "status": "running",
        "docs_url": "/docs",
        "health_url": "/health"
    }
