"""
Game router - Game mechanics (renovations, time advancement)
Single Responsibility: Game progression and renovation management
"""

import logging

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pymongo import UpdateOne

from api.auth import get_current_user, require_admin
from api.database import get_database
from api.models import RenovateRequest
from api.services import (
    add_quarters,
    apply_renovation_delta,
    compute_property_price,
    generate_next_market_quarter,
    get_current_quarter,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/game", tags=["Game"])


@router.get("/renovations")
async def get_renovations():
    """Get catalog of available renovation types"""
    db = get_database()

    renovations = await db.renovations.find().to_list(length=None)

    results = []
    for reno in renovations:
        results.append(
            {
                "code": reno["code"],
                "label": reno["label"],
                "cost": reno["cost"],
                "durationQ": reno["durationQ"],
                "delta": reno["delta"],
            }
        )

    return results


@router.post("/renovate")
async def start_renovation(
    request: RenovateRequest, current_user: dict = Depends(get_current_user)
):
    """
    Start a renovation on a holding

    - Deducts cost from cash
    - Adds renovation work to holding with status 'ongoing'
    - Work will be completed when advancing to endT quarter
    """
    db = get_database()

    holding_id = ObjectId(request.holdingId)

    # Get holding
    holding = await db.holdings.find_one({"_id": holding_id})
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")

    # Verify holding belongs to user's portfolio
    portfolio = await db.portfolios.find_one(
        {"_id": holding["portfolioId"], "userId": current_user["_id"]}
    )
    if not portfolio:
        raise HTTPException(status_code=403, detail="Not authorized to renovate this property")

    # Get renovation
    renovation = await db.renovations.find_one({"code": request.renoCode})
    if not renovation:
        raise HTTPException(status_code=404, detail="Renovation not found")

    cost = renovation["cost"]
    cash = portfolio["cash"]

    # Check sufficient cash
    if cash < cost:
        raise HTTPException(
            status_code=400, detail=f"Insufficient funds. Need {cost:,.2f} €, have {cash:,.2f} €"
        )

    # Get current quarter
    current_t = await get_current_quarter(db)
    duration = renovation["durationQ"]
    end_t = add_quarters(current_t, duration)

    # Add work to holding
    work_item = {
        "renoId": renovation["_id"],
        "startT": current_t,
        "endT": end_t,
        "status": "ongoing",
    }

    await db.holdings.update_one({"_id": holding_id}, {"$push": {"works": work_item}})

    # Deduct cash
    await db.portfolios.update_one({"_id": portfolio["_id"]}, {"$inc": {"cash": -cost}})

    logger.info(
        f"User {current_user['username']} started renovation {request.renoCode} on holding {holding_id}"
    )

    return {
        "success": True,
        "holdingId": str(holding_id),
        "renovationCode": request.renoCode,
        "cost": cost,
        "startQuarter": current_t,
        "endQuarter": end_t,
        "remainingCash": round(cash - cost, 2),
    }


@router.post("/advance-quarter")
async def advance_quarter(current_user: dict = Depends(require_admin)):
    """
    Advance game time by one quarter

    Restricted to administrators: this is the only endpoint that moves the
    world for everybody at once. A single player calling it would fast-forward
    every other player's game, and calling it in a loop would run the whole
    simulation out.

    Actions performed:
    1. Generate or retrieve market data for next quarter
    2. Complete finished renovations and apply property upgrades
    3. Recalculate all property prices
    4. Update listings with new prices
    5. Insert price history records

    Returns summary of updates
    """
    db = get_database()

    # Get current quarter
    current_t = await get_current_quarter(db)
    next_t = add_quarters(current_t, 1)

    # Check if next quarter exists, if not generate it
    next_market = await db.marketindex.find_one({"t": next_t})
    if not next_market:
        # Generate new market data dynamically
        next_market = await generate_next_market_quarter(db, current_t)

    # Complete renovations that end at or before next quarter.
    # Only holdings that actually have an ongoing work due are read: the rest
    # of the table has nothing to contribute and does not need to travel.
    holdings = await db.holdings.find(
        {"works": {"$elemMatch": {"status": "ongoing", "endT": {"$lte": next_t}}}}
    ).to_list(length=None)

    completed_count = 0
    holding_updates = []
    property_updates = []

    if holdings:
        # The renovations and the properties the works refer to, read once each
        # rather than once per work.
        renovation_ids = {
            work["renoId"]
            for holding in holdings
            for work in holding.get("works", [])
            if work["status"] == "ongoing" and work["endT"] <= next_t
        }
        renovations = await db.renovations.find({"_id": {"$in": list(renovation_ids)}}).to_list(
            length=None
        )
        renovations_by_id = {reno["_id"]: reno for reno in renovations}

        property_ids = list({holding["propertyId"] for holding in holdings})
        properties_being_renovated = await db.properties.find(
            {"_id": {"$in": property_ids}}
        ).to_list(length=None)
        # Deltas from several completed works accumulate on the same property,
        # so each one is applied to the running copy, not to what was read.
        renovated_by_id = {prop["_id"]: dict(prop) for prop in properties_being_renovated}

        for holding in holdings:
            property_id = holding["propertyId"]
            works = holding.get("works", [])

            updated = False
            for work in works:
                if work["status"] != "ongoing" or work["endT"] > next_t:
                    continue

                work["status"] = "completed"
                updated = True
                completed_count += 1

                renovation = renovations_by_id.get(work["renoId"])
                property_data = renovated_by_id.get(property_id)
                if renovation and property_data:
                    renovated_by_id[property_id] = apply_renovation_delta(
                        property_data, renovation["delta"]
                    )

            if updated:
                holding_updates.append(
                    UpdateOne({"_id": holding["_id"]}, {"$set": {"works": works}})
                )
                property_updates.append(
                    UpdateOne(
                        {"_id": property_id},
                        {
                            "$set": {
                                field: renovated_by_id[property_id][field]
                                for field in ("epc", "state", "kitchen", "bath", "surface")
                            }
                        },
                    )
                )

    if holding_updates:
        await db.holdings.bulk_write(holding_updates)
    if property_updates:
        await db.properties.bulk_write(property_updates)

    # Recalculate prices for all properties at next quarter
    properties = await db.properties.find().to_list(length=None)
    price_updates = []

    for prop in properties:
        price = compute_property_price(prop, next_market)
        price_updates.append({"propertyId": prop["_id"], "t": next_t, "price": round(price, 2)})

    # Insert new price history
    if price_updates:
        await db.pricehistory.insert_many(price_updates)

    # Update listings with new prices. Each listing gets a different price, so
    # this cannot be one update; bulk_write makes it one round trip instead of
    # one per property.
    if price_updates:
        await db.listings.bulk_write(
            [
                UpdateOne(
                    {"propertyId": price_update["propertyId"]},
                    {"$set": {"lastComputedPrice": price_update["price"], "lastT": next_t}},
                )
                for price_update in price_updates
            ]
        )

    logger.info(
        f"Advanced from {current_t} to {next_t}: {len(price_updates)} properties updated, {completed_count} renovations completed"
    )

    return {
        "success": True,
        "previousQuarter": current_t,
        "quarter": next_t,
        "propertiesUpdated": len(price_updates),
        "renovationsCompleted": completed_count,
    }


@router.get("/current-quarter")
async def get_current_quarter_endpoint():
    """Get the current game quarter"""
    db = get_database()
    current_t = await get_current_quarter(db)
    return {"quarter": current_t}
