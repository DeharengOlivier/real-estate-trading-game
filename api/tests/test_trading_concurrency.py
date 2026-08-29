"""Money invariants under two requests that overlap.

An `if cash < total_cost` followed by a write is advisory: two requests both
read the balance, both pass the check, and the second write decides. The same
holds for `isAvailable`. These tests force exactly that interleaving instead of
hoping for it, because hoping for it produces a test that is green for the
wrong reason.

The rendezvous is placed on `get_current_quarter`, which both handlers await
after reading the portfolio and the listing and before writing anything. Two
requests that meet there have both read the old world, which is the state a
real MongoDB happily serves to two concurrent connections.

The invariants asserted here outlive any particular implementation:

- a player never spends money they do not have;
- a property is never owned by two players at once;
- a sale is never paid for twice.
"""

import asyncio
from datetime import datetime

import pytest

import api.routers.trading as trading
from api.database import get_database
from api.tests.conftest import Rendezvous, api_client


@pytest.fixture
def overlap_two_requests(monkeypatch):
    """Make two in-flight trades read the world before either one writes."""
    rendezvous = Rendezvous(party=2)
    real_get_current_quarter = trading.get_current_quarter

    async def blocking_get_current_quarter(db):
        quarter = await real_get_current_quarter(db)
        await rendezvous.wait()
        return quarter

    monkeypatch.setattr(trading, "get_current_quarter", blocking_get_current_quarter)
    return rendezvous


async def _create_listing(db, price):
    """Insert one property and its available listing, return the property id."""
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
async def test_two_overlapping_buys_cannot_spend_the_same_cash_twice(
    test_user_and_token, overlap_two_requests
):
    """Cash for one property, two requests: exactly one of them may succeed."""
    user, _, headers = test_user_and_token
    db = get_database()

    # 205,000 covers one purchase at 200,000 + 2.5% fees (205,000) and no more.
    await db.portfolios.update_one({"userId": user["user_id"]}, {"$set": {"cash": 205_000.0}})
    first = await _create_listing(db, 200_000.0)
    second = await _create_listing(db, 200_000.0)

    async with api_client() as client:
        responses = await asyncio.gather(
            client.post("/trading/buy", headers=headers, json={"propertyId": str(first)}),
            client.post("/trading/buy", headers=headers, json={"propertyId": str(second)}),
        )

    portfolio = await db.portfolios.find_one({"userId": user["user_id"]})
    holdings = await db.holdings.count_documents({"portfolioId": portfolio["_id"]})

    assert portfolio["cash"] >= 0, "the player spent money they did not have"
    assert holdings == 1, f"paid for one property, received {holdings}"
    assert sorted(r.status_code for r in responses) == [200, 400]


@pytest.mark.asyncio
async def test_the_losing_buyer_is_charged_nothing(test_user_and_token, overlap_two_requests):
    """A refused purchase must leave the balance exactly where it was."""
    user, _, headers = test_user_and_token
    db = get_database()

    await db.portfolios.update_one({"userId": user["user_id"]}, {"$set": {"cash": 205_000.0}})
    first = await _create_listing(db, 200_000.0)
    second = await _create_listing(db, 200_000.0)

    async with api_client() as client:
        await asyncio.gather(
            client.post("/trading/buy", headers=headers, json={"propertyId": str(first)}),
            client.post("/trading/buy", headers=headers, json={"propertyId": str(second)}),
        )

    portfolio = await db.portfolios.find_one({"userId": user["user_id"]})
    buy_trades = await db.trades.count_documents({"portfolioId": portfolio["_id"], "side": "buy"})

    # The balance alone would not catch the defect: two writes of an absolute
    # `cash - total_cost`, computed from the same stale read, also land on 0.
    # What separates one charge from two is how many purchases were recorded.
    assert buy_trades == 1, f"one affordable purchase, {buy_trades} recorded"
    assert portfolio["cash"] == pytest.approx(0.0), (
        "exactly one purchase of 205,000 should have been charged"
    )


@pytest.mark.asyncio
async def test_a_property_cannot_be_sold_to_two_players_at_once(
    test_user_and_token, ordinary_user_and_token, overlap_two_requests
):
    """Two buyers, one property: the listing is a resource, not a suggestion."""
    _, _, headers_a = test_user_and_token
    _, _, headers_b = ordinary_user_and_token
    db = get_database()

    property_id = await _create_listing(db, 200_000.0)

    async with api_client() as client:
        responses = await asyncio.gather(
            client.post("/trading/buy", headers=headers_a, json={"propertyId": str(property_id)}),
            client.post("/trading/buy", headers=headers_b, json={"propertyId": str(property_id)}),
        )

    owners = await db.holdings.count_documents({"propertyId": property_id})
    assert owners == 1, f"one property, {owners} owners"
    assert sorted(r.status_code for r in responses) == [200, 404]


