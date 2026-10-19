from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from relaykit.database.base import Base


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "event_type",
            "endpoint_id",
            name="uq_subscriptions_event_type_endpoint_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    endpoint_id: Mapped[str] = mapped_column(
        String(35),
        ForeignKey(
            "endpoints.id",
            name="fk_subscriptions_endpoint_id_endpoints",
        ),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
