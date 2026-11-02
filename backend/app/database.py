"""
Database configuration and session management for the ESP32 Water Tank Monitoring System.
Uses SQLAlchemy with PostgreSQL and environment-based credentials from backend/.env.
"""

import os
import logging
from pathlib import Path
from typing import Generator
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

logger = logging.getLogger(__name__)

# Explicitly load backend/.env regardless of the current working directory
backend_dir = Path(__file__).resolve().parent.parent
env_file = backend_dir / ".env"

if env_file.is_file():
    load_dotenv(dotenv_path=env_file)
else:
    load_dotenv()

# Read database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

# Fallback template if not configured
if not DATABASE_URL:
    DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/watertank_db"
    logger.info("DATABASE_URL not set in backend/.env; using local development fallback.")

# Normalize Render/Heroku postgres:// scheme to postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Ensure SSL requirement for Render external databases if omitted
if "render.com" in DATABASE_URL and "sslmode" not in DATABASE_URL:
    separator = "&" if "?" in DATABASE_URL else "?"
    DATABASE_URL = f"{DATABASE_URL}{separator}sslmode=require"

# Check if user mistakenly pasted Render Internal Database URL for local development
if "dpg-" in DATABASE_URL and "render.com" not in DATABASE_URL and "localhost" not in DATABASE_URL:
    logger.warning(
        "Notice: The configured DATABASE_URL appears to be a Render Internal URL. "
        "For local development outside of Render, use the 'External Database URL' from the Render dashboard."
    )

# Ensure compatible driver selection between psycopg (v3) and psycopg2 (v2)
try:
    import psycopg  # psycopg v3 is available
except ImportError:
    try:
        import psycopg2  # fallback to psycopg2
        if DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+"):
            DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    except ImportError:
        logger.warning("Neither psycopg nor psycopg2 is installed. PostgreSQL connections will fail.")

# Initialize SQLAlchemy engine with pool_pre_ping and 10s connection timeout for cloud databases
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={"connect_timeout": 10}
)

# Safe logging: log database connection target with masked password
try:
    safe_db_url = engine.url.render_as_string(hide_password=True)
    logger.info("SQLAlchemy engine initialized for: %s", safe_db_url)
except Exception:
    logger.info("SQLAlchemy engine initialized.")

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class for ORM models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a SQLAlchemy database session per request
    and guarantees it is closed after request processing.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
