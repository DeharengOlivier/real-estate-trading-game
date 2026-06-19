"""
Tests for the trading router: listings filters/pagination, buy, and sell.
"""
import pytest
from httpx import AsyncClient
from bson import ObjectId
from datetime import datetime

from api.main import app
from api.database import get_database


async def _make_property_with_listing(db, *, zone, type_, surface, base_ppm,
                                       price, available=True, t="2020-1"):
    """Helper: create a property and an associated listing, return its id."""
    result = await db.properties.insert_one({
        "zone": zone,
        "type": type_,
        "surface": surface,
        "epc": 0.5,
        "state": 0.6,
        "kitchen": 0.6,
        "bath": 0.6,
        "base_ppm": base_ppm,
        "createdAt": datetime.utcnow(),
    })
    await db.listings.insert_one({
        "propertyId": result.inserted_id,
        "isAvailable": available,
        "lastComputedPrice": float(price),
        "lastT": t,
    })
    return result.inserted_id


# ==================== LISTINGS ====================

@pytest.mark.asyncio
async def test_listings_empty():
    """No available listings returns an empty paginated payload."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/trading/listings")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["totalPages"] == 0


@pytest.mark.asyncio
async def test_listings_filter_by_type():
    """Listings can be filtered by property type."""
    db = get_database()
    await _make_property_with_listing(db, zone="Ixelles", type_="apartment",
                                      surface=80, base_ppm=4500, price=360000)
    await _make_property_with_listing(db, zone="Ixelles", type_="house",
                                      surface=150, base_ppm=4800, price=720000)

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/trading/listings?type=house")
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["type"] == "house"


@pytest.mark.asyncio
async def test_listings_filter_by_price_range():
    """minPrice / maxPrice filter on the computed price."""
    db = get_database()
    await _make_property_with_listing(db, zone="Uccle", type_="apartment",
                                      surface=50, base_ppm=2000, price=100000)
    await _make_property_with_listing(db, zone="Uccle", type_="apartment",
                                      surface=80, base_ppm=4000, price=320000)
    await _make_property_with_listing(db, zone="Uccle", type_="apartment",
                                      surface=120, base_ppm=5000, price=600000)

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/trading/listings?minPrice=150000&maxPrice=400000")
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["price"] == 320000


@pytest.mark.asyncio
async def test_listings_pagination_and_sort():
    """Pagination metadata and descending sort by price."""
    db = get_database()
    prices = [100000, 200000, 300000, 400000, 500000]
    for i, price in enumerate(prices):
        await _make_property_with_listing(db, zone="Schaerbeek", type_="apartment",
                                          surface=60 + i, base_ppm=3000, price=price)

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/trading/listings?page=1&limit=2&sortBy=price&sortOrder=desc"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert data["totalPages"] == 3
        assert data["page"] == 1
        assert data["limit"] == 2
        assert len(data["items"]) == 2
        # Descending: highest first
        assert data["items"][0]["price"] == 500000
        assert data["items"][1]["price"] == 400000


@pytest.mark.asyncio
async def test_listings_enrichment_fields():
    """Listings are enriched with derived analytics fields."""
    db = get_database()
    await _make_property_with_listing(db, zone="Bruxelles-Centre", type_="apartment",
                                      surface=100, base_ppm=4200, price=420000)

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/trading/listings")
        item = response.json()["items"][0]
        # Price per m2 computed in Python
        assert item["pricePerM2"] == pytest.approx(4200.0)
        # Quality and trend fields present
        for field in ("qualityScore", "epcScore", "zoneTrend",
                      "estimated1YearPrice", "estimated1YearGain"):
            assert field in item


@pytest.mark.asyncio
async def test_listings_unavailable_excluded():
    """Listings flagged unavailable are not returned."""
    db = get_database()
    await _make_property_with_listing(db, zone="Namur-Centre", type_="house",
                                      surface=100, base_ppm=2900, price=290000,
                                      available=False)

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/trading/listings?zone=Namur-Centre")
        assert response.json()["total"] == 0


# ==================== BUY ====================

@pytest.mark.asyncio
async def test_buy_requires_auth():
    """Buying without a token is rejected."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/trading/buy", json={"propertyId": str(ObjectId())})
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_buy_insufficient_funds(test_user_and_token):
    """Buying a property more expensive than available cash fails with 400."""
    user_data, token, headers = test_user_and_token
    db = get_database()

    # Listing priced well above the 1,000,000 starting cash
    prop_id = await _make_property_with_listing(
        db, zone="Uccle", type_="house", surface=400, base_ppm=5200, price=2000000
    )

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/trading/buy", headers=headers, json={"propertyId": str(prop_id)}
        )
        assert response.status_code == 400
        assert "insufficient" in response.json()["detail"].lower()

    # Cash unchanged
    portfolio = await db.portfolios.find_one({"userId": user_data["user_id"]})
    assert portfolio["cash"] == 1000000.0


