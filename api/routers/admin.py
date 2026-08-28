"""
Admin router - Administrative operations for properties, renovations, and trades
Single Responsibility: CRUD operations and monitoring, restricted to administrators.

Everything under this prefix either rewrites the shared world (the property and
renovation catalogs decide the market every player trades in) or reads across
every player's data. None of it is a player-facing operation, so the gate is
declared once on the router: an endpoint added here is refused to ordinary
players by default, rather than by remembering to add a decorator.

Handlers still take ``current_user`` where they need to know who acted; that
dependency answers identity, while the router-level one answers entitlement.
"""
from fastapi import APIRouter, HTTPException, Depends, status
from bson import ObjectId
from typing import List
import logging

from api.database import get_database
from api.models import Property, Renovation
from api.auth import get_current_user, require_admin
from api.services import get_current_quarter, compute_property_price

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/admin",
    tags=["Administration"],
    dependencies=[Depends(require_admin)],
)


# ==================== PROPERTIES ====================

@router.post("/properties", status_code=status.HTTP_201_CREATED)
async def create_property(
    property_data: Property,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new property
    
    Also creates a listing for the property with computed price
    Available to all authenticated users
    """
    db = get_database()
    
    prop_dict = property_data.model_dump(exclude={"id"})
    result = await db.properties.insert_one(prop_dict)
    
    # Create listing for this property
    current_t = await get_current_quarter(db)
    market_index = await db.marketindex.find_one({"t": current_t})
    
    if market_index:
        price = compute_property_price(prop_dict, market_index)
        await db.listings.insert_one({
            "propertyId": result.inserted_id,
            "isAvailable": True,
            "lastComputedPrice": price,
            "lastT": current_t
        })
    
    logger.info(f"Admin created property: {result.inserted_id}")
    return {"id": str(result.inserted_id), "message": "Property created successfully"}


@router.get("/properties")
async def list_all_properties(
    skip: int = 0,
    limit: int = 100,
    current_user: dict = Depends(get_current_user)
):
    """List all properties with pagination (available to all authenticated users)"""
    db = get_database()
    properties = await db.properties.find().skip(skip).limit(limit).to_list(length=limit)
    
    return [
        {
            "id": str(prop["_id"]),
            "zone": prop["zone"],
            "type": prop["type"],
            "surface": prop["surface"],
            "epc": prop["epc"],
            "state": prop["state"],
            "kitchen": prop["kitchen"],
            "bath": prop["bath"],
            "base_ppm": prop["base_ppm"]
        }
        for prop in properties
    ]


@router.get("/properties/{property_id}")
async def get_property_by_id(
    property_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get detailed property information by ID (available to all authenticated users)"""
    db = get_database()
    
    try:
        prop_id = ObjectId(property_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid property ID")
    
    prop = await db.properties.find_one({"_id": prop_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    
    return {
        "id": str(prop["_id"]),
        "zone": prop["zone"],
        "type": prop["type"],
        "surface": prop["surface"],
        "epc": prop["epc"],
        "state": prop["state"],
        "kitchen": prop["kitchen"],
        "bath": prop["bath"],
        "base_ppm": prop["base_ppm"]
    }


@router.put("/properties/{property_id}")
async def update_property(
    property_id: str,
    property_data: Property,
    current_user: dict = Depends(get_current_user)
):
    """Update property characteristics (available to all authenticated users)"""
    db = get_database()
    
    try:
        prop_id = ObjectId(property_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid property ID")
    
    prop_dict = property_data.model_dump(exclude={"id"})
    
    result = await db.properties.update_one(
        {"_id": prop_id},
        {"$set": prop_dict}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Property not found")
    
    logger.info(f"Admin updated property: {property_id}")
    return {"message": "Property updated successfully"}


@router.delete("/properties/{property_id}")
async def delete_property(
    property_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a property (only if not owned) - available to all authenticated users"""
    db = get_database()
    
    try:
        prop_id = ObjectId(property_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid property ID")
    
    # Check if property is in use
    holding = await db.holdings.find_one({"propertyId": prop_id})
    if holding:
        raise HTTPException(status_code=400, detail="Cannot delete property that is owned")
    
    result = await db.properties.delete_one({"_id": prop_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Property not found")
    
    # Delete associated listing
    await db.listings.delete_one({"propertyId": prop_id})
    
    logger.info(f"Admin deleted property: {property_id}")
    return {"message": "Property deleted successfully"}


# ==================== RENOVATIONS ====================

@router.post("/renovations", status_code=status.HTTP_201_CREATED)
async def create_renovation(
    renovation_data: Renovation,
    current_user: dict = Depends(get_current_user)
):
    """Create a new renovation type (available to all authenticated users)"""
    db = get_database()
    
    # Check if code already exists
    existing = await db.renovations.find_one({"code": renovation_data.code})
    if existing:
        raise HTTPException(status_code=400, detail="Renovation code already exists")
    
    reno_dict = renovation_data.model_dump(exclude={"id"})
    result = await db.renovations.insert_one(reno_dict)
    
    logger.info(f"Admin created renovation type: {renovation_data.code}")
    return {"id": str(result.inserted_id), "message": "Renovation type created successfully"}


@router.get("/renovations")
async def get_all_renovations(current_user: dict = Depends(get_current_user)):
    """Get all renovation types (available to all authenticated users)"""
    db = get_database()
    renovations = await db.renovations.find().to_list(length=None)
    
    # Convert ObjectId to string
    for reno in renovations:
        reno["id"] = str(reno.pop("_id"))
    
    return renovations


@router.put("/renovations/{code}")
async def update_renovation(
    code: str,
    renovation_data: Renovation,
    current_user: dict = Depends(get_current_user)
):
    """Update renovation type (available to all authenticated users)"""
    db = get_database()
    
    reno_dict = renovation_data.model_dump(exclude={"id"})
    
    result = await db.renovations.update_one(
        {"code": code},
        {"$set": reno_dict}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Renovation not found")
    
    logger.info(f"Admin updated renovation: {code}")
    return {"message": "Renovation updated successfully"}


@router.delete("/renovations/{code}")
async def delete_renovation(
    code: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a renovation type (available to all authenticated users)"""
    db = get_database()
    
    result = await db.renovations.delete_one({"code": code})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Renovation not found")
    
    logger.info(f"Admin deleted renovation: {code}")
    return {"message": "Renovation deleted successfully"}


# ==================== TRADES ====================

@router.get("/trades")
async def list_all_trades(
    skip: int = 0,
    limit: int = 100,
    current_user: dict = Depends(get_current_user)
):
    """List all trades across all portfolios (available to all authenticated users)"""
    db = get_database()
    trades = await db.trades.find().sort("ts", -1).skip(skip).limit(limit).to_list(length=limit)
    
    return [
        {
            "id": str(trade["_id"]),
            "portfolioId": str(trade["portfolioId"]),
            "propertyId": str(trade["propertyId"]),
            "side": trade["side"],
            "price": trade["price"],
            "fees": trade["fees"],
            "ts": trade["ts"].isoformat()
        }
        for trade in trades
    ]
