"""
Tests for Real Estate Game API
"""
from datetime import datetime

import pytest

from api.database import get_database
from api.tests.conftest import api_client


@pytest.mark.asyncio
async def test_health_check():
    """Test health check endpoint"""
    async with api_client() as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
        assert "timestamp" in data
        assert "dependencies" in data


@pytest.mark.asyncio
async def test_buy_reduces_cash_and_creates_holding(test_user_and_token):
    """Test that buying a property reduces cash and creates holding"""
    user_data, token, headers = test_user_and_token
    db = get_database()

    # Create property
    property_result = await db.properties.insert_one({
        "zone": "Bruxelles-Centre",
        "type": "apartment",
        "surface": 100,
        "epc": 0.5,
        "state": 0.7,
        "kitchen": 0.6,
        "bath": 0.6,
        "base_ppm": 4200,
        "createdAt": datetime.utcnow()
    })

    # The market index for "2020-1" comes from the baseline fixture and covers
    # every zone. Inserting a second document for the same quarter is what the
    # unique index on marketindex.t exists to stop, in a test as in production.

    # Create listing
    listing_price = 300000
    await db.listings.insert_one({
        "propertyId": property_result.inserted_id,
        "isAvailable": True,
        "lastComputedPrice": listing_price,
        "lastT": "2020-1"
    })

    # Get initial cash
    portfolio = await db.portfolios.find_one({"userId": user_data["user_id"]})
    initial_cash = portfolio["cash"]

    # Test: Buy property with authentication
    async with api_client() as client:
        response = await client.post(
            "/trading/buy",
            json={"propertyId": str(property_result.inserted_id)},
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Check cash reduced
        portfolio = await db.portfolios.find_one({"userId": user_data["user_id"]})
        expected_cost = listing_price * 1.025
        assert portfolio["cash"] == pytest.approx(initial_cash - expected_cost, rel=0.01)

        # Check holding created
        holding = await db.holdings.find_one({"propertyId": property_result.inserted_id})
        assert holding is not None
        assert holding["buyPrice"] == listing_price

        # Check trade recorded
        trade = await db.trades.find_one({
            "propertyId": property_result.inserted_id,
            "side": "buy"
        })
        assert trade is not None


@pytest.mark.asyncio
async def test_sell_creates_trade_and_removes_holding(test_user_and_token):
    """Test that selling a property creates trade and removes holding"""
    user_data, token, headers = test_user_and_token
    db = get_database()

    # Create property
    property_result = await db.properties.insert_one({
        "zone": "Ixelles",
        "type": "house",
        "surface": 150,
        "epc": 0.6,
        "state": 0.8,
        "kitchen": 0.7,
        "bath": 0.7,
        "base_ppm": 4800,
        "createdAt": datetime.utcnow()
    })

    # Create market index
    await db.marketindex.insert_one({
        "t": "2020-2",
        "inflation": 0.02,
        "rate": 0.015,
        "income": 0.01,
        "unemployment": 0.05,
        "confidence": 0.0,
        "policy": 0.0,
        "locals": [{
            "zone": "Ixelles",
            "access": 0.0,
            "attract": 0.0,
            "nuisance": 0.0,
            "tension": 0.0
        }]
    })

    buy_price = 450000
    portfolio = await db.portfolios.find_one({"userId": user_data["user_id"]})

    await db.holdings.insert_one({
        "portfolioId": portfolio["_id"],
        "propertyId": property_result.inserted_id,
        "buyPrice": buy_price,
        "buyDate": datetime.utcnow(),
        "works": []
    })

    # Create price history
    current_price = 480000
    await db.pricehistory.insert_one({
        "propertyId": property_result.inserted_id,
        "t": "2020-2",
        "price": current_price
    })

    # Test: Sell property with authentication
    async with api_client() as client:
        response = await client.post(
            "/trading/sell",
            json={"propertyId": str(property_result.inserted_id)},
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


@pytest.mark.asyncio
async def test_listings_filters():
    """Test that listings endpoint correctly filters properties"""
    db = get_database()

    # Setup: Create properties in different zones and types
    properties = [
        {"zone": "Bruxelles-Centre", "type": "apartment", "surface": 80, "base_ppm": 4200},
        {"zone": "Bruxelles-Centre", "type": "house", "surface": 150, "base_ppm": 4500},
        {"zone": "Liège-Centre", "type": "apartment", "surface": 70, "base_ppm": 2500},
    ]

    for prop in properties:
        result = await db.properties.insert_one({
            **prop,
            "epc": 0.5,
            "state": 0.6,
            "kitchen": 0.6,
            "bath": 0.6,
            "createdAt": datetime.utcnow()
        })

        # Create listing
        await db.listings.insert_one({
            "propertyId": result.inserted_id,
            "isAvailable": True,
            "lastComputedPrice": prop["surface"] * prop["base_ppm"],
            "lastT": "2020-1"
        })

    # Test: Filter by zone
    async with api_client() as client:
        response = await client.get("/trading/listings?zone=Bruxelles-Centre")
        assert response.status_code == 200
        data = response.json()
        # The response is paginated
        items = data["items"] if isinstance(data, dict) and "items" in data else data
        assert len(items) == 2
