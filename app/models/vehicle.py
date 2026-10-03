import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.sql import func

from ..database import Base
from .guid import GUID


class Vehicle(Base):
    """A driver's own vehicle (dominio/marca/modelo/país) -- entirely optional, self-service.

    Picked (optionally) when booking a spot so the owner knows which plate to expect; the
    booking itself stores its own snapshot of plate/brand/model/country at creation time (see
    booking-service's Booking entity), so editing or deleting a Vehicle here never changes an
    already-made booking's record.
    """

    __tablename__ = "vehicles"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Not uppercased/validated beyond trimming at the schema layer (see
    # schemas.VehicleCreate) -- plate formats vary enough by country that strict
    # validation would just reject real plates.
    plate = Column(String(10), nullable=False)
    brand = Column(String(80), nullable=False)
    model = Column(String(80), nullable=False)
    # ISO 3166-1 alpha-2 (e.g. "AR", "BR", "UY", "PY") -- drives which plate graphic mobile
    # renders (see VehiclePlate.tsx), not just a free-text label.
    country = Column(String(2), nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
