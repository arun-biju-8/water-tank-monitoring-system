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
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Server UTC timestamp")
    detail: Optional[str] = Field(default=None, description="Optional diagnostic details")
