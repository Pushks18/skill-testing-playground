import os
import pathlib
import socket
import sys

import pytest
import httpx
import subprocess
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SERVER_PATH = REPO_ROOT / "eval" / "mock_mcp" / "server.py"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def mcp_server():
    # sys.executable: bare "python" is not on PATH in all environments
    # (only python3 / the venv interpreter). Absolute script path: pytest
    # may be invoked from any cwd. Free port: a long-running dev mock server
    # may already occupy the default 8000.
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(SERVER_PATH)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={**os.environ, "MOCK_MCP_PORT": str(port)},
    )
    base_url = f"http://localhost:{port}"
    deadline = time.monotonic() + 15.0
    while True:
        if proc.poll() is not None:
            raise RuntimeError(f"mock MCP server exited early (code {proc.returncode})")
        try:
            if httpx.get(f"{base_url}/health", timeout=1.0).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        if time.monotonic() > deadline:
            proc.terminate()
            proc.wait()
            raise RuntimeError("mock MCP server did not become healthy within 15s")
        time.sleep(0.2)
    yield base_url
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
