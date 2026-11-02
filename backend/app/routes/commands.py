"""
API routes for bidirectional device command execution (Remote Buzzer Mute Control).
Provides authenticated endpoints for dashboard operators and ESP32 microcontrollers.
"""

import os
import hmac
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


def is_production_environment() -> bool:
    """
    Returns True if running in Render production or explicit production environment.
    Guarantees production security controls cannot be accidentally disabled.
    """
    # Render environment markers
    if os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID") or os.getenv("RENDER_INSTANCE_ID"):
        return True
    env = os.getenv("ENVIRONMENT", os.getenv("ENV", "production")).strip().lower()
    return env in ("production", "prod")


def is_insecure_dev_allowed() -> bool:
    """
    Returns True ONLY if insecure dev auth is explicitly enabled AND NOT running on Render / production.
    Render production strictly blocks this bypass regardless of flag values.
    """
    if is_production_environment():
        return False
    return os.getenv("ALLOW_INSECURE_DEV_AUTH", "").strip().lower() in ("true", "1", "yes")


def _verify_dashboard_auth(x_dashboard_token: Optional[str] = Header(None, alias="X-Dashboard-Token")):
    """
    Enforces mandatory security token validation for dashboard control actions.
    - If DASHBOARD_CONTROL_TOKEN is missing on server: returns HTTP 503 (server misconfigured).
    - If X-Dashboard-Token is missing or does not match: returns HTTP 401.
    - Development bypass is strictly prohibited in Render production.
    """
    configured_token = os.getenv("DASHBOARD_CONTROL_TOKEN", "").strip()
    if not configured_token:
        if is_insecure_dev_allowed():
            logger.warning("DEVELOPMENT MODE: Insecure dashboard auth bypass active (ALLOW_INSECURE_DEV_AUTH=true).")
            return True
        logger.error("Authentication rejected: DASHBOARD_CONTROL_TOKEN is not configured on the server.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Remote command service unavailable: DASHBOARD_CONTROL_TOKEN is not configured on the server."
        )

    if not x_dashboard_token or not hmac.compare_digest(x_dashboard_token.strip().encode("utf-8"), configured_token.encode("utf-8")):
        logger.warning("Unauthorized dashboard command attempt. Missing or invalid X-Dashboard-Token.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid or missing Operator Control Token (X-Dashboard-Token)."
        )
    return True


def _verify_esp32_auth(x_device_key: Optional[str] = Header(None, alias="X-Device-Key")):
    """
    Enforces mandatory security key validation for ESP32 hardware endpoints (/pending, /{id}/ack).
    - If ESP32_API_KEY is missing on server: returns HTTP 503 (server misconfigured).
    - If X-Device-Key is missing or does not match: returns HTTP 401.
    - Development bypass is strictly prohibited in Render production.
    """
    configured_key = os.getenv("ESP32_API_KEY", "").strip()
    if not configured_key:
        if is_insecure_dev_allowed():
            logger.warning("DEVELOPMENT MODE: Insecure ESP32 auth bypass active (ALLOW_INSECURE_DEV_AUTH=true).")
            return True
        logger.error("Authentication rejected: ESP32_API_KEY is not configured on the server.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Device command channel unavailable: ESP32_API_KEY is not configured on the server."
        )

    if not x_device_key or not hmac.compare_digest(x_device_key.strip().encode("utf-8"), configured_key.encode("utf-8")):
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
    description="Issued by authorized dashboard operator to silence physical buzzer on GPIO 23."
)
def request_alarm_mute(
    payload: Optional[schemas.MuteCommandRequest] = None,
    db: Session = Depends(get_db),
    _auth: bool = Depends(_verify_dashboard_auth)
):
    """
    Creates a new MUTE_ALARM command record in PostgreSQL with PENDING status.
    Deduplicates requests if an active pending command is already in flight.
    """
    target_device = (payload.device_id if payload and payload.device_id else "esp32-tank-01").strip()
    try:
        cmd = crud.create_mute_command(db=db, device_id=target_device)
        logger.info("MUTE_ALARM command #%d prepared for device '%s' (status: %s)", cmd.id, target_device, cmd.command_status)
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
    Returns the oldest valid (unexpired) pending command for the device.
    Automatically expires stale commands exceeding TTL to prevent unexpected buzzer silencing.
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
    Marks command status as ACKNOWLEDGED and records timestamp.
    Enforces strict command ownership and rejects expired commands.
    """
    requesting_device = (payload.device_id if payload and payload.device_id else "esp32-tank-01").strip()
    try:
        # 1. Fetch command and verify existence
        cmd = crud.get_command_by_id(db=db, command_id=command_id)
        if not cmd:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Command #{command_id} not found."
            )

        # 2. Enforce strict device ownership
        if cmd.device_id != requesting_device:
            logger.warning(
                "Command ownership mismatch: device '%s' attempted to acknowledge command #%d belonging to '%s'",
                requesting_device, command_id, cmd.device_id
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Command #{command_id} was issued to device '{cmd.device_id}', not '{requesting_device}'."
            )

        # 3. Reject acknowledgment of expired commands
        if cmd.command_status == "EXPIRED":
            logger.warning("Attempted to acknowledge expired command #%d by device '%s'", command_id, requesting_device)
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail=f"Command #{command_id} has expired and cannot be acknowledged."
            )

        # 4. Mark acknowledged
        updated_cmd = crud.acknowledge_command(db=db, command_id=command_id, device_id=requesting_device)
        logger.info("Command #%d confirmed executed and acknowledged by device '%s'", command_id, requesting_device)
        return updated_cmd
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
    Returns current status of a command (PENDING, ACKNOWLEDGED, or EXPIRED).
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