@pytest.mark.asyncio
async def test_buy_unavailable_property(test_user_and_token):
    """Buying a property with no available listing returns 404."""
    user_data, token, headers = test_user_and_token

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/trading/buy", headers=headers, json={"propertyId": str(ObjectId())}
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_buy_marks_listing_unavailable(test_user_and_token):
    """A successful buy marks the listing unavailable and charges fees."""
    user_data, token, headers = test_user_and_token
    db = get_database()

    price = 300000
    prop_id = await _make_property_with_listing(
        db, zone="Ixelles", type_="apartment", surface=80, base_ppm=4000, price=price
    )

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/trading/buy", headers=headers, json={"propertyId": str(prop_id)}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["fees"] == pytest.approx(price * 0.025)
        assert data["totalCost"] == pytest.approx(price * 1.025)

    listing = await db.listings.find_one({"propertyId": prop_id})
    assert listing["isAvailable"] is False


# ==================== SELL ====================

@pytest.mark.asyncio
async def test_sell_property_not_in_portfolio(test_user_and_token):
    """Selling a property not held returns 404."""
    user_data, token, headers = test_user_and_token

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/trading/sell", headers=headers, json={"propertyId": str(ObjectId())}
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_sell_blocked_by_ongoing_renovation(test_user_and_token):
    """A holding with an ongoing renovation cannot be sold."""
    user_data, token, headers = test_user_and_token
    db = get_database()

    prop_id = await _make_property_with_listing(
        db, zone="Gand-Centre", type_="house", surface=120, base_ppm=3500, price=420000
    )
    portfolio = await db.portfolios.find_one({"userId": user_data["user_id"]})
    await db.holdings.insert_one({
        "portfolioId": portfolio["_id"],
        "propertyId": prop_id,
        "buyPrice": 420000,
        "buyDate": datetime.utcnow(),
        "works": [{"renoId": ObjectId(), "startT": "2020-1",
                   "endT": "2020-3", "status": "ongoing"}],
    })
    await db.pricehistory.insert_one(
        {"propertyId": prop_id, "t": "2020-1", "price": 450000}
    )

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/trading/sell", headers=headers, json={"propertyId": str(prop_id)}
        )
        assert response.status_code == 400
        assert "ongoing" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_sell_computes_pnl_and_credits_cash(test_user_and_token):
    """Selling credits net proceeds and reports P&L."""
    user_data, token, headers = test_user_and_token
    db = get_database()

    buy_price = 400000
    current_price = 460000
    prop_id = await _make_property_with_listing(
        db, zone="Ixelles", type_="house", surface=150, base_ppm=4800,
        price=current_price, available=False
    )
    portfolio = await db.portfolios.find_one({"userId": user_data["user_id"]})
    initial_cash = portfolio["cash"]
    await db.holdings.insert_one({
        "portfolioId": portfolio["_id"],
        "propertyId": prop_id,
        "buyPrice": buy_price,
        "buyDate": datetime.utcnow(),
        "works": [],
    })
    await db.pricehistory.insert_one(
        {"propertyId": prop_id, "t": "2020-1", "price": current_price}
    )

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/trading/sell", headers=headers, json={"propertyId": str(prop_id)}
        )
        assert response.status_code == 200
        data = response.json()
        expected_fees = current_price * 0.025
        expected_net = current_price - expected_fees
        assert data["netProceeds"] == pytest.approx(expected_net)
        assert data["pnl"] == pytest.approx(expected_net - buy_price)

    # Holding removed, listing back to available, cash credited.
    assert await db.holdings.find_one({"propertyId": prop_id}) is None
    listing = await db.listings.find_one({"propertyId": prop_id})
    assert listing["isAvailable"] is True
    portfolio = await db.portfolios.find_one({"userId": user_data["user_id"]})
    assert portfolio["cash"] == pytest.approx(initial_cash + expected_net)
