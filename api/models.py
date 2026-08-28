"""
Pydantic models for Real Estate Simulation
Validation for all MongoDB entities
"""
from typing import Annotated, Optional, List, Literal
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr, field_validator
from pydantic.functional_validators import AfterValidator
from bson import ObjectId


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


class User(BaseModel):
    """User entity, as it is stored.

    The field names here are the field names in the documents: this model is
    what a reader consults to know what a user looks like, so a name that does
    not match the collection is worse than no model at all. ``hashedPassword``
    in particular is the field ``authenticate_user`` reads.
    """
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    name: str
    hashedPassword: str  # bcrypt hash, never the password itself
    roles: List[str] = Field(default_factory=lambda: ["user"])
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class UserRegister(BaseModel):
    """User registration request"""
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    name: str
    password: str = Field(min_length=8, description="Minimum 8 characters, must contain uppercase, lowercase, and digit")
    
    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v):
        import re
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one digit')
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
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    zone: str
    type: Literal["house", "apartment"]
    surface: float = Field(gt=0)
    epc: float = Field(ge=0, le=1)  # Energy performance score [0,1]
    state: float = Field(ge=0, le=1)  # General state score [0,1]
    kitchen: float = Field(ge=0, le=1)  # Kitchen quality score [0,1]
    bath: float = Field(ge=0, le=1)  # Bathroom quality score [0,1]
    base_ppm: float = Field(gt=0)  # Base price per m² for zone/type
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class LocalIndex(BaseModel):
    """Local zone indicators for a given quarter"""
    zone: str
    access: float  # Accessibility score
    attract: float  # Attractiveness score
    nuisance: float  # Nuisance score
    tension: float  # Market tension score


class MarketIndex(BaseModel):
    """Market indices for a given quarter"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    t: str  # Quarter "YYYY-Q"
    inflation: float
    rate: float  # Interest rate
    income: float  # Average income evolution
    unemployment: float
    confidence: float  # Consumer confidence
    policy: float  # Policy impact
    locals: List[LocalIndex]

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class Listing(BaseModel):
    """Market listing"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    propertyId: PyObjectId
    isAvailable: bool = True
    lastComputedPrice: float = Field(ge=0)
    lastT: str  # Last quarter computed "YYYY-Q"

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class Portfolio(BaseModel):
    """User portfolio"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    userId: PyObjectId
    cash: float = Field(ge=0)
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class WorkItem(BaseModel):
    """Renovation work item within a holding"""
    renoId: PyObjectId
    startT: str  # Start quarter "YYYY-Q"
    endT: str  # End quarter "YYYY-Q"
    status: Literal["ongoing", "completed"] = "ongoing"


class Holding(BaseModel):
    """Property held in portfolio"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    portfolioId: PyObjectId
    propertyId: PyObjectId
    buyPrice: float = Field(ge=0)
    buyDate: datetime = Field(default_factory=datetime.utcnow)
    works: List[WorkItem] = []

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class RenovationDelta(BaseModel):
    """Deltas applied by a renovation"""
    epc: float = 0.0
    state: float = 0.0
    kitchen: float = 0.0
    bath: float = 0.0
    surfacePct: float = 0.0  # % increase in surface


class Renovation(BaseModel):
    """Renovation type catalog"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    code: str
    label: str
    cost: float = Field(ge=0)
    durationQ: int = Field(ge=1)  # Duration in quarters
    delta: RenovationDelta

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class Trade(BaseModel):
    """Trade (buy or sell)"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    portfolioId: PyObjectId
    propertyId: PyObjectId
    side: Literal["buy", "sell"]
    price: float = Field(ge=0)
    fees: float = Field(ge=0)
    ts: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class PriceHistory(BaseModel):
    """Historical price for a property at a given quarter"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    propertyId: PyObjectId
    t: str  # Quarter "YYYY-Q"
    price: float = Field(ge=0)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


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
