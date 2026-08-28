"""The password rule, pinned at the boundary that enforces it.

The rule was written twice: once as a pydantic validator on UserRegister and
once as validate_password_strength in the auth router, with different status
codes (422 and 400). Pydantic runs first, so the router copy was unreachable:
two statements of one rule, one of which could drift for a long time without
anybody noticing, because no request ever reached it.

These tests assert the rule through the endpoint, so they hold whichever layer
ends up enforcing it, and they name the reason each password is refused.
"""
import pytest
from httpx import AsyncClient

from api.database import get_database
from api.main import app

REFUSED = [
    ("nouppercase123", "no uppercase letter"),
    ("NOLOWERCASE123", "no lowercase letter"),
    ("NoDigitsAtAllHere", "no digit"),
    ("Ab1", "shorter than eight characters"),
    ("Abcdef1", "seven characters, one short"),
    ("", "empty"),
]


async def _register(client, password, username="candidate"):
    return await client.post("/auth/register", json={
        "username": username,
        "email": f"{username}@example.com",
        "name": "Candidate",
        "password": password,
    })


@pytest.mark.asyncio
@pytest.mark.parametrize("password,why", REFUSED)
async def test_a_password_missing_a_required_class_is_refused(password, why):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await _register(client, password)

    assert response.status_code == 422, f"accepted a password with {why}"


@pytest.mark.asyncio
@pytest.mark.parametrize("password,why", REFUSED)
async def test_a_refused_registration_creates_nothing(password, why):
    async with AsyncClient(app=app, base_url="http://test") as client:
        await _register(client, password)

    db = get_database()
    assert await db.users.count_documents({"username": "candidate"}) == 0
    assert await db.portfolios.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("password", [
    "Abcdefg1",           # exactly eight, one of each class
    "CorrectHorse1",
    "Pass1word-with-punctuation",
    "Éléphant1Majuscule",  # non-ASCII letters still carry case
])
async def test_a_compliant_password_is_accepted(password):
    """The rule must refuse the weak without refusing the merely unusual."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await _register(client, password)

    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_the_password_is_never_stored_or_returned():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await _register(client, "CorrectHorse1")

    assert "CorrectHorse1" not in response.text

    db = get_database()
    stored = await db.users.find_one({"username": "candidate"})
    assert "CorrectHorse1" not in str(stored)
    assert stored["hashedPassword"].startswith("$2")
