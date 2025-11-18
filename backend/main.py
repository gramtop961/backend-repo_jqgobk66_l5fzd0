import os
from datetime import datetime, date
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents
from schemas import (
    Property, RoomType, Reservation, ReservationGuest,
    AvailabilitySearch, AvailabilityResult, AvailabilityResultItem,
    CreatePropertyRequest, CreateRoomTypeRequest, CreateReservationRequest,
    EmailNotification,
)

import smtplib
from email.mime.text import MIMEText
from bson import ObjectId

app = FastAPI(title="Booking Engine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Booking Engine Backend Running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response

# Utility

def generate_confirmation_code(prefix: str = "RES") -> str:
    return f"{prefix}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

# Email sending helper (simple SMTP)

def send_email(notification: EmailNotification) -> bool:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    sender = os.getenv("SMTP_SENDER", user or "no-reply@example.com")

    if not host:
        # SMTP not configured, simulate success (log only)
        print(f"[Email] To: {notification.to} | Subject: {notification.subject}\n{notification.body}")
        return True

    try:
        msg = MIMEText(notification.body, "html")
        msg["Subject"] = notification.subject
        msg["From"] = sender
        msg["To"] = notification.to

        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            if user and password:
                server.login(user, password)
            server.send_message(msg)
        return True
    except Exception as e:
        print("Email error:", e)
        return False

# ======== Property and RoomType Management ========

@app.post("/api/properties", response_model=dict)
def create_property(payload: CreatePropertyRequest):
    property_id = create_document("property", payload)
    return {"id": property_id}

@app.get("/api/properties", response_model=List[Property])
def list_properties():
    return get_documents("property")

@app.post("/api/room-types", response_model=dict)
def create_room_type(payload: CreateRoomTypeRequest):
    room_type_id = create_document("roomtype", payload)
    return {"id": room_type_id}

@app.get("/api/room-types", response_model=List[RoomType])
def list_room_types(property_id: Optional[str] = None):
    filt = {"property_id": property_id} if property_id else {}
    return get_documents("roomtype", filt)

# ======== Availability Search ========

@app.post("/api/availability", response_model=AvailabilityResult)
def search_availability(payload: AvailabilitySearch):
    # Simple availability: all room types for the property are available with base price.
    room_types = get_documents("roomtype", {"property_id": payload.property_id})
    items: List[AvailabilityResultItem] = []
    for rt in room_types:
        items.append(AvailabilityResultItem(
            room_type_id=str(rt.get("_id")),
            name=rt.get("name"),
            description=rt.get("description"),
            max_guests=rt.get("max_guests"),
            nightly_price=float(rt.get("base_price", 0)),
            available=True
        ))
    return AvailabilityResult(items=items)

# ======== Reservation (Direct + OTA Webhook) ========

@app.post("/api/reservations", response_model=dict)
def create_reservation(payload: CreateReservationRequest):
    # Price calculation: simple nightly price * nights
    try:
        rt = db["roomtype"].find_one({"_id": ObjectId(payload.room_type_id)})
    except Exception:
        rt = None
    if not rt:
        raise HTTPException(status_code=404, detail="Room type not found")

    nights = (payload.check_out - payload.check_in).days
    if nights <= 0:
        raise HTTPException(status_code=400, detail="check_out must be after check_in")

    total_price = float(rt.get("base_price", 0)) * nights
    confirmation_code = generate_confirmation_code()

    reservation = Reservation(
        property_id=payload.property_id,
        room_type_id=payload.room_type_id,
        check_in=payload.check_in,
        check_out=payload.check_out,
        guests=payload.guests,
        total_price=total_price,
        currency="USD",
        channel="direct",
        status="confirmed",
        guest=payload.guest,
        special_requests=payload.special_requests,
        confirmation_code=confirmation_code,
    )
    res_id = create_document("reservation", reservation)

    # Send email notification
    to_email = os.getenv("BOOKING_NOTIFICATION_EMAIL", reservation.guest.email)
    subject = f"New Reservation {confirmation_code}"
    nights_text = nights
    body = f"""
    <h2>New Reservation</h2>
    <p><strong>Confirmation:</strong> {confirmation_code}</p>
    <p><strong>Property:</strong> {reservation.property_id}</p>
    <p><strong>Room Type:</strong> {reservation.room_type_id}</p>
    <p><strong>Dates:</strong> {reservation.check_in} to {reservation.check_out} ({nights_text} nights)</p>
    <p><strong>Guest:</strong> {reservation.guest.first_name} {reservation.guest.last_name} ({reservation.guest.email})</p>
    <p><strong>Total:</strong> {reservation.total_price} {reservation.currency}</p>
    <p><strong>Channel:</strong> {reservation.channel}</p>
    """
    send_email(EmailNotification(to=to_email, subject=subject, body=body))

    return {"id": res_id, "confirmation_code": confirmation_code}

# OTA webhook endpoint (e.g., Booking.com, channel managers)
class OTAWebhookPayload(BaseModel):
    property_id: str
    room_type_id: str
    check_in: date
    check_out: date
    guests: int
    guest: ReservationGuest
    total_price: Optional[float] = None
    currency: Optional[str] = "USD"
    channel: str = "booking.com"
    confirmation_code: Optional[str] = None

@app.post("/api/ota/webhook", response_model=dict)
def ota_webhook(payload: OTAWebhookPayload):
    # Accept OTA pushes. If confirmation_code not provided, generate one.
    confirmation_code = payload.confirmation_code or generate_confirmation_code("OTA")
    nights = (payload.check_out - payload.check_in).days
    if nights <= 0:
        raise HTTPException(status_code=400, detail="check_out must be after check_in")

    # If total_price not provided, attempt simple calc from room type base_price
    try:
        rt = db["roomtype"].find_one({"_id": ObjectId(payload.room_type_id)})
        base_price = float(rt.get("base_price", 0)) if rt else 0.0
    except Exception:
        base_price = 0.0
    total_price = payload.total_price if payload.total_price is not None else base_price * nights

    reservation = Reservation(
        property_id=payload.property_id,
        room_type_id=payload.room_type_id,
        check_in=payload.check_in,
        check_out=payload.check_out,
        guests=payload.guests,
        total_price=total_price,
        currency=payload.currency or "USD",
        channel=payload.channel,
        status="confirmed",
        guest=payload.guest,
        special_requests=None,
        confirmation_code=confirmation_code,
    )
    res_id = create_document("reservation", reservation)

    # Notify email
    to_email = os.getenv("BOOKING_NOTIFICATION_EMAIL", reservation.guest.email)
    subject = f"OTA Reservation {confirmation_code} ({payload.channel})"
    body = f"""
    <h2>OTA Reservation</h2>
    <p><strong>Channel:</strong> {payload.channel}</p>
    <p><strong>Confirmation:</strong> {confirmation_code}</p>
    <p><strong>Property:</strong> {reservation.property_id}</p>
    <p><strong>Room Type:</strong> {reservation.room_type_id}</p>
    <p><strong>Dates:</strong> {reservation.check_in} to {reservation.check_out} ({nights} nights)</p>
    <p><strong>Guest:</strong> {reservation.guest.first_name} {reservation.guest.last_name} ({reservation.guest.email})</p>
    <p><strong>Total:</strong> {reservation.total_price} {reservation.currency}</p>
    """
    send_email(EmailNotification(to=to_email, subject=subject, body=body))

    return {"id": res_id, "confirmation_code": confirmation_code}

# Health for schemas viewer
@app.get("/schema")
def get_schema_names():
    return {
        "collections": [
            "property",
            "roomtype",
            "reservation"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
