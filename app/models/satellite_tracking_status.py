# app/models/satellite_tracking_status.py
from datetime import datetime
from typing import Any, Dict, Optional, TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.database_config import Base

# Avoid circular imports
if TYPE_CHECKING:
    from .satellite import Satellite


class SatelliteTrackingStatus(Base):
    """Where a satellite is right now, as seen from the ground station.

    One row per satellite, overwritten by the TC Scheduler on every tracking
    cycle — this is current state, not history. It exists so the dashboard can
    answer "where is everything" without having to propagate orbits itself.
    """

    __tablename__ = 'satellite_tracking_status'

    satellite_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('satellites.id', ondelete='CASCADE'),
        primary_key=True
    )

    # Sub-satellite point
    latitude_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    altitude_km: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # As seen from the station
    azimuth_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    elevation_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    range_km: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default='false'
    )

    tle_epoch: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    data_source: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Why the last attempt failed, when it did (missing TLE, propagation error,
    # CelesTrak unreachable with no cache). Keeps an isolated failure visible
    # instead of turning it into silence.
    status_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    satellite: Mapped["Satellite"] = relationship(
        "Satellite", back_populates="tracking_status"
    )

    __table_args__ = (
        CheckConstraint("data_source IN ('omm', 'tle')", name='valid_tracking_data_source'),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'satellite_id': self.satellite_id,
            'latitude_deg': self.latitude_deg,
            'longitude_deg': self.longitude_deg,
            'altitude_km': self.altitude_km,
            'azimuth_deg': self.azimuth_deg,
            'elevation_deg': self.elevation_deg,
            'range_km': self.range_km,
            'is_visible': self.is_visible,
            'tle_epoch': self.tle_epoch.isoformat() if self.tle_epoch else None,
            'data_source': self.data_source,
            'status_message': self.status_message,
            'checked_at': self.checked_at.isoformat() if self.checked_at else None
        }

    def __repr__(self) -> str:
        return (
            f'<SatelliteTrackingStatus sat={self.satellite_id} '
            f'el={self.elevation_deg} visible={self.is_visible}>'
        )
