from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from relaykit.database.base import Base


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "endpoint_id",
            name="uq_deliveries_event_id_endpoint_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "events.id",
            name="fk_deliveries_event_id_events",
        ),
        nullable=False,
    )
    endpoint_id: Mapped[str] = mapped_column(
        String(35),
        ForeignKey(
            "endpoints.id",
            name="fk_deliveries_endpoint_id_endpoints",
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="pending",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
