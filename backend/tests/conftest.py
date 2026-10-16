import ipaddress
import socket

import pytest

import ai_planner
import database


@pytest.fixture(autouse=True)
def no_real_database(monkeypatch):
    """Tests never connect to the DATABASE_URL from backend/.env."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "_engine", None)
    monkeypatch.setattr(database, "_session_factory", None)


@pytest.fixture(autouse=True)
def no_real_ai(monkeypatch):
    """Tests can never reach the real Gemini API or use a real key:
    - any GEMINI_* values loaded from backend/.env are removed,
    - the base URL points at an unresolvable reserved domain,
    - the rate-limit cooldown starts clear for every test."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setattr(ai_planner, "GEMINI_BASE_URL", "https://gemini.test.invalid/v1beta/models")
    monkeypatch.setattr(ai_planner, "_cooldown_until", 0.0)


def _is_loopback(address) -> bool:
    host = address[0] if isinstance(address, tuple) else address
    if host in ("localhost",):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def no_outbound_network(monkeypatch):
    """Block every non-loopback socket connection (loopback is still allowed:
    the event loop uses a local socket pair internally)."""
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def guarded_connect(self, address):
        if not _is_loopback(address):
            raise ConnectionRefusedError(f"network access disabled in tests: {address!r}")
        return real_connect(self, address)

    def guarded_connect_ex(self, address):
        if not _is_loopback(address):
            raise ConnectionRefusedError(f"network access disabled in tests: {address!r}")
        return real_connect_ex(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
