# app/models/satellite.py
from datetime import datetime, timezone, UTC
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from sqlalchemy import CheckConstraint
from sqlalchemy import DateTime
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import event
from sqlalchemy import func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from ..database.database_config import Base

# Avoid circular imports
if TYPE_CHECKING:
    from .telecommand import Telecommand
    from .scheduled_pass import ScheduledPass
    from .satellite_tracking_status import SatelliteTrackingStatus


class Satellite(Base):
    __tablename__ = 'satellites'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(),
                                                 server_default=func.now())
    status: Mapped[str] = mapped_column(
        String(20),
        default='active',
        nullable=False,
        server_default='active'
    )

    # Orbital data. Optional: a satellite without either still accepts
    # telecommands, but is skipped by the automatic scheduler — there is no way
    # to predict passes for an orbit we don't know.
    # norad_id is preferred (the TLE is fetched from CelesTrak and stays fresh);
    # the TLE lines cover satellites outside the public catalogue, or pin a
    # specific TLE for testing, and take precedence when set.
    norad_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True, nullable=True)
    tle_line1: Mapped[Optional[str]] = mapped_column(String(69), nullable=True)
    tle_line2: Mapped[Optional[str]] = mapped_column(String(69), nullable=True)

    # Relationships
    telecommands: Mapped[List["Telecommand"]] = relationship(
        "Telecommand",
        back_populates="satellite",
        cascade="all, delete-orphan",
        passive_deletes=True
    )
    scheduled_passes: Mapped[List["ScheduledPass"]] = relationship(
        "ScheduledPass",
        back_populates="satellite",
        cascade="all, delete-orphan",
        passive_deletes=True
    )
    tracking_status: Mapped[Optional["SatelliteTrackingStatus"]] = relationship(
        "SatelliteTrackingStatus",
        back_populates="satellite",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'inactive', 'maintenance')",
            name='valid_satellite_status'
        ),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'description': self.description,
            'status': self.status,
            'norad_id': self.norad_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    @property
    def is_trackable(self) -> bool:
        """Whether the scheduler can predict passes for this satellite."""
        return self.norad_id is not None or bool(self.tle_line1 and self.tle_line2)

    def __repr__(self):
        return f'<Satellite {self.code}: {self.name}>'


# Update the timestamp when the satellite is updated.
@event.listens_for(Satellite, 'before_update')
def update_updated_at(mapper, connection, target):
    # Use timezone-aware UTC datetime
    target.updated_at = datetime.now(UTC)
