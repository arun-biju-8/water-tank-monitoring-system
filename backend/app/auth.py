"""
Authentication and security dependencies for TankPulse backend.
Enforces strict token and device key verification for dashboard operators and ESP32 hardware.
Guarantees production bypass immunity on Render.
"""

import os
import hmac
import logging
from typing import Optional
from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)


def is_production_environment() -> bool:
    """
    Returns True if running in Render production or explicit production environment.
    Guarantees production security controls cannot be accidentally disabled.
    """
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


def verify_dashboard_auth(x_dashboard_token: Optional[str] = Header(None, alias="X-Dashboard-Token")) -> bool:
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


def verify_esp32_auth(x_device_key: Optional[str] = Header(None, alias="X-Device-Key")) -> bool:
    """
    Enforces mandatory security key validation for ESP32 hardware endpoints (/api/readings, /pending, /{id}/ack).
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
            detail="Service unavailable: ESP32_API_KEY is not configured on the server."
        )

    if not x_device_key or not hmac.compare_digest(x_device_key.strip().encode("utf-8"), configured_key.encode("utf-8")):
        logger.warning("Unauthorized ESP32 telemetry/command access attempt. Missing or invalid X-Device-Key.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid or missing ESP32 Device Key (X-Device-Key)."
        )
    return True


# Backward-compatibility aliases for private naming convention
_verify_dashboard_auth = verify_dashboard_auth
_verify_esp32_auth = verify_esp32_auth
