"""
Pydantic models for Real Estate Simulation
Validation for all MongoDB entities
"""

from datetime import datetime
from typing import Annotated, Literal

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from pydantic.functional_validators import AfterValidator

from api.clock import utc_now
from simulation.constants import ZONES


class PyObjectId(ObjectId):
    """Custom ObjectId type for Pydantic"""

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema):
        field_schema.update(type="string")


# Every model below describes a stored document, and they all need the same
# two settings: accept the stored field name as well as the alias, and allow
# ObjectId, which pydantic does not know how to validate on its own. Stated
# once rather than repeated verbatim under each class.
#
# ``json_encoders`` used to be here too. It is deprecated in pydantic v2, and
# every id these models expose is serialised as a string by the route handlers
# before it leaves, so nothing depended on it.
DOCUMENT_MODEL_CONFIG = ConfigDict(
    populate_by_name=True,
    arbitrary_types_allowed=True,
)


def _must_look_like_an_object_id(value: str) -> str:
    """Reject anything ``ObjectId()`` would refuse, at the request boundary.

    ``ObjectId("not-an-id")`` raises ``bson.errors.InvalidId``. Raised inside a
    handler that exception escapes to the global handler and the caller gets a
    500, which reports a server fault for what is plainly a bad request. Parsed
    here it is a 422 with the offending field named, and every handler past
    this point can construct an ObjectId without a guard.
    """
    if not ObjectId.is_valid(value):
        raise ValueError("must be a 24-character hexadecimal object id")
    return value


# A string that is known to be a valid object id. Use this, never a bare `str`,
# for any identifier arriving from a request.
ObjectIdStr = Annotated[str, AfterValidator(_must_look_like_an_object_id)]


def _must_be_a_known_zone(value: str) -> str:
    """Reject a zone the simulation has no numbers for.

    Every zone in ``ZONES`` has a base price per square metre, an appreciation
    trend and a local index. A zone outside that list cannot be priced at all,
    so accepting one only defers the failure to the first time somebody asks
    what the property is worth.

    Checked against the list rather than repeated as a ``Literal`` so the
    zones are named in exactly one place.
    """
    if value not in ZONES:
        raise ValueError(f"must be one of the known zones: {', '.join(ZONES)}")
    return value


# A zone the simulation can price. Use this, never a bare `str`.
Zone = Annotated[str, AfterValidator(_must_be_a_known_zone)]


class User(BaseModel):
    """User entity, as it is stored.

    The field names here are the field names in the documents: this model is
    what a reader consults to know what a user looks like, so a name that does
    not match the collection is worse than no model at all. ``hashedPassword``
    in particular is the field ``authenticate_user`` reads.
    """

    id: PyObjectId | None = Field(default=None, alias="_id")
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    name: str
    hashedPassword: str  # bcrypt hash, never the password itself
    roles: list[str] = Field(default_factory=lambda: ["user"])
    createdAt: datetime = Field(default_factory=utc_now)

    model_config = DOCUMENT_MODEL_CONFIG


class UserRegister(BaseModel):
    """User registration request"""

    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    name: str
    password: str = Field(
        min_length=8,
        description="At least 8 characters, with an uppercase letter, a "
        "lowercase letter and a digit",
    )

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """The password rule, stated here and nowhere else.

        Registration is the only way a password enters the system, so this is
        the boundary that owns the rule. A second copy inside the handler would
        be unreachable (pydantic runs first) and free to drift.

        ``str.isupper`` and friends are used rather than an ASCII character
        class, so an accented capital counts as a capital.
        """
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserLogin(BaseModel):
    """User login request"""

    username: str
    password: str


class Token(BaseModel):
    """JWT token response"""

    access_token: str
    token_type: str = "bearer"
    user: dict


class Property(BaseModel):
    """Property entity (intrinsic characteristics)"""

    id: PyObjectId | None = Field(default=None, alias="_id")
    zone: str
    type: Literal["house", "apartment"]
    surface: float = Field(gt=0)
    epc: float = Field(ge=0, le=1)  # Energy performance score [0,1]
    state: float = Field(ge=0, le=1)  # General state score [0,1]
    kitchen: float = Field(ge=0, le=1)  # Kitchen quality score [0,1]
    bath: float = Field(ge=0, le=1)  # Bathroom quality score [0,1]
    base_ppm: float = Field(gt=0)  # Base price per m² for zone/type
    createdAt: datetime = Field(default_factory=utc_now)

    model_config = DOCUMENT_MODEL_CONFIG


