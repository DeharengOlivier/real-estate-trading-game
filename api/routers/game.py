"""
Game router - Game mechanics (renovations, time advancement)
Single Responsibility: Game progression and renovation management
"""
from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from typing import List
import logging

from api.database import get_database
from api.models import RenovateRequest
from api.auth import get_current_user
from api.services import (
    get_current_quarter, add_quarters,
    apply_renovation_delta, compute_property_price,
    generate_next_market_quarter
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
        results.append({
            "code": reno['code'],
            "label": reno['label'],
            "cost": reno['cost'],
            "durationQ": reno['durationQ'],
            "delta": reno['delta']
        })
    
    return results


@router.post("/renovate")
async def start_renovation(request: RenovateRequest, current_user: dict = Depends(get_current_user)):
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
    portfolio = await db.portfolios.find_one({
        "_id": holding["portfolioId"],
        "userId": current_user["_id"]
    })
    if not portfolio:
        raise HTTPException(status_code=403, detail="Not authorized to renovate this property")
    
    # Get renovation
    renovation = await db.renovations.find_one({"code": request.renoCode})
    if not renovation:
        raise HTTPException(status_code=404, detail="Renovation not found")
    
    cost = renovation['cost']
    cash = portfolio['cash']
    
    # Check sufficient cash
    if cash < cost:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient funds. Need {cost:,.2f} €, have {cash:,.2f} €"
        )
    
    # Get current quarter
    current_t = await get_current_quarter(db)
    duration = renovation['durationQ']
    end_t = add_quarters(current_t, duration)
    
    # Add work to holding
    work_item = {
        "renoId": renovation['_id'],
        "startT": current_t,
        "endT": end_t,
        "status": "ongoing"
    }
    
    await db.holdings.update_one(
        {"_id": holding_id},
        {"$push": {"works": work_item}}
    )
    
    # Deduct cash
    await db.portfolios.update_one(
        {"_id": portfolio['_id']},
        {"$inc": {"cash": -cost}}
    )
    
    logger.info(f"User {current_user['username']} started renovation {request.renoCode} on holding {holding_id}")
    
    return {
        "success": True,
        "holdingId": str(holding_id),
        "renovationCode": request.renoCode,
        "cost": cost,
        "startQuarter": current_t,
        "endQuarter": end_t,
        "remainingCash": round(cash - cost, 2)
    }


@router.post("/advance-quarter")
async def advance_quarter(current_user: dict = Depends(get_current_user)):
    """
    Advance game time by one quarter
    
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
    
    # Complete renovations that end at or before next quarter
    holdings = await db.holdings.find().to_list(length=None)
    
    completed_count = 0
    for holding in holdings:
        property_id = holding['propertyId']
        works = holding.get('works', [])
        
        updated = False
        for work in works:
            if work['status'] == 'ongoing' and work['endT'] <= next_t:
                # Complete this work
                work['status'] = 'completed'
                updated = True
                completed_count += 1
                
                # Apply renovation deltas to property
                renovation = await db.renovations.find_one({"_id": work['renoId']})
                if renovation:
                    property_data = await db.properties.find_one({"_id": property_id})
                    if property_data:
                        updated_prop = apply_renovation_delta(dict(property_data), renovation['delta'])
                        
                        await db.properties.update_one(
                            {"_id": property_id},
                            {"$set": {
                                "epc": updated_prop['epc'],
                                "state": updated_prop['state'],
                                "kitchen": updated_prop['kitchen'],
                                "bath": updated_prop['bath'],
                                "surface": updated_prop['surface']
                            }}
                        )
        
        if updated:
            await db.holdings.update_one(
                {"_id": holding['_id']},
                {"$set": {"works": works}}
            )
    
    # Recalculate prices for all properties at next quarter
    properties = await db.properties.find().to_list(length=None)
    price_updates = []
    
    for prop in properties:
        price = compute_property_price(prop, next_market)
        price_updates.append({
            "propertyId": prop['_id'],
            "t": next_t,
            "price": round(price, 2)
        })
    
    # Insert new price history
    if price_updates:
        await db.pricehistory.insert_many(price_updates)
    
    # Update listings with new prices
    for price_update in price_updates:
        await db.listings.update_one(
            {"propertyId": price_update['propertyId']},
            {"$set": {
                "lastComputedPrice": price_update['price'],
                "lastT": next_t
            }}
        )
    
    logger.info(f"Advanced from {current_t} to {next_t}: {len(price_updates)} properties updated, {completed_count} renovations completed")
    
    return {
        "success": True,
        "previousQuarter": current_t,
        "quarter": next_t,
        "propertiesUpdated": len(price_updates),
        "renovationsCompleted": completed_count
    }


@router.get("/current-quarter")
async def get_current_quarter_endpoint():
    """Get the current game quarter"""
    db = get_database()
    current_t = await get_current_quarter(db)
    return {"quarter": current_t}
