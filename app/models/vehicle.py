import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.sql import func

from ..database import Base
from .guid import GUID


class Vehicle(Base):
    """A driver's own vehicle (tipo/dominio/marca/modelo/país) -- self-service.

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
    # Nullable only for a bicycle (no plate; brand/model optional) -- required for every
    # other type at the schema layer (see schemas.VehicleCreate).
    plate = Column(String(10), nullable=True)
    brand = Column(String(80), nullable=True)
    model = Column(String(80), nullable=True)
    # Which kind of vehicle it is -- same set of values as the types a parking spot accepts
    # (car/suv/pickup/van/motorcycle/bicycle, see schemas.VEHICLE_TYPES): it decides which
    # spots it fits in and, for a spot priced per vehicle type, what the driver pays. NULL
    # only for a vehicle saved before types existed; the app asks the driver to fill it in.
    type = Column(String(16), nullable=True)
    # ISO 3166-1 alpha-2 (e.g. "AR", "BR", "UY", "PY") -- drives which plate graphic mobile
    # renders (see VehiclePlate.tsx), not just a free-text label.
    country = Column(String(2), nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
