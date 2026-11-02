"""
CRUD (Create, Read, Update, Delete) operations for water reading records and device commands.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from . import models, schemas


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

def create_mute_command(db: Session, device_id: str = "esp32-tank-01") -> models.DeviceCommand:
    """
    Creates a new MUTE_ALARM command for the target device.
    Re-uses existing pending mute command if one is already in flight.
    """
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
    Retrieves the oldest pending command waiting to be consumed by the ESP32.
    """
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
    device_id: Optional[str] = None
) -> Optional[models.DeviceCommand]:
    """
    Marks a command as ACKNOWLEDGED once executed by the ESP32 hardware.
    """
    filters = [models.DeviceCommand.id == command_id]
    if device_id:
        filters.append(models.DeviceCommand.device_id == device_id)
    cmd = db.query(models.DeviceCommand).filter(*filters).first()
    if not cmd:
        return None

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
