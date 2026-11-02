"""
API routes for bidirectional device command execution (Remote Buzzer Mute Control).
Provides authenticated endpoints for dashboard operators and ESP32 microcontrollers.
"""

import os
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..database import get_db
from .. import schemas, crud

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/commands",
    tags=["Commands"]
)


def _verify_dashboard_auth(x_dashboard_token: Optional[str] = Header(None, alias="X-Dashboard-Token")):
    """
    Enforces security token validation for dashboard control actions.
    If DASHBOARD_CONTROL_TOKEN is configured in server environment, requires matching header.
    """
    configured_token = os.getenv("DASHBOARD_CONTROL_TOKEN", "").strip()
    if configured_token:
        if not x_dashboard_token or x_dashboard_token.strip() != configured_token:
            logger.warning("Unauthorized dashboard command attempt. Missing or invalid X-Dashboard-Token.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: Invalid or missing Operator Control Token (X-Dashboard-Token)."
            )
    return True


def _verify_esp32_auth(x_device_key: Optional[str] = Header(None, alias="X-Device-Key")):
    """
    Enforces security key validation for ESP32 hardware endpoints.
    If ESP32_API_KEY is configured in server environment, requires matching header.
    """
    configured_key = os.getenv("ESP32_API_KEY", "").strip()
    if configured_key:
        if not x_device_key or x_device_key.strip() != configured_key:
            logger.warning("Unauthorized ESP32 command access attempt. Missing or invalid X-Device-Key.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: Invalid or missing ESP32 Device Key (X-Device-Key)."
            )
    return True


@router.post(
    "/mute",
    response_model=schemas.CommandResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request alarm mute",
    description="Issued by dashboard operator to silence physical buzzer on GPIO 23."
)
def request_alarm_mute(
    payload: Optional[schemas.MuteCommandRequest] = None,
    db: Session = Depends(get_db),
    _auth: bool = Depends(_verify_dashboard_auth)
):
    """
    Creates a new MUTE_ALARM command record in PostgreSQL with PENDING status.
    The ESP32 retrieves this command during its polling loop.
    """
    target_device = payload.device_id if payload and payload.device_id else "esp32-tank-01"
    try:
        cmd = crud.create_mute_command(db=db, device_id=target_device)
        logger.info("Created MUTE_ALARM command #%d for device '%s'", cmd.id, target_device)
        return cmd
    except SQLAlchemyError as exc:
        logger.error("Database error while creating mute command: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error: Could not schedule mute command."
        )


@router.get(
    "/pending",
    response_model=schemas.PendingCommandResponse,
    summary="Poll pending commands (ESP32)",
    description="Endpoint polled by ESP32 to receive pending hardware instructions."
)
def get_pending_commands_for_device(
    device_id: str = Query("esp32-tank-01", description="Device ID polling for commands"),
    db: Session = Depends(get_db),
    _auth: bool = Depends(_verify_esp32_auth)
):
    """
    Returns the oldest pending command for the device.
    Returns command: None if no pending instructions exist.
    """
    try:
        cmd = crud.get_pending_command(db=db, device_id=device_id)
        if cmd:
            return schemas.PendingCommandResponse(command=cmd, message="Pending command available")
        return schemas.PendingCommandResponse(command=None, message="No pending commands")
    except SQLAlchemyError as exc:
        logger.error("Database error while checking pending commands: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error: Could not check pending commands."
        )


@router.post(
    "/{command_id}/ack",
    response_model=schemas.CommandResponse,
    summary="Acknowledge command execution (ESP32)",
    description="Called by ESP32 microcontroller after successfully silencing physical buzzer on GPIO 23."
)
def acknowledge_command_execution(
    command_id: int,
    payload: Optional[schemas.CommandAckRequest] = None,
    db: Session = Depends(get_db),
    _auth: bool = Depends(_verify_esp32_auth)
):
    """
    Marks command status as ACKNOWLEDGED and sets acknowledged_at timestamp.
    """
    device_id = payload.device_id if payload and payload.device_id else None
    try:
        cmd = crud.acknowledge_command(db=db, command_id=command_id, device_id=device_id)
        if not cmd:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Command #{command_id} not found."
            )
        logger.info("Command #%d confirmed executed and acknowledged by device", command_id)
        return cmd
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.error("Database error while acknowledging command: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error: Could not acknowledge command."
        )


@router.get(
    "/status/{command_id}",
    response_model=schemas.CommandResponse,
    summary="Get command status",
    description="Polled by web dashboard to verify whether ESP32 has acknowledged buzzer mute."
)
def get_command_status(
    command_id: int,
    db: Session = Depends(get_db)
):
    """
    Returns current status of a command (PENDING or ACKNOWLEDGED).
    """
    try:
        cmd = crud.get_command_by_id(db=db, command_id=command_id)
        if not cmd:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Command #{command_id} not found."
            )
        return cmd
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.error("Database error while checking command status: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error: Could not check command status."
        )


@router.get(
    "/history",
    response_model=List[schemas.CommandResponse],
    summary="Get command history",
    description="Retrieves recent command history for audit logging and timeline presentation."
)
def get_command_history(
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    limit: int = Query(20, ge=1, le=100, description="Max command history records"),
    db: Session = Depends(get_db)
):
    """
    Returns recent command events ordered newest first.
    """
    try:
        return crud.get_command_history(db=db, device_id=device_id, limit=limit)
    except SQLAlchemyError as exc:
        logger.error("Database error while checking command history: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error: Could not check command history."
        )
