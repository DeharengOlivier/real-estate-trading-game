"""
Tests for the game router: renovation catalog, starting renovations,
advancing quarters, and current-quarter reporting.
"""

import pytest
from bson import ObjectId

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
async def test_renovation_catalog_public():
    """The renovation catalog is public and seeded."""
    async with api_client() as client:
        response = await client.get("/game/renovations")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        codes = {r["code"] for r in data}
        assert "KITCHEN" in codes


@pytest.mark.asyncio
async def test_current_quarter_endpoint():
    async with api_client() as client:
        response = await client.get("/game/current-quarter")
        assert response.status_code == 200
        assert response.json()["quarter"] == "2020-1"


@pytest.mark.asyncio
async def test_renovate_requires_auth():
    async with api_client() as client:
        response = await client.post(
            "/game/renovate", json={"holdingId": str(ObjectId()), "renoCode": "KITCHEN"}
        )
        # No Authorization header at all: 401. FastAPI's HTTPBearer used to
        # answer 403 here, which said "you may not" to a caller who had not
        # yet said who they were. 401 is the answer to a missing credential;
        # 403 is what an identified caller without the role gets.
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_renovate_holding_not_found(test_user_and_token):
    user_data, token, headers = test_user_and_token
    async with api_client() as client:
        response = await client.post(
            "/game/renovate",
            headers=headers,
            json={"holdingId": str(ObjectId()), "renoCode": "KITCHEN"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_renovate_unknown_code(test_user_and_token):
    user_data, token, headers = test_user_and_token
    db = get_database()
    prop_id = await _add_property(db)
    portfolio = await db.portfolios.find_one({"userId": user_data["user_id"]})
    holding = await db.holdings.insert_one(
        {
            "portfolioId": portfolio["_id"],
            "propertyId": prop_id,
            "buyPrice": 300000,
            "buyDate": utc_now(),
            "works": [],
        }
    )
    async with api_client() as client:
        response = await client.post(
            "/game/renovate",
            headers=headers,
            json={"holdingId": str(holding.inserted_id), "renoCode": "NOPE"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_renovate_insufficient_funds(test_user_and_token):
    user_data, token, headers = test_user_and_token
    db = get_database()
    prop_id = await _add_property(db)
    portfolio = await db.portfolios.find_one({"userId": user_data["user_id"]})
    await db.portfolios.update_one({"_id": portfolio["_id"]}, {"$set": {"cash": 100.0}})
    holding = await db.holdings.insert_one(
        {
            "portfolioId": portfolio["_id"],
            "propertyId": prop_id,
            "buyPrice": 300000,
            "buyDate": utc_now(),
            "works": [],
        }
    )
    async with api_client() as client:
        response = await client.post(
            "/game/renovate",
            headers=headers,
            json={"holdingId": str(holding.inserted_id), "renoCode": "KITCHEN"},
        )
        assert response.status_code == 400
        assert "insufficient" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_renovate_success_deducts_cash_and_adds_work(test_user_and_token):
    user_data, token, headers = test_user_and_token
    db = get_database()
    prop_id = await _add_property(db)
    portfolio = await db.portfolios.find_one({"userId": user_data["user_id"]})
    holding = await db.holdings.insert_one(
        {
            "portfolioId": portfolio["_id"],
            "propertyId": prop_id,
            "buyPrice": 300000,
            "buyDate": utc_now(),
            "works": [],
        }
    )
    reno = await db.renovations.find_one({"code": "KITCHEN"})

    async with api_client() as client:
        response = await client.post(
            "/game/renovate",
            headers=headers,
            json={"holdingId": str(holding.inserted_id), "renoCode": "KITCHEN"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["cost"] == reno["cost"]

    updated = await db.holdings.find_one({"_id": holding.inserted_id})
    assert len(updated["works"]) == 1
    assert updated["works"][0]["status"] == "ongoing"
    portfolio = await db.portfolios.find_one({"_id": portfolio["_id"]})
    assert portfolio["cash"] == pytest.approx(1000000.0 - reno["cost"])


@pytest.mark.asyncio
async def test_advance_quarter_completes_renovation_and_updates_prices(test_user_and_token):
    """Advancing a quarter generates market data, completes due renovations
    and recomputes prices/listings."""
    user_data, token, headers = test_user_and_token
    db = get_database()

    prop_id = await _add_property(db, zone="Bruxelles-Centre", surface=100, base_ppm=4200)
    await db.listings.insert_one(
        {
            "propertyId": prop_id,
            "isAvailable": False,
            "lastComputedPrice": 420000,
            "lastT": "2020-1",
        }
    )
    portfolio = await db.portfolios.find_one({"userId": user_data["user_id"]})
    reno = await db.renovations.find_one({"code": "HEATING"})  # durationQ = 1
    await db.holdings.insert_one(
        {
            "portfolioId": portfolio["_id"],
            "propertyId": prop_id,
            "buyPrice": 400000,
            "buyDate": utc_now(),
            "works": [
                {"renoId": reno["_id"], "startT": "2020-1", "endT": "2020-2", "status": "ongoing"}
            ],
        }
    )
    epc_before = (await db.properties.find_one({"_id": prop_id}))["epc"]

    async with api_client() as client:
        response = await client.post("/game/advance-quarter", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["previousQuarter"] == "2020-1"
        assert data["quarter"] == "2020-2"
        assert data["renovationsCompleted"] == 1
        assert data["propertiesUpdated"] >= 1

    # Renovation applied: EPC increased and work marked completed.
    prop_after = await db.properties.find_one({"_id": prop_id})
    assert prop_after["epc"] > epc_before
    holding_after = await db.holdings.find_one({"propertyId": prop_id})
    assert holding_after["works"][0]["status"] == "completed"
    # A price history record now exists for the new quarter.
    assert await db.pricehistory.find_one({"propertyId": prop_id, "t": "2020-2"})
