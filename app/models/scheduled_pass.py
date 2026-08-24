# app/models/scheduled_pass.py
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.database_config import Base

# Avoid circular imports
if TYPE_CHECKING:
    from .satellite import Satellite
    from .telecommand import Telecommand


class ScheduledPass(Base):
    """A satellite pass the station has committed to tracking.

    Produced by the TC Scheduler, which predicts every visible pass in the
    planning horizon and picks the ones worth using. Persisted rather than kept
    in the scheduler's memory so that the plan survives a restart and the
    dashboard can show when each telecommand goes out.
    """

    __tablename__ = 'scheduled_passes'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    satellite_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('satellites.id', ondelete='CASCADE'),
        nullable=False
    )

    aos_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    los_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    culmination_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    max_elevation_deg: Mapped[float] = mapped_column(Float, nullable=False)
    aos_azimuth_deg: Mapped[float] = mapped_column(Float, nullable=False)
    los_azimuth_deg: Mapped[float] = mapped_column(Float, nullable=False)

    # Epoch of the orbital elements used: the older it is, the less trustworthy
    # the prediction. Kept so a failed pass can be audited afterwards.
    tle_epoch: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    data_source: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20),
        default='planned',
        nullable=False,
        server_default='planned'
    )
    status_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), server_default=func.now()
    )

    # Relationships
    satellite: Mapped["Satellite"] = relationship(
        "Satellite", back_populates="scheduled_passes"
    )
    telecommands: Mapped[List["Telecommand"]] = relationship(
        "Telecommand", back_populates="scheduled_pass"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('planned', 'active', 'completed', 'missed', 'cancelled')",
            name='valid_pass_status'
        ),
        CheckConstraint(
            "data_source IN ('omm', 'tle')",
            name='valid_pass_data_source'
        ),
        CheckConstraint("los_time > aos_time", name='valid_pass_window'),
    )

    @property
    def duration_seconds(self) -> float:
        return (self.los_time - self.aos_time).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        def iso(value: Optional[datetime]) -> Optional[str]:
            return value.isoformat() if value else None

        return {
            'id': self.id,
            'satellite_id': self.satellite_id,
            'aos_time': iso(self.aos_time),
            'los_time': iso(self.los_time),
            'culmination_time': iso(self.culmination_time),
            'duration_seconds': self.duration_seconds,
            'max_elevation_deg': self.max_elevation_deg,
            'aos_azimuth_deg': self.aos_azimuth_deg,
            'los_azimuth_deg': self.los_azimuth_deg,
            'tle_epoch': iso(self.tle_epoch),
            'data_source': self.data_source,
            'status': self.status,
            'status_message': self.status_message,
            'created_at': iso(self.created_at),
            'updated_at': iso(self.updated_at)
        }

    def __repr__(self) -> str:
        return f'<ScheduledPass {self.id}: sat={self.satellite_id} AOS={self.aos_time} ({self.status})>'
