"""
Tests for the charts router: portfolio equity series and property price history.
"""

from datetime import datetime

import pytest
from bson import ObjectId

from api.database import get_database
from api.tests.conftest import api_client


@pytest.mark.asyncio
async def test_portfolio_equity_requires_auth():
    async with api_client() as client:
        response = await client.get("/charts/portfolio-equity")
        # No Authorization header at all: 401. FastAPI's HTTPBearer used to
        # answer 403 here, which said "you may not" to a caller who had not
        # yet said who they were. 401 is the answer to a missing credential;
        # 403 is what an identified caller without the role gets.
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_portfolio_equity_no_trades_snapshot(test_user_and_token):
    """With no trades, the endpoint returns a single current snapshot."""
    user_data, token, headers = test_user_and_token

    async with api_client() as client:
        response = await client.get("/charts/portfolio-equity", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["quarter"] == "2020-1"
        assert data[0]["cash"] == pytest.approx(1000000.0)
        assert data[0]["equity"] == 0.0


@pytest.mark.asyncio
async def test_portfolio_equity_with_trades(test_user_and_token):
    """A buy trade is reflected in the reconstructed equity time series."""
    user_data, token, headers = test_user_and_token
    db = get_database()

    prop_result = await db.properties.insert_one(
        {
            "zone": "Ixelles",
            "type": "apartment",
            "surface": 80,
            "epc": 0.5,
            "state": 0.6,
            "kitchen": 0.6,
            "bath": 0.6,
            "base_ppm": 4000,
            "createdAt": datetime.utcnow(),
        }
    )
    prop_id = prop_result.inserted_id
    portfolio = await db.portfolios.find_one({"userId": user_data["user_id"]})

    buy_price = 300000
    fees = buy_price * 0.025
    await db.portfolios.update_one(
        {"_id": portfolio["_id"]}, {"$set": {"cash": 1000000.0 - buy_price - fees}}
    )
    await db.holdings.insert_one(
        {
            "portfolioId": portfolio["_id"],
            "propertyId": prop_id,
            "buyPrice": buy_price,
            "buyDate": datetime(2020, 1, 1),
            "works": [],
        }
    )
    await db.trades.insert_one(
        {
            "portfolioId": portfolio["_id"],
            "propertyId": prop_id,
            "side": "buy",
            "price": buy_price,
            "fees": fees,
            "ts": datetime(2020, 1, 1),
            "quarter": "2020-1",
        }
    )
    await db.pricehistory.insert_one({"propertyId": prop_id, "t": "2020-1", "price": buy_price})

    async with api_client() as client:
        response = await client.get("/charts/portfolio-equity", headers=headers)
        assert response.status_code == 200
        series = response.json()
        assert len(series) >= 1
        # Final point should include the held property's value as equity.
        last = series[-1]
        assert last["equity"] == pytest.approx(buy_price)


@pytest.mark.asyncio
async def test_property_price_chart_invalid_id(test_user_and_token):
    user_data, token, headers = test_user_and_token
    async with api_client() as client:
        response = await client.get("/charts/property/not-an-objectid", headers=headers)
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_property_price_chart_not_found(test_user_and_token):
    user_data, token, headers = test_user_and_token
    async with api_client() as client:
        response = await client.get(f"/charts/property/{ObjectId()}", headers=headers)
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_property_price_chart_series(test_user_and_token):
    """Price history is returned as parallel quarter/price arrays."""
    user_data, token, headers = test_user_and_token
    db = get_database()

    prop_result = await db.properties.insert_one(
        {
            "zone": "Gand-Centre",
            "type": "house",
            "surface": 120,
            "epc": 0.5,
            "state": 0.6,
            "kitchen": 0.6,
            "bath": 0.6,
            "base_ppm": 3500,
            "createdAt": datetime.utcnow(),
        }
    )
    prop_id = prop_result.inserted_id
    await db.pricehistory.insert_many(
        [
            {"propertyId": prop_id, "t": "2020-1", "price": 420000},
            {"propertyId": prop_id, "t": "2020-2", "price": 430000},
        ]
    )

    async with api_client() as client:
        response = await client.get(f"/charts/property/{prop_id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["zone"] == "Gand-Centre"
        assert data["quarters"] == ["2020-1", "2020-2"]
        assert data["prices"] == [420000, 430000]
