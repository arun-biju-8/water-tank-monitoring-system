"""
Pydantic schemas for data validation and API response serialization.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


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
    """
    id: int = Field(..., description="Unique reading identifier", examples=[1])
    created_at: datetime = Field(..., description="Timestamp when the reading was recorded")

    model_config = ConfigDict(from_attributes=True)


class HealthResponse(BaseModel):
    """
    Schema for backend health check endpoint.
    """
    status: str = Field(..., description="System overall health status", examples=["ok", "degraded"])
    database: str = Field(..., description="Database connection status", examples=["connected", "disconnected"])
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Server UTC timestamp")
    detail: Optional[str] = Field(default=None, description="Optional diagnostic details")