@pytest.mark.asyncio
async def test_the_refused_buyer_of_a_taken_property_is_charged_nothing(
    test_user_and_token, ordinary_user_and_token, overlap_two_requests
):
    _, _, headers_a = test_user_and_token
    player, _, headers_b = ordinary_user_and_token
    db = get_database()

    property_id = await _create_listing(db, 200_000.0)
    before = (await db.portfolios.find_one({"userId": player["user_id"]}))["cash"]

    async with api_client() as client:
        responses = await asyncio.gather(
            client.post("/trading/buy", headers=headers_a, json={"propertyId": str(property_id)}),
            client.post("/trading/buy", headers=headers_b, json={"propertyId": str(property_id)}),
        )

    player_owns = await db.holdings.count_documents(
        {"portfolioId": (await db.portfolios.find_one({"userId": player["user_id"]}))["_id"]}
    )
    after = (await db.portfolios.find_one({"userId": player["user_id"]}))["cash"]

    # Whichever of the two lost, the loser paid nothing for nothing.
    if player_owns == 0:
        assert after == pytest.approx(before)
    assert sorted(r.status_code for r in responses) == [200, 404]


@pytest.mark.asyncio
async def test_the_same_holding_cannot_be_sold_twice(test_user_and_token, overlap_two_requests):
    """Two overlapping sales of one holding must credit the player once."""
    user, _, headers = test_user_and_token
    db = get_database()

    property_id = await _create_listing(db, 200_000.0)
    portfolio = await db.portfolios.find_one({"userId": user["user_id"]})
    await db.portfolios.update_one({"_id": portfolio["_id"]}, {"$set": {"cash": 0.0}})
    await db.listings.update_one({"propertyId": property_id}, {"$set": {"isAvailable": False}})
    await db.holdings.insert_one(
        {
            "portfolioId": portfolio["_id"],
            "propertyId": property_id,
            "buyPrice": 200_000.0,
            "buyDate": datetime(2020, 1, 1),
            "works": [],
        }
    )

    async with api_client() as client:
        responses = await asyncio.gather(
            client.post("/trading/sell", headers=headers, json={"propertyId": str(property_id)}),
            client.post("/trading/sell", headers=headers, json={"propertyId": str(property_id)}),
        )

    portfolio = await db.portfolios.find_one({"_id": portfolio["_id"]})
    sell_trades = await db.trades.count_documents({"portfolioId": portfolio["_id"], "side": "sell"})

    assert sell_trades == 1, f"one holding, {sell_trades} sales recorded"
    # One sale at 200,000 nets 195,000 after the 2.5% commission.
    assert portfolio["cash"] < 400_000, (
        f"the holding was paid for twice: cash is {portfolio['cash']}"
    )
    assert sorted(r.status_code for r in responses) == [200, 404]


@pytest.mark.asyncio
async def test_an_ordinary_purchase_still_works(test_user_and_token):
    """The guards must refuse the impossible without refusing the ordinary."""
    user, _, headers = test_user_and_token
    db = get_database()
    property_id = await _create_listing(db, 200_000.0)

    async with api_client() as client:
        response = await client.post(
            "/trading/buy", headers=headers, json={"propertyId": str(property_id)}
        )

    assert response.status_code == 200
    portfolio = await db.portfolios.find_one({"userId": user["user_id"]})
    assert portfolio["cash"] == pytest.approx(1_000_000.0 - 205_000.0)
    assert await db.holdings.count_documents({"propertyId": property_id}) == 1
    listing = await db.listings.find_one({"propertyId": property_id})
    assert listing["isAvailable"] is False


@pytest.mark.asyncio
async def test_a_purchase_beyond_the_balance_is_refused_and_charges_nothing(
    test_user_and_token,
):
    user, _, headers = test_user_and_token
    db = get_database()
    await db.portfolios.update_one({"userId": user["user_id"]}, {"$set": {"cash": 1_000.0}})
    property_id = await _create_listing(db, 200_000.0)

    async with api_client() as client:
        response = await client.post(
            "/trading/buy", headers=headers, json={"propertyId": str(property_id)}
        )

    assert response.status_code == 400
    portfolio = await db.portfolios.find_one({"userId": user["user_id"]})
    assert portfolio["cash"] == pytest.approx(1_000.0)
    listing = await db.listings.find_one({"propertyId": property_id})
    assert listing["isAvailable"] is True, (
        "a refused purchase must leave the property on the market"
    )
    # The claims taken on the way in are given back on the way out: no holding,
    # no trade, nothing for the portfolio page to show.
    assert await db.holdings.count_documents({"propertyId": property_id}) == 0
    assert await db.trades.count_documents({"propertyId": property_id}) == 0
