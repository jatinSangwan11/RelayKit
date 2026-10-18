from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from relaykit.database.base import Base


class Endpoint(Base):
    __tablename__ = "endpoints"

    id: Mapped[str] = mapped_column(String(35), primary_key=True)
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="active",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(), # this is postgres time only - and it returns the time at which the transaction started not the time at which transaction committed
    )
