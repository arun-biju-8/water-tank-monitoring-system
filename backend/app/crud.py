"""
CRUD (Create, Read, Update, Delete) operations for water reading records and device commands.
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from . import models, schemas

logger = logging.getLogger(__name__)

def get_command_ttl_seconds() -> int:
    """
    Returns the command TTL in seconds (default: 120s).
    Robust against invalid, non-numeric, or non-positive environment values.
    """
    raw = os.getenv("COMMAND_TTL_SECONDS", "120").strip()
    try:
        val = int(raw)
        return val if val > 0 else 120
    except (ValueError, TypeError):
        return 120


# Backward compatibility reference
COMMAND_TTL_SECONDS = get_command_ttl_seconds()


# ==============================================================================
# Sensor Reading Operations
# ==============================================================================

def create_reading(db: Session, reading_in: schemas.WaterReadingCreate) -> models.WaterReading:
    """
    Inserts a newly received sensor reading into the PostgreSQL database.
    """
    reading_data = (
        reading_in.model_dump()
        if hasattr(reading_in, "model_dump")
        else reading_in.dict()
    )
    db_reading = models.WaterReading(**reading_data)
    db.add(db_reading)
    db.commit()
    db.refresh(db_reading)
    return db_reading


def get_latest_reading(db: Session) -> Optional[models.WaterReading]:
    """
    Retrieves the most recent sensor reading by ID.
    Returns None if no records exist.
    """
    return (
        db.query(models.WaterReading)
        .order_by(models.WaterReading.id.desc())
        .first()
    )


def get_history_readings(
    db: Session,
    skip: int = 0,
    limit: int = 50
) -> List[models.WaterReading]:
    """
    Retrieves historical sensor readings ordered by descending ID with pagination.
    """
    return (
        db.query(models.WaterReading)
        .order_by(models.WaterReading.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_readings(db: Session) -> int:
    """
    Returns the total number of sensor readings stored in the database.
    """
    return db.query(models.WaterReading).count()


# ==============================================================================
# Device Command Operations (Bidirectional Remote Control)
# ==============================================================================

def expire_stale_commands(db: Session, device_id: Optional[str] = None) -> int:
    """
    Marks any PENDING commands older than COMMAND_TTL_SECONDS as EXPIRED.
    Prevents stale commands from unexpectedly silencing the buzzer after reconnection.
    Returns the count of expired commands.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=get_command_ttl_seconds())
    filters = [
        models.DeviceCommand.command_status == "PENDING",
        models.DeviceCommand.created_at < cutoff
    ]
    if device_id:
        filters.append(models.DeviceCommand.device_id == device_id)

    stale_commands = db.query(models.DeviceCommand).filter(*filters).all()
    if stale_commands:
        for cmd in stale_commands:
            cmd.command_status = "EXPIRED"
        db.commit()
        logger.info("Expired %d stale pending command(s) for device '%s'", len(stale_commands), device_id or "all")
        return len(stale_commands)
    return 0


def create_mute_command(db: Session, device_id: str = "esp32-tank-01") -> models.DeviceCommand:
    """
    Creates a new MUTE_ALARM command for the target device.
    First cleans up any stale commands exceeding TTL, then re-uses any active
    pending mute command in flight (deduplicating rapid operator clicks).
    """
    expire_stale_commands(db=db, device_id=device_id)

    existing = (
        db.query(models.DeviceCommand)
        .filter(
            models.DeviceCommand.device_id == device_id,
            models.DeviceCommand.command_status == "PENDING",
            models.DeviceCommand.command_type == "MUTE_ALARM"
        )
        .order_by(models.DeviceCommand.id.desc())
        .first()
    )
    if existing:
        logger.info("Deduplicating mute request: reusing active pending command #%d for device '%s'", existing.id, device_id)
        return existing

    cmd = models.DeviceCommand(
        device_id=device_id,
        command_type="MUTE_ALARM",
        command_status="PENDING"
    )
    db.add(cmd)
    db.commit()
    db.refresh(cmd)
    return cmd


def get_pending_command(db: Session, device_id: str = "esp32-tank-01") -> Optional[models.DeviceCommand]:
    """
    Retrieves the oldest valid (unexpired) pending command waiting for the ESP32.
    First marks any stale commands exceeding TTL as EXPIRED.
    """
    expire_stale_commands(db=db, device_id=device_id)

    return (
        db.query(models.DeviceCommand)
        .filter(
            models.DeviceCommand.device_id == device_id,
            models.DeviceCommand.command_status == "PENDING"
        )
        .order_by(models.DeviceCommand.id.asc())
        .first()
    )


def acknowledge_command(
    db: Session,
    command_id: int,
    device_id: str
) -> Optional[models.DeviceCommand]:
    """
    Marks a command as ACKNOWLEDGED once executed by the intended ESP32 hardware.
    Enforces matching device_id ownership.
    Ensures that expired commands cannot become acknowledged.
    """
    cmd = (
        db.query(models.DeviceCommand)
        .filter(
            models.DeviceCommand.id == command_id,
            models.DeviceCommand.device_id == device_id
        )
        .first()
    )
    if not cmd:
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=get_command_ttl_seconds())
    cmd_created = cmd.created_at.replace(tzinfo=timezone.utc) if cmd.created_at and cmd.created_at.tzinfo is None else cmd.created_at

    # Reject if already expired or past TTL
    if cmd.command_status == "EXPIRED" or (cmd_created and cmd_created < cutoff):
        if cmd.command_status != "EXPIRED":
            cmd.command_status = "EXPIRED"
            db.commit()
            db.refresh(cmd)
        return cmd

    if cmd.command_status == "PENDING":
        cmd.command_status = "ACKNOWLEDGED"
        cmd.acknowledged_at = func.now()
        db.commit()
        db.refresh(cmd)

    return cmd


def get_command_by_id(db: Session, command_id: int) -> Optional[models.DeviceCommand]:
    """
    Retrieves a single command by ID.
    """
    return db.query(models.DeviceCommand).filter(models.DeviceCommand.id == command_id).first()


def get_command_history(
    db: Session,
    device_id: Optional[str] = None,
    limit: int = 20
) -> List[models.DeviceCommand]:
    """
    Retrieves recent command history for audit and timeline logs.
    """
    query = db.query(models.DeviceCommand)
    if device_id:
        query = query.filter(models.DeviceCommand.device_id == device_id)
    return query.order_by(models.DeviceCommand.id.desc()).limit(limit).all()
