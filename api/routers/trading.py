"""
Trading router - Buy/sell properties and market listings
Single Responsibility: Property transactions and market operations
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from bson import ObjectId
from datetime import datetime
from pymongo import ReturnDocument
from typing import Optional
import logging

from api.database import get_database
from api.models import BuyRequest, SellRequest
from api.auth import get_current_user
from api.services import get_current_quarter, get_property_current_price, ZONE_TRENDS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trading", tags=["Trading"])

# Charged on both sides of a trade, on the price of the property.
TRANSACTION_FEE_RATE = 0.025


def _first_day_of_quarter(quarter: str) -> datetime:
    """Turn a game quarter such as "2024-3" into the date its quarter starts.

    Trades are stamped with a game date, not a wall-clock one, so that a chart
    of a portfolio reads against the simulated timeline.
    """
    year, index = map(int, quarter.split('-'))
    return datetime(year, (index - 1) * 3 + 1, 1)


async def _release_listing(db, property_id: ObjectId) -> None:
    """Put a property back on the market.

    Called on the two paths that give a claimed property up: a purchase that
    could not be paid for, and a completed sale.
    """
    await db.listings.update_one(
        {"propertyId": property_id},
        {"$set": {"isAvailable": True}}
    )


@router.get("/listings")
async def get_listings(
    zone: Optional[str] = None,
    type: Optional[str] = Query(None, description="Property type: house or apartment"),
    minPrice: Optional[float] = None,
    maxPrice: Optional[float] = None,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(50, ge=1, le=200, description="Number of results per page"),
    sortBy: str = Query("price", description="Sort by: price, surface, zone"),
    sortOrder: str = Query("asc", description="Sort order: asc or desc")
):
    """
    Get available property listings with filters and pagination.
    This endpoint uses a MongoDB aggregation pipeline for efficient querying.
    """
    db = get_database()
    
    # MongoDB Aggregation Pipeline
    pipeline = []

    # 1. Initial match on listings collection for available properties
    pipeline.append({"$match": {"isAvailable": True}})

    # 2. Join with the properties collection
    pipeline.append({
        "$lookup": {
            "from": "properties",
            "localField": "propertyId",
            "foreignField": "_id",
            "as": "property"
        }
    })

    # 3. Unwind the property array and filter out listings with no matching property
    pipeline.append({"$unwind": "$property"})

    # 4. Build the filter stage ($match)
    match_stage = {}
    if zone:
        match_stage["property.zone"] = zone
    if type:
        match_stage["property.type"] = type
    
    price_filter = {}
    if minPrice is not None:
        price_filter["$gte"] = minPrice
    if maxPrice is not None:
        price_filter["$lte"] = maxPrice
    if price_filter:
        match_stage["lastComputedPrice"] = price_filter

    if match_stage:
        pipeline.append({"$match": match_stage})

    # 5. Define the sort stage
    sort_field = "lastComputedPrice"
    if sortBy == "surface":
        sort_field = "property.surface"
    elif sortBy == "zone":
        sort_field = "property.zone"
    
    sort_order_val = 1 if sortOrder.lower() == "asc" else -1
    sort_stage = {"$sort": {sort_field: sort_order_val}}

    # 6. Use $facet for pagination and total count in one query
    facet_stage = {
        "$facet": {
            "items": [
                sort_stage,
                {"$skip": (page - 1) * limit},
                {"$limit": limit},
                {
                    "$project": {
                        "_id": 0,
                        "propertyId": {"$toString": "$property._id"},
                        "zone": "$property.zone",
                        "type": "$property.type",
                        "surface": "$property.surface",
                        "epc": "$property.epc",
                        "state": "$property.state",
                        "kitchen": "$property.kitchen",
                        "bath": "$property.bath",
                        "basePpm": "$property.base_ppm",
                        "price": "$lastComputedPrice"
                    }
                }
            ],
            "total": [
                {"$count": "count"}
            ]
        }
    }
    pipeline.append(facet_stage)

    # Execute the aggregation pipeline
    result = await db.listings.aggregate(pipeline).to_list(length=1)
    
    if not result:
        return {"items": [], "total": 0, "page": page, "limit": limit, "totalPages": 0}

    result_data = result[0]
    items = result_data.get("items", [])
    total_count = result_data["total"][0]["count"] if result_data.get("total") else 0
    
    # Enrich items with zone trend information and quality scores
    for item in items:
        zone = item.get("zone")
        zone_trend = ZONE_TRENDS.get(zone, 0.005)
        
        # Price per square metre (computed in Python for portability)
        surface = item.get("surface", 0)
        item["pricePerM2"] = round(item.get("price", 0) / surface, 2) if surface else 0

        # Add zone trend info (% per quarter)
        item["zoneTrend"] = round(zone_trend * 100, 2)  # Convert to percentage
        item["zoneTrendAnnual"] = round(zone_trend * 4 * 100, 1)  # Annual trend
        
        # Calculate quality scores (0-100)
        item["epcScore"] = round(item.get("epc", 0) * 100, 1)
        item["stateScore"] = round(item.get("state", 0) * 100, 1)
        item["kitchenScore"] = round(item.get("kitchen", 0) * 100, 1)
        item["bathScore"] = round(item.get("bath", 0) * 100, 1)
        
        # Overall quality score
        item["qualityScore"] = round(
            (item["epcScore"] + item["stateScore"] + item["kitchenScore"] + item["bathScore"]) / 4,
            1
        )
        
        # Calculate potential appreciation (estimated value in 1 year if market continues)
        current_price = item.get("price", 0)
        estimated_1y = current_price * (1 + zone_trend * 4)
        item["estimated1YearPrice"] = round(estimated_1y, 2)
        item["estimated1YearGain"] = round(estimated_1y - current_price, 2)
        item["estimated1YearGainPct"] = round(zone_trend * 4 * 100, 1)
    
    return {
        "items": items,
        "total": total_count,
        "page": page,
        "limit": limit,
        "totalPages": (total_count + limit - 1) // limit
    }


@router.post("/buy")
async def buy_property(request: BuyRequest, current_user: dict = Depends(get_current_user)):
    """
    Buy a property from the market

    - Claims the listing, so exactly one of two concurrent buyers wins it
    - Debits price + fees (2.5%) only if the balance actually covers them
    - Creates the holding and the trade record

    Concurrency
    -----------
    Both scarce things here (the property, the cash) are claimed with a single
    conditional write whose precondition lives in the filter, so the database
    decides the winner. Reading a value, checking it in Python and writing the
    result back is advisory: two requests read the same balance, both pass the
    check, and the second write silently overwrites the first.

    The claim comes first and the debit second, so a buyer who cannot pay
    releases the property again rather than holding it while the payment fails.
    Neither step depends on a transaction being available.
    """
    db = get_database()

    property_id = ObjectId(request.propertyId)

    portfolio = await db.portfolios.find_one({"userId": current_user["_id"]})
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    portfolio_id = portfolio['_id']

    # Claim the listing. find_one_and_update is atomic and returns the document
    # as it was before the write, so the price we pay is the price we claimed.
    listing = await db.listings.find_one_and_update(
        {"propertyId": property_id, "isAvailable": True},
        {"$set": {"isAvailable": False}}
    )

    if not listing:
        raise HTTPException(status_code=404, detail="Property not available")

    price = listing['lastComputedPrice']
    fees = price * TRANSACTION_FEE_RATE
    total_cost = price + fees

    current_quarter = await get_current_quarter(db)
    trade_date = _first_day_of_quarter(current_quarter)

    # The holding is created before the money moves. These are two writes, and
    # a process that dies between them leaves one of the two states behind: a
    # property nobody paid for, or a payment for nothing. The first is the one
    # to prefer, so it is the one this order can produce.
    holding = await db.holdings.insert_one({
        "portfolioId": portfolio_id,
        "propertyId": property_id,
        "buyPrice": price,
        "buyDate": trade_date,
        "works": []
    })

    # Debit with the affordability condition in the filter: the balance is read
    # and written in one operation, so it can never go negative.
    debited = await db.portfolios.find_one_and_update(
        {"_id": portfolio_id, "cash": {"$gte": total_cost}},
        {"$inc": {"cash": -total_cost}},
        return_document=ReturnDocument.AFTER
    )

    if not debited:
        # Nothing was charged, so undo the two claims: hand the property back
        # and put it on the market it was taken off a moment ago.
        await db.holdings.delete_one({"_id": holding.inserted_id})
        await _release_listing(db, property_id)
        current = await db.portfolios.find_one({"_id": portfolio_id})
        available = current['cash'] if current else 0.0
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient funds. Need {total_cost:,.2f} €, have {available:,.2f} €"
        )

    await db.trades.insert_one({
        "portfolioId": portfolio_id,
        "propertyId": property_id,
        "side": "buy",
        "price": price,
        "fees": fees,
        "ts": trade_date,
        "quarter": current_quarter
    })

    logger.info(f"User {current_user['username']} bought property {property_id} for {price}")

    return {
        "success": True,
        "propertyId": str(property_id),
        "price": round(price, 2),
        "fees": round(fees, 2),
        "totalCost": round(total_cost, 2),
        "remainingCash": round(debited['cash'], 2)
    }


@router.post("/sell")
async def sell_property(request: SellRequest, current_user: dict = Depends(get_current_user)):
    """
    Sell a property from holdings

    - Cannot sell while a renovation is ongoing
    - Claims the holding, so two concurrent sales cannot both be paid
    - Credits net proceeds (price - 2.5% commission) and puts the property back
      on the market

    Concurrency
    -----------
    The holding is the scarce resource, and it is removed with a single atomic
    find_one_and_delete. The loser of a race gets the same answer as somebody
    selling a property they never owned: 404. Reading the holding, deciding, and
    deleting it afterwards would pay both sellers.
    """
    db = get_database()

    property_id = ObjectId(request.propertyId)

    portfolio = await db.portfolios.find_one({"userId": current_user["_id"]})
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    portfolio_id = portfolio['_id']

    # Refuse an ongoing renovation before claiming anything, so a refusal
    # leaves the holding untouched.
    holding = await db.holdings.find_one({
        "portfolioId": portfolio_id,
        "propertyId": property_id
    })
    if not holding:
        raise HTTPException(status_code=404, detail="Property not in portfolio")

    if any(work['status'] == 'ongoing' for work in holding.get('works', [])):
        raise HTTPException(
            status_code=400,
            detail="Cannot sell property with ongoing renovations"
        )

    # Claim the holding. Whoever removes it is the one who gets paid for it.
    claimed = await db.holdings.find_one_and_delete({"_id": holding['_id']})
    if not claimed:
        raise HTTPException(status_code=404, detail="Property not in portfolio")

    current_t = await get_current_quarter(db)
    current_price = await get_property_current_price(db, property_id, current_t)

    fees = current_price * TRANSACTION_FEE_RATE
    net_proceeds = current_price - fees
    trade_date = _first_day_of_quarter(current_t)

    await db.portfolios.update_one(
        {"_id": portfolio_id},
        {"$inc": {"cash": net_proceeds}}
    )

    await db.trades.insert_one({
        "portfolioId": portfolio_id,
        "propertyId": property_id,
        "side": "sell",
        "price": current_price,
        "fees": fees,
        "ts": trade_date,
        "quarter": current_t
    })

    await _release_listing(db, property_id)

    buy_price = claimed['buyPrice']
    pnl = net_proceeds - buy_price

    logger.info(f"User {current_user['username']} sold property {property_id} for {current_price}, P&L: {pnl}")

    return {
        "success": True,
        "propertyId": str(property_id),
        "sellPrice": round(current_price, 2),
        "fees": round(fees, 2),
        "netProceeds": round(net_proceeds, 2),
        "buyPrice": round(buy_price, 2),
        "pnl": round(pnl, 2)
    }
