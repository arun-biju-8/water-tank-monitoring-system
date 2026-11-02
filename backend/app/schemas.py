"""
Pydantic schemas for data validation and API response serialization.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator

# Standard IANA timezone identifier for Indian Standard Time
IST_TIMEZONE = ZoneInfo("Asia/Kolkata")


def to_ist(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Converts a datetime to Indian Standard Time (Asia/Kolkata, UTC+05:30).
    If the input datetime is naive (lacks tzinfo), it is treated as UTC.
    Returns a timezone-aware datetime with the +05:30 offset.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST_TIMEZONE)


class WaterReadingBase(BaseModel):
    """
    Base attributes shared across request and response models.
    """
    water_level: int = Field(
        ...,
        ge=0,
        le=100,
        description="Water level percentage (integer between 0 and 100)",
        examples=[75]
    )
    probe_25: bool = Field(
        ...,
        description="25% probe state: true if submerged in water, false otherwise",
        examples=[True]
    )
    probe_50: bool = Field(
        ...,
        description="50% probe state: true if submerged in water, false otherwise",
        examples=[True]
    )
    probe_75: bool = Field(
        ...,
        description="75% probe state: true if submerged in water, false otherwise",
        examples=[True]
    )
    probe_100: bool = Field(
        ...,
        description="100% probe state: true if submerged in water, false otherwise",
        examples=[False]
    )
    alarm: bool = Field(
        default=False,
        description="Alarm active flag (true on empty 0% or full 100%)",
        examples=[False]
    )
    muted: bool = Field(
        default=False,
        description="Alarm muted state (true if silenced by user)",
        examples=[False]
    )


class WaterReadingCreate(WaterReadingBase):
    """
    Schema for validating incoming sensor readings sent via HTTP POST from ESP32.
    """
    pass


class WaterReadingResponse(WaterReadingBase):
    """
    Schema for serializing sensor reading records returned by the API.
    Converts created_at timestamp to Indian Standard Time (IST, UTC+05:30).
    """
    id: int = Field(..., description="Unique reading identifier", examples=[1])
    created_at: datetime = Field(..., description="Timestamp when the reading was recorded (IST, UTC+05:30)")

    model_config = ConfigDict(from_attributes=True)

    @field_validator("created_at", mode="after")
    @classmethod
    def convert_created_at_to_ist(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Converts UTC database timestamp to Indian Standard Time (+05:30) on output."""
        return to_ist(v)


class HealthResponse(BaseModel):
    """
    Schema for backend health check endpoint.
    """
    status: str = Field(..., description="System overall health status", examples=["ok", "degraded"])
    database: str = Field(..., description="Database connection status", examples=["connected", "disconnected"])
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Server UTC timestamp")
    detail: Optional[str] = Field(default=None, description="Optional diagnostic details")


# ==============================================================================
# Device Command Schemas for Bidirectional Buzzer Control
# ==============================================================================

class MuteCommandRequest(BaseModel):
    """Request payload sent from dashboard to silence physical alarm."""
    device_id: str = Field(
        default="esp32-tank-01",
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_\-]+$",
        description="Target hardware device ID"
    )

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("device_id cannot be empty or whitespace")
        return s


class CommandAckRequest(BaseModel):
    """Acknowledgment payload sent by ESP32 once physical buzzer is silenced."""
    device_id: str = Field(
        default="esp32-tank-01",
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_\-]+$",
        description="Device ID confirming execution"
    )
    status: str = Field(
        default="ACKNOWLEDGED",
        description="Confirmation status (must be ACKNOWLEDGED)"
    )

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("device_id cannot be empty or whitespace")
        return s

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        s = v.strip()
        if s != "ACKNOWLEDGED":
            raise ValueError("status must be ACKNOWLEDGED")
        return s


class CommandResponse(BaseModel):
    """Serialized command object returned to dashboard and ESP32."""
    id: int = Field(..., description="Unique command ID")
    device_id: str = Field(..., min_length=1, max_length=64, description="Target device identifier")
    command_type: str = Field(..., pattern=r"^(MUTE_ALARM|UNMUTE_ALARM)$", description="Command type (e.g. MUTE_ALARM)")
    command_status: str = Field(..., pattern=r"^(PENDING|ACKNOWLEDGED|EXPIRED)$", description="Status: PENDING, ACKNOWLEDGED, EXPIRED")
    created_at: datetime = Field(..., description="Timestamp created (IST, UTC+05:30)")
    acknowledged_at: Optional[datetime] = Field(default=None, description="Timestamp acknowledged by ESP32 (IST, UTC+05:30)")

    model_config = ConfigDict(from_attributes=True)

    @field_validator("created_at", "acknowledged_at", mode="after")
    @classmethod
    def convert_command_timestamps_to_ist(cls, v: Optional[datetime]) -> Optional[datetime]:
        return to_ist(v)


class PendingCommandResponse(BaseModel):
    """Polling response format for ESP32 microcontroller."""
    command: Optional[CommandResponse] = Field(default=None, description="Pending command object, if any")
    message: Optional[str] = Field(default=None, description="Status description")
