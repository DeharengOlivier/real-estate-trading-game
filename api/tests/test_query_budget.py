"""How many round trips a page costs, stated rather than discovered.

Both portfolio endpoints read one document per holding, and one more per
renovation work inside that holding, so the cost of rendering a portfolio grew
with the portfolio. These tests fix a bound that does not depend on how much a
player owns; a loop that reads per item breaks them immediately.

Measured with 24 holdings of 3 completed works each:

    /portfolio/summary    102 round trips -> 5
    /portfolio/holdings   124 round trips -> 7

The remaining calls are the portfolio, the current quarter, the holdings, the
trades, and the batched reads of properties, prices and renovations.
"""
from datetime import datetime

import pytest

import api.routers.portfolio as portfolio_router
from api.database import get_database
from api.tests.conftest import CountingDatabase, api_client

HOLDINGS = 12
WORKS_PER_HOLDING = 3


@pytest.fixture
def counted_queries(monkeypatch):
    """Count every collection call the portfolio router makes."""
    counter = CountingDatabase(get_database())
    monkeypatch.setattr(portfolio_router, "get_database", lambda: counter)
    return counter


async def _fill_portfolio(db, user_id, holdings=HOLDINGS, works=WORKS_PER_HOLDING):
    """Give the player `holdings` properties, each with `works` renovations."""
    portfolio = await db.portfolios.find_one({"userId": user_id})
    renovations = await db.renovations.find().to_list(length=None)

    for index in range(holdings):
        prop = await db.properties.insert_one({
            "zone": "Bruxelles-Centre", "type": "house", "surface": 100 + index,
            "epc": 0.6, "state": 0.7, "kitchen": 0.6, "bath": 0.6,
            "base_ppm": 3000,
        })
        await db.pricehistory.insert_one({
            "propertyId": prop.inserted_id, "t": "2020-1", "price": 300_000.0,
        })
        await db.holdings.insert_one({
            "portfolioId": portfolio["_id"],
            "propertyId": prop.inserted_id,
            "buyPrice": 250_000.0,
            "buyDate": datetime(2020, 1, 1),
            "works": [
                {
                    "renoId": renovations[work % len(renovations)]["_id"],
                    "startT": "2020-1", "endT": "2020-2", "status": "completed",
                }
                for work in range(works)
            ],
        })
        await db.trades.insert_one({
            "portfolioId": portfolio["_id"],
            "propertyId": prop.inserted_id,
            "side": "buy", "price": 250_000.0, "fees": 6_250.0,
            "ts": datetime(2020, 1, 1), "quarter": "2020-1",
        })
    return portfolio


@pytest.mark.asyncio
async def test_the_summary_costs_the_same_whatever_the_portfolio_holds(
    test_user_and_token, counted_queries
):
    user, _, headers = test_user_and_token
    db = get_database()
    await _fill_portfolio(db, user["user_id"])

    async with api_client() as client:
        response = await client.get("/portfolio/summary", headers=headers)

    assert response.status_code == 200, response.text
    assert counted_queries.count() <= 8, (
        f"{counted_queries.count()} round trips for {HOLDINGS} holdings: "
        f"{counted_queries.calls}"
    )


@pytest.mark.asyncio
async def test_the_summary_reads_no_document_per_renovation_work(
    test_user_and_token, counted_queries
):
    user, _, headers = test_user_and_token
    db = get_database()
    await _fill_portfolio(db, user["user_id"])

    async with api_client() as client:
        await client.get("/portfolio/summary", headers=headers)

    assert counted_queries.count("renovations.find_one") == 0, (
        "one lookup per work is the shape that made this page grow with the "
        "portfolio"
    )


@pytest.mark.asyncio
async def test_the_holdings_page_costs_the_same_whatever_it_lists(
    test_user_and_token, counted_queries
):
    user, _, headers = test_user_and_token
    db = get_database()
    await _fill_portfolio(db, user["user_id"])

    async with api_client() as client:
        response = await client.get("/portfolio/holdings", headers=headers)

    assert response.status_code == 200, response.text
    assert counted_queries.count() <= 8, (
        f"{counted_queries.count()} round trips for {HOLDINGS} holdings: "
        f"{counted_queries.calls}"
    )


@pytest.mark.asyncio
async def test_the_bound_holds_when_the_portfolio_doubles(
    test_user_and_token, counted_queries
):
    """A bound that only holds at one size is a coincidence, not a bound."""
    user, _, headers = test_user_and_token
    db = get_database()
    await _fill_portfolio(db, user["user_id"], holdings=HOLDINGS * 2)

    async with api_client() as client:
        await client.get("/portfolio/summary", headers=headers)
        first = counted_queries.count()
        counted_queries.calls.clear()
        await client.get("/portfolio/holdings", headers=headers)
        second = counted_queries.count()

    assert first <= 8 and second <= 8, f"{first} and {second} round trips"
