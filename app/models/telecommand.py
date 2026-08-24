# app/models/telecommand.py
from datetime import datetime, timezone, UTC
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.database_config import Base

# Avoid circular imports
if TYPE_CHECKING:
    from .satellite import Satellite
    from .operator import Operator
    from .execution_log import ExecutionLog
    from .scheduled_pass import ScheduledPass

class Telecommand(Base):
    """Represents a telecommand that can be sent to a satellite."""
    __tablename__ = 'telecommands'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    satellite_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('satellites.id', ondelete='CASCADE'),
        nullable=False
    )
    operator_id: Mapped[int] = mapped_column(
        Integer,
        # If operator is deleted, reassign to Admin (ID 1)
        ForeignKey('operators.id', ondelete='SET DEFAULT'),
        nullable=False,
        # Default value '1' (Admin) is required for ON DELETE SET DEFAULT
        server_default='1'
    )
    command_type: Mapped[str] = mapped_column(String(50), nullable=False)
    parameters: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default='pending',
        nullable=False,
        server_default='pending'
    )
    status_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(timezone.utc),
        nullable=False
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    priority: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
        server_default='5'
    )
    metadata_: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        'metadata',  # Actual column name in the database
        JSONB,
        nullable=True
    )
    # Pass this command is scheduled to be transmitted on. SET NULL on delete
    # because cancelling a pass must not delete the telecommand: it goes back
    # to the queue and is rescheduled on the next planning cycle.
    scheduled_pass_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey('scheduled_passes.id', ondelete='SET NULL'),
        nullable=True
    )

    # Relationships
    satellite: Mapped["Satellite"] = relationship("Satellite", back_populates="telecommands")
    scheduled_pass: Mapped[Optional["ScheduledPass"]] = relationship(
        "ScheduledPass", back_populates="telecommands"
    )
    operator: Mapped[Optional["Operator"]] = relationship("Operator", back_populates="telecommands")

    # Use string literal for ExecutionLog to avoid circular import
    execution_logs: Mapped[List["ExecutionLog"]] = relationship(
        "ExecutionLog",
        back_populates="telecommand",
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'queued', 'sent', 'confirmed', 'failed')",
            name='valid_status'
        ),
        CheckConstraint(
            "priority BETWEEN 1 AND 10",
            name='valid_priority'
        ),
    )

    def update_status(self, new_status: str, message: Optional[str] = None) -> 'Telecommand':
        """Update the status of the telecommand and set relevant timestamps.

        Args:
            new_status: The new status (pending, queued, sent, confirmed, failed)
            message: Optional status message

        Returns:
            Self for method chaining
        """
        self.status = new_status.lower()
        self.status_message = message

        now = datetime.now(timezone.utc)
        if new_status.lower() == 'sent':
            self.sent_at = now
        elif new_status.lower() == 'confirmed':
            self.confirmed_at = now

        return self

    def to_dict(self) -> Dict[str, Any]:
        """Convert the telecommand to a dictionary."""
        def format_datetime(dt: Optional[datetime]) -> Optional[str]:
            return dt.astimezone(UTC).isoformat() if dt else None

        return {
            'id': self.id,
            'satellite_id': self.satellite_id,
            'operator_id': self.operator_id,
            'command_type': self.command_type,
            'parameters': self.parameters,
            'status': self.status,
            'status_message': self.status_message,
            'created_at': format_datetime(self.created_at),
            'sent_at': format_datetime(self.sent_at),
            'confirmed_at': format_datetime(self.confirmed_at),
            'priority': self.priority,
            'metadata': self.metadata_,
            'scheduled_pass_id': self.scheduled_pass_id
        }

    def __repr__(self) -> str:
        return f'<Telecommand {self.id}: {self.command_type} ({self.status})>'