from sqlalchemy import Column, String, DateTime
from datetime import datetime

from app.database import Base


class WebhookEvent(Base):
    """Dedupe table for external webhook deliveries (Stripe, etc.).

    Stripe retries every webhook until we return 2xx, and will re-deliver on
    transient failures. Handlers mutate billing state, so we MUST NOT process
    the same event twice. Inserting the event id as a PK lets us atomically
    claim the event: the first worker wins, duplicates fail with unique-key
    violation and are ignored.
    """

    __tablename__ = "webhook_events"

    event_id = Column(String, primary_key=True)
    source = Column(String, nullable=False, default="stripe")
    event_type = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
