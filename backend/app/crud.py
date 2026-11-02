"""
CRUD (Create, Read, Update, Delete) operations for water reading records.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from . import models, schemas


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
