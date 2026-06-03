import pytest
import httpx
import subprocess
import time
import signal

@pytest.fixture(scope="module")
def mcp_server():
    proc = subprocess.Popen(
        ["python", "eval/mock_mcp/server.py"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(2.0)
    yield "http://localhost:8000"
    proc.terminate()
    proc.wait()

def test_search_flights(mcp_server):
    r = httpx.post(f"{mcp_server}/search_flights",
                   json={"origin": "JFK", "destination": "LAX", "date": "2026-07-01"})
    assert r.status_code == 200
    data = r.json()
    assert "flights" in data
    assert len(data["flights"]) > 0
    assert "price" in data["flights"][0]

def test_search_hotels(mcp_server):
    r = httpx.post(f"{mcp_server}/search_hotels",
                   json={"location": "Los Angeles", "check_in": "2026-07-01", "check_out": "2026-07-03"})
    assert r.status_code == 200
    assert "hotels" in r.json()

def test_check_availability(mcp_server):
    r = httpx.post(f"{mcp_server}/check_availability",
                   json={"resource_id": "FL123", "date": "2026-07-01"})
    assert r.status_code == 200
    assert "available" in r.json()

def test_create_booking(mcp_server):
    r = httpx.post(f"{mcp_server}/create_booking",
                   json={"flight_id": "FL123", "passenger": {"name": "Alice", "dob": "1990-01-01"}})
    assert r.status_code == 200
    assert "booking_id" in r.json()

def test_get_fare_rules(mcp_server):
    r = httpx.post(f"{mcp_server}/get_fare_rules", json={"flight_id": "FL123"})
    assert r.status_code == 200
    data = r.json()
    assert "cancellation" in data
    assert "baggage" in data

def test_cancel_booking(mcp_server):
    r = httpx.post(f"{mcp_server}/cancel_booking", json={"booking_id": "BK123"})
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
