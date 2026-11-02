"""
SQLAlchemy ORM models for the Water Tank Monitoring System.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from .database import Base


class WaterReading(Base):
    """
    Model representing a single sensor snapshot from the ESP32 water tank monitor.
    """
    __tablename__ = "water_readings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    water_level = Column(Integer, nullable=False, index=True)
    probe_25 = Column(Boolean, nullable=False)
    probe_50 = Column(Boolean, nullable=False)
    probe_75 = Column(Boolean, nullable=False)
    probe_100 = Column(Boolean, nullable=False)
    alarm = Column(Boolean, nullable=False, default=False)
    muted = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )

    def __repr__(self) -> str:
        return (
            f"<WaterReading(id={self.id}, level={self.water_level}%, "
            f"probes=[{int(self.probe_25)},{int(self.probe_50)},"
            f"{int(self.probe_75)},{int(self.probe_100)}], "
            f"alarm={self.alarm}, muted={self.muted})>"
        )


class DeviceCommand(Base):
    """
    Model representing bidirectional commands issued from cloud dashboard to ESP32 (e.g. MUTE_ALARM).
    Tracks command delivery and physical hardware execution acknowledgment.
    """
    __tablename__ = "device_commands"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    device_id = Column(String(64), nullable=False, default="esp32-tank-01", index=True)
    command_type = Column(String(32), nullable=False)  # "MUTE_ALARM", "UNMUTE_ALARM"
    command_status = Column(String(32), nullable=False, default="PENDING", index=True)  # "PENDING", "ACKNOWLEDGED", "EXPIRED"
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<DeviceCommand(id={self.id}, device='{self.device_id}', "
            f"type='{self.command_type}', status='{self.command_status}')>"
        )
