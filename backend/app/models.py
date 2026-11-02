"""
SQLAlchemy ORM models for the Water Tank Monitoring System.
"""

from sqlalchemy import Column, Integer, Boolean, DateTime
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
