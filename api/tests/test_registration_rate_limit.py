"""Registration is bounded, like login.

Login has been rate limited from the start. Registration was not, and it is the
more expensive of the two: each call hashes a password with bcrypt and inserts
a user and a portfolio holding a million in cash. Nothing stopped one caller
from doing that in a loop.

Keyed on the client address, not on the username: a registration username is
whatever the caller just invented, so limiting per username limits nobody.
"""

import pytest

from api.database import get_database
from api.routers.auth import REGISTRATION_LIMIT
from api.tests.conftest import api_client


def _account(index: int) -> dict:
    return {
        "username": f"flood{index}",
        "email": f"flood{index}@example.com",
        "name": f"Flood {index}",
        "password": "StrongEnoughPassword1",
    }


async def _register(index: int, host: str):
    async with api_client(client_host=host) as client:
        return await client.post("/auth/register", json=_account(index))


@pytest.mark.asyncio
async def test_one_address_can_register_up_to_the_limit():
    """The limit is a ceiling, not a smaller number: the Nth call still works."""
    for index in range(REGISTRATION_LIMIT):
        response = await _register(index, "203.0.113.10")
        assert response.status_code == 201, (index, response.text)


@pytest.mark.asyncio
async def test_the_next_registration_from_that_address_is_refused():
    """The exact defect: an unbounded loop of account creation."""
    for index in range(REGISTRATION_LIMIT):
        await _register(index, "203.0.113.11")

    response = await _register(REGISTRATION_LIMIT, "203.0.113.11")

    assert response.status_code == 429, response.text
    db = get_database()
    assert await db.users.find_one({"username": f"flood{REGISTRATION_LIMIT}"}) is None


@pytest.mark.asyncio
async def test_nothing_is_created_by_a_refused_registration():
    """A 429 must not leave a user, a portfolio, or a bcrypt hash behind."""
    for index in range(REGISTRATION_LIMIT):
        await _register(index, "203.0.113.12")
    before = await get_database().users.count_documents({})

    await _register(99, "203.0.113.12")

    assert await get_database().users.count_documents({}) == before


@pytest.mark.asyncio
async def test_another_address_is_not_affected():
    """The limit is per caller. One flooder must not lock everybody else out."""
    for index in range(REGISTRATION_LIMIT + 3):
        await _register(index, "203.0.113.13")

    response = await _register(500, "198.51.100.7")

    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_registering_does_not_consume_the_login_budget():
    """The two limits are separate buckets, not one shared counter."""
    for index in range(REGISTRATION_LIMIT):
        await _register(index, "203.0.113.14")

    async with api_client(client_host="203.0.113.14") as client:
        response = await client.post(
            "/auth/login", json={"username": "flood0", "password": "StrongEnoughPassword1"}
        )

    assert response.status_code == 200, response.text
