"""The balance the API reports is the balance the game spends.

Registration wrote `cashBalance` onto the user document and, separately, `cash`
onto the portfolio. Trading only ever moved the portfolio, and nothing ever
updated `cashBalance` again, so /auth/me answered 1,000,000 for the rest of the
account's life no matter how much had been spent. Two fields holding the same
quantity is one field holding a lie.
"""

import pytest

from api.database import get_database
from api.tests.conftest import api_client


async def _register(client, username="spender"):
    response = await client.post(
        "/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "name": "A Spender",
            "password": "SpenderPassword123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_listing(db, price):
    prop = await db.properties.insert_one(
        {
            "zone": "Bruxelles-Centre",
            "type": "house",
            "surface": 100,
            "epc": 0.6,
            "state": 0.7,
            "kitchen": 0.6,
            "bath": 0.6,
            "base_ppm": 3000,
        }
    )
    await db.listings.insert_one(
        {
            "propertyId": prop.inserted_id,
            "isAvailable": True,
            "lastComputedPrice": price,
            "lastT": "2020-1",
        }
    )
    return prop.inserted_id


@pytest.mark.asyncio
async def test_the_balance_reported_after_a_purchase_is_the_one_that_was_charged():
    db = get_database()
    property_id = await _create_listing(db, 200_000.0)

    async with api_client() as client:
        registration = await _register(client)
        headers = {"Authorization": f"Bearer {registration['access_token']}"}

        await client.post("/trading/buy", headers=headers, json={"propertyId": str(property_id)})
        me = await client.get("/auth/me", headers=headers)
        summary = await client.get("/portfolio/summary", headers=headers)

    # 200,000 + 2.5% fees leaves 795,000 of the starting 1,000,000.
    assert me.json()["cashBalance"] == pytest.approx(795_000.0)
    assert me.json()["cashBalance"] == pytest.approx(summary.json()["cash"])


@pytest.mark.asyncio
async def test_logging_back_in_reports_the_same_balance():
    db = get_database()
    property_id = await _create_listing(db, 200_000.0)

    async with api_client() as client:
        registration = await _register(client)
        headers = {"Authorization": f"Bearer {registration['access_token']}"}
        await client.post("/trading/buy", headers=headers, json={"propertyId": str(property_id)})

        login = await client.post(
            "/auth/login",
            json={
                "username": "spender",
                "password": "SpenderPassword123",
            },
        )

    assert login.json()["user"]["cashBalance"] == pytest.approx(795_000.0)


@pytest.mark.asyncio
async def test_the_user_document_does_not_carry_a_second_balance():
    """Names the defect: one quantity, one place to read it."""
    async with api_client() as client:
        await _register(client)

    db = get_database()
    stored = await db.users.find_one({"username": "spender"})
    assert "cashBalance" not in stored, (
        "the balance belongs to the portfolio, which is what trading moves"
    )


@pytest.mark.asyncio
async def test_a_fresh_account_starts_with_the_advertised_amount():
    async with api_client() as client:
        registration = await _register(client)
        headers = {"Authorization": f"Bearer {registration['access_token']}"}
        me = await client.get("/auth/me", headers=headers)

    assert registration["user"]["cashBalance"] == pytest.approx(1_000_000.0)
    assert me.json()["cashBalance"] == pytest.approx(1_000_000.0)
