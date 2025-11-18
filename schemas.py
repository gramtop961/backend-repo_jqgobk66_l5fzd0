"""
Database Schemas for Booking Engine

Each Pydantic model represents a collection in MongoDB. The collection name is the lowercase of the class name.
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import date, datetime

# Core domain schemas

class Property(BaseModel):
    name: str = Field(..., description="Property name")
    address: str = Field(..., description="Street address")
    city: str = Field(..., description="City")
    country: str = Field(..., description="Country")
    timezone: Optional[str] = Field("UTC", description="IANA timezone string")
    contact_email: Optional[EmailStr] = Field(None, description="Property contact email")

class RoomType(BaseModel):
    property_id: str = Field(..., description="ID of the property this room belongs to")
    name: str = Field(..., description="Room type name (e.g., Deluxe King)")
    description: Optional[str] = None
    max_guests: int = Field(..., ge=1, description="Maximum occupancy")
    base_price: float = Field(..., ge=0, description="Base nightly price")

class ReservationGuest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None

class Reservation(BaseModel):
    property_id: str
    room_type_id: str
    check_in: date
    check_out: date
    guests: int = Field(..., ge=1)
    total_price: float = Field(..., ge=0)
    currency: str = Field("USD", min_length=3, max_length=3)
    channel: str = Field("direct", description="booking channel: direct, booking.com, airbnb, etc.")
    status: str = Field("confirmed", description="confirmed, pending, cancelled")
    guest: ReservationGuest
    special_requests: Optional[str] = None
    confirmation_code: Optional[str] = None

class AvailabilitySearch(BaseModel):
    property_id: str
    check_in: date
    check_out: date
    guests: int = Field(..., ge=1)

class CreatePropertyRequest(Property):
    pass

class CreateRoomTypeRequest(RoomType):
    pass

class CreateReservationRequest(BaseModel):
    property_id: str
    room_type_id: str
    check_in: date
    check_out: date
    guests: int
    guest: ReservationGuest
    special_requests: Optional[str] = None

class AvailabilityResultItem(BaseModel):
    room_type_id: str
    name: str
    description: Optional[str] = None
    max_guests: int
    nightly_price: float
    available: bool

class AvailabilityResult(BaseModel):
    items: List[AvailabilityResultItem]

class EmailNotification(BaseModel):
    to: EmailStr
    subject: str
    body: str
    sent_at: Optional[datetime] = None
