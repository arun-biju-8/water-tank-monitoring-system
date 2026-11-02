"""
API routes for sensor readings received from ESP32 and queried by the dashboard.
"""

import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..database import get_db
from .. import schemas, crud

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/readings",
    tags=["Readings"]
)


@router.post(
    "",
    response_model=schemas.WaterReadingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest new sensor reading",
    description="Endpoint for the ESP32 to publish water level and probe readings via HTTP POST."
)
def create_sensor_reading(
    reading: schemas.WaterReadingCreate,
    db: Session = Depends(get_db)
):
    """
    Receives JSON payload from ESP32, validates the structure and values,
    and persists the record to the PostgreSQL database.
    """
    try:
        new_reading = crud.create_reading(db=db, reading_in=reading)
        return new_reading
    except SQLAlchemyError as exc:
        logger.error("Database error while saving sensor reading: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection error. Could not persist sensor reading."
        )


@router.get(
    "/latest",
    response_model=schemas.WaterReadingResponse,
    summary="Get latest sensor reading",
    description="Retrieves the most recent reading for live dashboard cards and visual gauges."
)
def get_latest_sensor_reading(db: Session = Depends(get_db)):
    """
    Returns the newest sensor reading snapshot.
    Returns HTTP 404 if no readings have been recorded yet.
    """
    try:
        latest = crud.get_latest_reading(db=db)
        if not latest:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No water level readings have been recorded yet."
            )
        return latest
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.error("Database error while retrieving latest reading: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection error. Could not retrieve latest reading."
        )


@router.get(
    "/history",
    response_model=List[schemas.WaterReadingResponse],
    summary="Get historical sensor readings",
    description="Retrieves paginated historical readings for charts and tabular logs."
)
def get_sensor_history(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=500, description="Maximum records to retrieve (1-500)"),
    db: Session = Depends(get_db)
):
    """
    Returns a list of historical readings ordered by newest first.
    """
    try:
        history = crud.get_history_readings(db=db, skip=skip, limit=limit)
        return history
    except SQLAlchemyError as exc:
        logger.error("Database error while retrieving readings history: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection error. Could not retrieve reading history."
        )