class PropertyCreate(BaseModel):
    """What a caller may say when creating a property.

    Deliberately not the same shape as :class:`Property`: `base_ppm` is absent.
    The base price per square metre decides every future price of the property,
    so it is derived server-side from the zone and type table rather than
    accepted from whoever is calling. The zone is a closed set for the same
    reason: a zone outside the table has no base price, no appreciation trend
    and no local index, and would be priced from whatever arrived in the body.
    """

    zone: Zone
    type: Literal["house", "apartment"]
    surface: float = Field(gt=0)
    epc: float = Field(ge=0, le=1)
    state: float = Field(ge=0, le=1)
    kitchen: float = Field(ge=0, le=1)
    bath: float = Field(ge=0, le=1)

    # An unexpected field is a caller trying to set something it does not own,
    # most likely base_ppm. Refuse it rather than ignore it.
    model_config = ConfigDict(extra="forbid")


class LocalIndex(BaseModel):
    """Local zone indicators for a given quarter"""

    zone: str
    access: float  # Accessibility score
    attract: float  # Attractiveness score
    nuisance: float  # Nuisance score
    tension: float  # Market tension score


class MarketIndex(BaseModel):
    """Market indices for a given quarter"""

    id: PyObjectId | None = Field(default=None, alias="_id")
    t: str  # Quarter "YYYY-Q"
    inflation: float
    rate: float  # Interest rate
    income: float  # Average income evolution
    unemployment: float
    confidence: float  # Consumer confidence
    policy: float  # Policy impact
    locals: list[LocalIndex]

    model_config = DOCUMENT_MODEL_CONFIG


class Listing(BaseModel):
    """Market listing"""

    id: PyObjectId | None = Field(default=None, alias="_id")
    propertyId: PyObjectId
    isAvailable: bool = True
    lastComputedPrice: float = Field(ge=0)
    lastT: str  # Last quarter computed "YYYY-Q"

    model_config = DOCUMENT_MODEL_CONFIG


class Portfolio(BaseModel):
    """User portfolio"""

    id: PyObjectId | None = Field(default=None, alias="_id")
    userId: PyObjectId
    cash: float = Field(ge=0)
    createdAt: datetime = Field(default_factory=utc_now)

    model_config = DOCUMENT_MODEL_CONFIG


class WorkItem(BaseModel):
    """Renovation work item within a holding"""

    renoId: PyObjectId
    startT: str  # Start quarter "YYYY-Q"
    endT: str  # End quarter "YYYY-Q"
    status: Literal["ongoing", "completed"] = "ongoing"


class Holding(BaseModel):
    """Property held in portfolio"""

    id: PyObjectId | None = Field(default=None, alias="_id")
    portfolioId: PyObjectId
    propertyId: PyObjectId
    buyPrice: float = Field(ge=0)
    buyDate: datetime = Field(default_factory=utc_now)
    works: list[WorkItem] = []

    model_config = DOCUMENT_MODEL_CONFIG


class RenovationDelta(BaseModel):
    """Deltas applied by a renovation"""

    epc: float = 0.0
    state: float = 0.0
    kitchen: float = 0.0
    bath: float = 0.0
    surfacePct: float = 0.0  # % increase in surface


class Renovation(BaseModel):
    """Renovation type catalog"""

    id: PyObjectId | None = Field(default=None, alias="_id")
    code: str
    label: str
    cost: float = Field(ge=0)
    durationQ: int = Field(ge=1)  # Duration in quarters
    delta: RenovationDelta

    model_config = DOCUMENT_MODEL_CONFIG


class Trade(BaseModel):
    """Trade (buy or sell)"""

    id: PyObjectId | None = Field(default=None, alias="_id")
    portfolioId: PyObjectId
    propertyId: PyObjectId
    side: Literal["buy", "sell"]
    price: float = Field(ge=0)
    fees: float = Field(ge=0)
    ts: datetime = Field(default_factory=utc_now)

    model_config = DOCUMENT_MODEL_CONFIG


class PriceHistory(BaseModel):
    """Historical price for a property at a given quarter"""

    id: PyObjectId | None = Field(default=None, alias="_id")
    propertyId: PyObjectId
    t: str  # Quarter "YYYY-Q"
    price: float = Field(ge=0)

    model_config = DOCUMENT_MODEL_CONFIG


# Request/Response models
class BuyRequest(BaseModel):
    """Request to buy a property"""

    propertyId: ObjectIdStr


class SellRequest(BaseModel):
    """Request to sell a property"""

    propertyId: ObjectIdStr


class RenovateRequest(BaseModel):
    """Request to start a renovation"""

    holdingId: ObjectIdStr
    renoCode: str


class PortfolioSummary(BaseModel):
    """Portfolio summary response"""

    cash: float
    equity: float
    totalValue: float
    pnlTotal: float
    pnlYTD: float


class HoldingDetail(BaseModel):
    """Detailed holding information"""

    holdingId: str
    propertyId: str
    zone: str
    type: str
    surface: float
    buyPrice: float
    buyFees: float = 0.0
    renovationCosts: float = 0.0
    totalInvested: float
    currentPrice: float
    pnl: float
    pnlPct: float
    ongoingWorks: int
