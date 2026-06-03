import uuid
import random
from fastapi import FastAPI
import uvicorn
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Mock Mondee MCP")

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

AIRLINES = ["Delta", "United", "American", "JetBlue", "Southwest"]
HOTEL_CHAINS = ["Marriott", "Hilton", "Hyatt", "IHG", "Wyndham"]

@app.post("/search_flights")
def search_flights(req: FlightSearch):
    flights = [
        {
            "flight_id": f"FL{random.randint(100,999)}",
            "airline": random.choice(AIRLINES),
            "origin": req.origin,
            "destination": req.destination,
            "date": req.date,
            "departure": f"{random.randint(6,20):02d}:{random.choice(['00','30'])}",
            "duration_min": random.randint(90, 360),
            "price": round(random.uniform(150, 900), 2),
            "seats_available": random.randint(1, 30),
            "cabin": "economy",
        }
        for _ in range(random.randint(3, 6))
    ]
    return {"flights": flights, "currency": "USD"}

@app.post("/search_hotels")
def search_hotels(req: HotelSearch):
    hotels = [
        {
            "hotel_id": f"HT{random.randint(100,999)}",
            "name": f"{random.choice(HOTEL_CHAINS)} {req.location}",
            "location": req.location,
            "check_in": req.check_in,
            "check_out": req.check_out,
            "price_per_night": round(random.uniform(80, 500), 2),
            "stars": random.randint(3, 5),
            "available": True,
        }
        for _ in range(random.randint(3, 5))
    ]
    return {"hotels": hotels, "currency": "USD"}

@app.post("/check_availability")
def check_availability(req: AvailabilityCheck):
    return {"resource_id": req.resource_id, "date": req.date, "available": random.random() > 0.2}

@app.post("/get_fare_rules")
def get_fare_rules(req: FareRulesRequest):
    return {
        "flight_id": req.flight_id,
        "cancellation": "Free within 24h; $150 fee after",
        "changes": "$75 change fee applies",
        "baggage": "1 carry-on included; checked bag $35",
        "refundable": random.random() > 0.5,
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
