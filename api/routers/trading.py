"""
Trading router - Buy/sell properties and market listings
Single Responsibility: Property transactions and market operations
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from bson import ObjectId
from datetime import datetime
from typing import Optional
import logging

from api.database import get_database
from api.models import BuyRequest, SellRequest
from api.auth import get_current_user
from api.services import get_current_quarter, get_property_current_price, ZONE_TRENDS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trading", tags=["Trading"])


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
    
    - Deducts price + fees (2.5%) from cash
    - Creates holding record
    - Creates trade record
    - Marks listing as unavailable
    
    Uses MongoDB transaction for atomicity (with fallback)
    """
    db = get_database()
    
    property_id = ObjectId(request.propertyId)
    
    # Get user's portfolio
    portfolio = await db.portfolios.find_one({"userId": current_user["_id"]})
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    portfolio_id = portfolio['_id']
    cash = portfolio['cash']
    
    # Check if property is available
    listing = await db.listings.find_one({
        "propertyId": property_id,
        "isAvailable": True
    })
    
    if not listing:
        raise HTTPException(status_code=404, detail="Property not available")
    
    price = listing['lastComputedPrice']
    fees = price * 0.025  # 2.5% transaction fees
    total_cost = price + fees
    
    # Check sufficient cash
    if cash < total_cost:
        raise HTTPException(
            status_code=400, 
            detail=f"Insufficient funds. Need {total_cost:,.2f} €, have {cash:,.2f} €"
        )
    
    # Get current game quarter for trade timestamp
    current_quarter = await get_current_quarter(db)
    # Convert quarter string (e.g. "2024-4") to approximate datetime
    year, quarter = map(int, current_quarter.split('-'))
    trade_date = datetime(year, (quarter - 1) * 3 + 1, 1)  # First day of the quarter
    
    # Try to use MongoDB transaction for atomicity (requires replica set)
    # Falls back to sequential operations if transactions not available
    try:
        async with await db.client.start_session() as session:
            async with session.start_transaction():
                # Create holding
                holding = {
                    "portfolioId": portfolio_id,
                    "propertyId": property_id,
                    "buyPrice": price,
                    "buyDate": trade_date,
                    "works": []
                }
                await db.holdings.insert_one(holding, session=session)
                
                # Create trade record
                trade = {
                    "portfolioId": portfolio_id,
                    "propertyId": property_id,
                    "side": "buy",
                    "price": price,
                    "fees": fees,
                    "ts": trade_date,
                    "quarter": current_quarter
                }
                await db.trades.insert_one(trade, session=session)
                
                # Update cash
                new_cash = cash - total_cost
                await db.portfolios.update_one(
                    {"_id": portfolio_id},
                    {"$set": {"cash": new_cash}},
                    session=session
                )
                
                # Mark listing as unavailable
                await db.listings.update_one(
                    {"propertyId": property_id},
                    {"$set": {"isAvailable": False}},
                    session=session
                )
    except Exception as e:
        # If transactions not supported, fall back to sequential operations
        logger.warning(f"Transaction not supported, using sequential operations: {e}")
        
        # Create holding
        holding = {
            "portfolioId": portfolio_id,
            "propertyId": property_id,
            "buyPrice": price,
            "buyDate": trade_date,
            "works": []
        }
        await db.holdings.insert_one(holding)
        
        # Create trade record
        trade = {
            "portfolioId": portfolio_id,
            "propertyId": property_id,
            "side": "buy",
            "price": price,
            "fees": fees,
            "ts": trade_date,
            "quarter": current_quarter
        }
        await db.trades.insert_one(trade)
        
        # Update cash
        new_cash = cash - total_cost
        await db.portfolios.update_one(
            {"_id": portfolio_id},
            {"$set": {"cash": new_cash}}
        )
        
        # Mark listing as unavailable
        await db.listings.update_one(
            {"propertyId": property_id},
            {"$set": {"isAvailable": False}}
        )
    
    logger.info(f"User {current_user['username']} bought property {property_id} for {price}")
    
    return {
        "success": True,
        "propertyId": str(property_id),
        "price": round(price, 2),
        "fees": round(fees, 2),
        "totalCost": round(total_cost, 2),
        "remainingCash": round(new_cash, 2)
    }


@router.post("/sell")
async def sell_property(request: SellRequest, current_user: dict = Depends(get_current_user)):
    """
    Sell a property from holdings
    
    - Cannot sell if renovations are ongoing
    - Adds net proceeds (price - 2.5% fees) to cash
    - Removes holding record
    - Creates trade record
    - Marks listing as available
    
    Uses MongoDB transaction for atomicity (with fallback)
    """
    db = get_database()
    
    property_id = ObjectId(request.propertyId)
    
    # Get user's portfolio
    portfolio = await db.portfolios.find_one({"userId": current_user["_id"]})
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    portfolio_id = portfolio['_id']
    
    # Find holding
    holding = await db.holdings.find_one({
        "portfolioId": portfolio_id,
        "propertyId": property_id
    })
    
    if not holding:
        raise HTTPException(status_code=404, detail="Property not in portfolio")
    
    # Check for ongoing works
    ongoing_works = [w for w in holding.get('works', []) if w['status'] == 'ongoing']
    if ongoing_works:
        raise HTTPException(
            status_code=400, 
            detail="Cannot sell property with ongoing renovations"
        )
    
    # Get current price
    current_t = await get_current_quarter(db)
    current_price = await get_property_current_price(db, property_id, current_t)
    
    fees = current_price * 0.025  # 2.5% transaction fees
    net_proceeds = current_price - fees
    
    # Convert quarter string to datetime for trade timestamp
    year, quarter = map(int, current_t.split('-'))
    trade_date = datetime(year, (quarter - 1) * 3 + 1, 1)
    
    # Try to use MongoDB transaction for atomicity (requires replica set)
    # Falls back to sequential operations if transactions not available
    try:
        async with await db.client.start_session() as session:
            async with session.start_transaction():
                # Create trade record
                trade = {
                    "portfolioId": portfolio_id,
                    "propertyId": property_id,
                    "side": "sell",
                    "price": current_price,
                    "fees": fees,
                    "ts": trade_date,
                    "quarter": current_t
                }
                await db.trades.insert_one(trade, session=session)
                
                # Update cash
                await db.portfolios.update_one(
                    {"_id": portfolio_id},
                    {"$inc": {"cash": net_proceeds}},
                    session=session
                )
                
                # Remove holding
                await db.holdings.delete_one({"_id": holding['_id']}, session=session)
                
                # Mark listing as available again
                await db.listings.update_one(
                    {"propertyId": property_id},
                    {"$set": {"isAvailable": True}},
                    session=session
                )
    except Exception as e:
        # If transactions not supported, fall back to sequential operations
        logger.warning(f"Transaction not supported, using sequential operations: {e}")
        
        # Create trade record
        trade = {
            "portfolioId": portfolio_id,
            "propertyId": property_id,
            "side": "sell",
            "price": current_price,
            "fees": fees,
            "ts": trade_date,
            "quarter": current_t
        }
        await db.trades.insert_one(trade)
        
        # Update cash
        await db.portfolios.update_one(
            {"_id": portfolio_id},
            {"$inc": {"cash": net_proceeds}}
        )
        
        # Remove holding
        await db.holdings.delete_one({"_id": holding['_id']})
        
        # Mark listing as available again
        await db.listings.update_one(
            {"propertyId": property_id},
            {"$set": {"isAvailable": True}}
        )
    
    buy_price = holding['buyPrice']
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
