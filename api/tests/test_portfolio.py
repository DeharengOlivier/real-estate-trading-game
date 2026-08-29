"""
Tests for the portfolio router: summary, P&L computation, and holdings detail.
"""

from datetime import datetime

import pytest

from api.clock import utc_now
from api.database import get_database
from api.tests.conftest import api_client


async def _add_property(db, *, zone="Ixelles", type_="apartment", surface=80, base_ppm=4000):
    result = await db.properties.insert_one(
        {
            "zone": zone,
            "type": type_,
            "surface": surface,
            "epc": 0.5,
            "state": 0.6,
            "kitchen": 0.6,
            "bath": 0.6,
            "base_ppm": base_ppm,
            "createdAt": utc_now(),
        }
    )
    return result.inserted_id


@pytest.mark.asyncio
async def test_summary_requires_auth():
    async with api_client() as client:
        response = await client.get("/portfolio/summary")
        # No Authorization header at all: 401. FastAPI's HTTPBearer used to
        # answer 403 here, which said "you may not" to a caller who had not
        # yet said who they were. 401 is the answer to a missing credential;
        # 403 is what an identified caller without the role gets.
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_summary_empty_portfolio(test_user_and_token):
    """A fresh portfolio has all cash, no equity and zero P&L."""
    user_data, token, headers = test_user_and_token

    async with api_client() as client:
        response = await client.get("/portfolio/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["cash"] == 1000000.0
        assert data["equity"] == 0.0
        assert data["totalValue"] == 1000000.0
        assert data["pnlTotal"] == 0.0


@pytest.mark.asyncio
async def test_summary_unrealized_gain(test_user_and_token):
    """Holding a property that appreciated yields positive equity and P&L."""
    user_data, token, headers = test_user_and_token
    db = get_database()

    prop_id = await _add_property(db)
    portfolio = await db.portfolios.find_one({"userId": user_data["user_id"]})
    buy_price = 300000
    current_price = 350000
    # Cash was reduced by buy price + fees when the property was acquired.
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
    await db.pricehistory.insert_one({"propertyId": prop_id, "t": "2020-1", "price": current_price})

    async with api_client() as client:
        response = await client.get("/portfolio/summary", headers=headers)
        data = response.json()

    assert data["equity"] == pytest.approx(current_price)
    # Total value = remaining cash + current equity.
    expected_total = (1000000.0 - buy_price - fees) + current_price
    assert data["totalValue"] == pytest.approx(expected_total)
    # Total P&L = appreciation - purchase fees.
    assert data["pnlTotal"] == pytest.approx((current_price - buy_price) - fees)


@pytest.mark.asyncio
async def test_holdings_empty(test_user_and_token):
    user_data, token, headers = test_user_and_token
    async with api_client() as client:
        response = await client.get("/portfolio/holdings", headers=headers)
        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.asyncio
async def test_holdings_detail_includes_costs_and_pnl(test_user_and_token):
    """Holdings detail reflects buy price, fees, renovation cost and P&L."""
    user_data, token, headers = test_user_and_token
    db = get_database()

    prop_id = await _add_property(db, zone="Bruxelles-Centre", surface=100, base_ppm=4200)
    portfolio = await db.portfolios.find_one({"userId": user_data["user_id"]})

    buy_price = 400000
    buy_fees = buy_price * 0.025
    reno = await db.renovations.find_one({"code": "KITCHEN"})
    current_price = 500000

    await db.holdings.insert_one(
        {
            "portfolioId": portfolio["_id"],
            "propertyId": prop_id,
            "buyPrice": buy_price,
            "buyDate": datetime(2020, 1, 1),
            "works": [
                {"renoId": reno["_id"], "startT": "2020-1", "endT": "2020-3", "status": "completed"}
            ],
        }
    )
    await db.trades.insert_one(
        {
            "portfolioId": portfolio["_id"],
            "propertyId": prop_id,
            "side": "buy",
            "price": buy_price,
            "fees": buy_fees,
            "ts": datetime(2020, 1, 1),
            "quarter": "2020-1",
        }
    )
    await db.pricehistory.insert_one({"propertyId": prop_id, "t": "2020-1", "price": current_price})

    async with api_client() as client:
        response = await client.get("/portfolio/holdings", headers=headers)
        assert response.status_code == 200
        holdings = response.json()
        assert len(holdings) == 1
        h = holdings[0]
        assert h["propertyId"] == str(prop_id)
        assert h["buyPrice"] == pytest.approx(buy_price)
        assert h["buyFees"] == pytest.approx(buy_fees)
        assert h["renovationCosts"] == pytest.approx(reno["cost"])
        expected_invested = buy_price + buy_fees + reno["cost"]
        assert h["totalInvested"] == pytest.approx(expected_invested)
        assert h["pnl"] == pytest.approx(current_price - expected_invested)
        assert h["ongoingWorks"] == 0
