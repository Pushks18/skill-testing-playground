import hashlib
import os
import uuid
import random
from fastapi import FastAPI
import uvicorn
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Mock Mondee MCP")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"status": "ok"}


def _seeded(key: str) -> random.Random:
    """Return a Random instance seeded by key so same params → same response."""
    seed = int(hashlib.md5(key.encode()).hexdigest(), 16) % (2**32)
    return random.Random(seed)

class FlightSearch(BaseModel):
    origin: str
    destination: str
    date: str
    passengers: int = 1

class HotelSearch(BaseModel):
    location: str
    check_in: str
    check_out: str
    guests: int = 1

class AvailabilityCheck(BaseModel):
    resource_id: str
    date: str

class FareRulesRequest(BaseModel):
    flight_id: str

class PassengerValidation(BaseModel):
    name: str
    dob: str
    passport: Optional[str] = None

class BookingRequest(BaseModel):
    flight_id: Optional[str] = None
    hotel_id: Optional[str] = None
    passenger: dict

class ModifyBookingRequest(BaseModel):
    booking_id: str
    changes: dict

class CancelBookingRequest(BaseModel):
    booking_id: str

class GetItineraryRequest(BaseModel):
    booking_id: str

class AncillaryRequest(BaseModel):
    booking_id: str
    service_type: str
    details: Optional[dict] = None

AIRLINES = ["Delta", "United", "American", "JetBlue", "Southwest"]
HOTEL_CHAINS = ["Marriott", "Hilton", "Hyatt", "IHG", "Wyndham"]

@app.post("/search_flights")
def search_flights(req: FlightSearch):
    rng = _seeded(f"flights:{req.origin}:{req.destination}:{req.date}:{req.passengers}")
    flights = [
        {
            "flight_id": f"FL{rng.randint(100,999)}",
            "airline": rng.choice(AIRLINES),
            "origin": req.origin,
            "destination": req.destination,
            "date": req.date,
            "departure": f"{rng.randint(6,20):02d}:{rng.choice(['00','30'])}",
            "duration_min": rng.randint(90, 360),
            "price": round(rng.uniform(150, 900), 2),
            "seats_available": rng.randint(1, 30),
            "cabin": "economy",
        }
        for _ in range(rng.randint(3, 6))
    ]
    return {"flights": flights, "currency": "USD"}

@app.post("/search_hotels")
def search_hotels(req: HotelSearch):
    rng = _seeded(f"hotels:{req.location}:{req.check_in}:{req.check_out}:{req.guests}")
    hotels = [
        {
            "hotel_id": f"HT{rng.randint(100,999)}",
            "name": f"{rng.choice(HOTEL_CHAINS)} {req.location}",
            "location": req.location,
            "check_in": req.check_in,
            "check_out": req.check_out,
            "price_per_night": round(rng.uniform(80, 500), 2),
            "stars": rng.randint(3, 5),
            "amenities": rng.sample(["WiFi", "Pool", "Gym", "Breakfast", "Parking", "Spa"], k=3),
            "cancellation_policy": rng.choice(["Free cancellation until 24h before", "Non-refundable", "Free cancellation until 48h before"]),
            "available": True,
        }
        for _ in range(rng.randint(3, 5))
    ]
    return {"hotels": hotels, "currency": "USD"}

@app.post("/check_availability")
def check_availability(req: AvailabilityCheck):
    rng = _seeded(f"avail:{req.resource_id}:{req.date}")
    return {"resource_id": req.resource_id, "date": req.date, "available": rng.random() > 0.2}

@app.post("/get_fare_rules")
def get_fare_rules(req: FareRulesRequest):
    rng = _seeded(f"fare:{req.flight_id}")
    return {
        "flight_id": req.flight_id,
        "cancellation": "Free within 24h; $150 fee after",
        "changes": "$75 change fee applies",
        "baggage": "1 carry-on included; checked bag $35",
        "refundable": rng.random() > 0.5,
    }

@app.post("/validate_passenger")
def validate_passenger(req: PassengerValidation):
    return {"valid": True, "name": req.name, "warnings": []}

@app.post("/create_booking")
def create_booking(req: BookingRequest):
    return {
        "booking_id": f"BK{uuid.uuid4().hex[:8].upper()}",
        "status": "confirmed",
        "flight_id": req.flight_id,
        "hotel_id": req.hotel_id,
        "total_price": round(random.uniform(200, 1500), 2),
    }

@app.post("/modify_booking")
def modify_booking(req: ModifyBookingRequest):
    return {"booking_id": req.booking_id, "status": "modified", "changes_applied": req.changes}

@app.post("/cancel_booking")
def cancel_booking(req: CancelBookingRequest):
    return {"booking_id": req.booking_id, "status": "cancelled", "refund_amount": round(random.uniform(0, 500), 2)}

@app.post("/get_itinerary")
def get_itinerary(req: GetItineraryRequest):
    return {
        "booking_id": req.booking_id,
        "itinerary": [
            {"type": "flight", "details": "JFK → LAX, 2026-07-01 09:00"},
            {"type": "hotel", "details": "Marriott LA, 2026-07-01 to 2026-07-03"},
        ],
    }

ANCILLARY_PRICES = {
    "seat_selection": {"window": 15, "aisle": 12, "extra_legroom": 45, "bulkhead": 50},
    "extra_baggage": {"23kg": 35, "32kg": 60},
    "travel_insurance": {"basic": 25, "standard": 55, "premium": 90},
    "lounge_access": {"day_pass": 40},
    "priority_boarding": {"fee": 12},
    "car_rental": {"economy": 45, "compact": 55, "suv": 85},
    "airport_transfer": {"shared": 20, "private": 65},
}

@app.post("/add_ancillary")
def add_ancillary(req: AncillaryRequest):
    prices = ANCILLARY_PRICES.get(req.service_type, {})
    details = req.details or {}
    tier = list(details.values())[0] if details else list(prices.keys())[0] if prices else "standard"
    price = prices.get(str(tier), 30)
    return {
        "booking_id": req.booking_id,
        "ancillary_id": f"ANC{uuid.uuid4().hex[:6].upper()}",
        "service_type": req.service_type,
        "details": details,
        "price_usd": price,
        "status": "confirmed",
    }


if __name__ == "__main__":
    # MOCK_MCP_PORT lets tests spawn an isolated instance without colliding
    # with a long-running dev server on the default port 8000.
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("MOCK_MCP_PORT", "8000")))
