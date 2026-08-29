"""Advancing the quarter must not cost one round trip per property.

The handler loaded every holding and every property in the database with no
filter, then issued a separate update_one per property to write the new price.
On the seeded data set that is 300 single-document writes for one click, and it
grows with the catalog.

The correctness of the advance is covered in test_game.py. What is fixed here
is its cost, stated as a bound rather than discovered in production.
"""
from datetime import datetime

import pytest
from httpx import AsyncClient

import api.routers.game as game_router
from api.database import get_database
from api.main import app
from api.tests.conftest import CountingDatabase

PROPERTIES = 40


@pytest.fixture
def counted_queries(monkeypatch):
    counter = CountingDatabase(get_database())
    monkeypatch.setattr(game_router, "get_database", lambda: counter)
    return counter


async def _fill_market(db, count=PROPERTIES):
    for index in range(count):
        prop = await db.properties.insert_one({
            "zone": "Bruxelles-Centre", "type": "house", "surface": 100 + index,
            "epc": 0.6, "state": 0.7, "kitchen": 0.6, "bath": 0.6,
            "base_ppm": 3000,
        })
        await db.listings.insert_one({
            "propertyId": prop.inserted_id, "isAvailable": True,
            "lastComputedPrice": 300_000.0, "lastT": "2020-1",
        })


@pytest.mark.asyncio
async def test_advancing_a_quarter_is_flat_in_the_number_of_properties(
    test_user_and_token, counted_queries
):
    _, _, headers = test_user_and_token
    db = get_database()
    await _fill_market(db)

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/game/advance-quarter", headers=headers)

    assert response.status_code == 200, response.text
    assert counted_queries.count() <= 12, (
        f"{counted_queries.count()} round trips for {PROPERTIES} properties: "
        f"{counted_queries.calls}"
    )


@pytest.mark.asyncio
async def test_no_single_document_write_per_listing(
    test_user_and_token, counted_queries
):
    _, _, headers = test_user_and_token
    db = get_database()
    await _fill_market(db)

    async with AsyncClient(app=app, base_url="http://test") as client:
        await client.post("/game/advance-quarter", headers=headers)

    assert counted_queries.count("listings.update_one") <= 1, (
        "one write per property is the shape that made this grow with the "
        "catalog"
    )


@pytest.mark.asyncio
async def test_the_bound_holds_when_the_catalog_doubles(
    test_user_and_token, counted_queries
):
    _, _, headers = test_user_and_token
    db = get_database()
    await _fill_market(db, count=PROPERTIES * 2)

    async with AsyncClient(app=app, base_url="http://test") as client:
        await client.post("/game/advance-quarter", headers=headers)

    assert counted_queries.count() <= 12, (
        f"{counted_queries.count()} round trips for {PROPERTIES * 2} properties"
    )


@pytest.mark.asyncio
async def test_every_price_is_still_written(test_user_and_token):
    """A cheaper advance that skips properties is not a cheaper advance."""
    db = get_database()
    await _fill_market(db, count=10)
    _, _, headers = test_user_and_token

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/game/advance-quarter", headers=headers)

    next_quarter = response.json()["quarter"]
    assert response.json()["propertiesUpdated"] == 10
    assert await db.pricehistory.count_documents({"t": next_quarter}) == 10

    listings = await db.listings.find({}).to_list(length=None)
    assert all(listing["lastT"] == next_quarter for listing in listings)
    assert all(listing["lastComputedPrice"] > 0 for listing in listings)


@pytest.mark.asyncio
async def test_a_completed_renovation_is_still_applied(test_user_and_token):
    """The loop that applies finished works must survive the batching."""
    user, _, headers = test_user_and_token
    db = get_database()

    renovation = await db.renovations.find_one({})
    prop = await db.properties.insert_one({
        "zone": "Bruxelles-Centre", "type": "house", "surface": 100,
        "epc": 0.3, "state": 0.3, "kitchen": 0.3, "bath": 0.3, "base_ppm": 3000,
    })
    await db.listings.insert_one({
        "propertyId": prop.inserted_id, "isAvailable": False,
        "lastComputedPrice": 300_000.0, "lastT": "2020-1",
    })
    portfolio = await db.portfolios.find_one({"userId": user["user_id"]})
    await db.holdings.insert_one({
        "portfolioId": portfolio["_id"],
        "propertyId": prop.inserted_id,
        "buyPrice": 250_000.0,
        "buyDate": datetime(2020, 1, 1),
        "works": [{
            "renoId": renovation["_id"],
            "startT": "2020-1", "endT": "2020-2", "status": "ongoing",
        }],
    })
    before = await db.properties.find_one({"_id": prop.inserted_id})

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/game/advance-quarter", headers=headers)

    assert response.json()["renovationsCompleted"] == 1
    after = await db.properties.find_one({"_id": prop.inserted_id})
    assert (after["epc"], after["state"], after["kitchen"], after["bath"]) != (
        before["epc"], before["state"], before["kitchen"], before["bath"]
    )

    holding = await db.holdings.find_one({"propertyId": prop.inserted_id})
    assert holding["works"][0]["status"] == "completed"
