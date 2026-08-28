"""
Charts router - Data visualization and analytics endpoints
Single Responsibility: Provide data for charts and reports
"""
from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from typing import Dict, List
from collections import defaultdict
from datetime import datetime
import logging

from api.database import get_database
from api.identifiers import parse_object_id
from api.auth import get_current_user
from api.services import (
    get_current_quarter,
    parse_quarter_string,
    add_quarters,
    get_property_current_price,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/charts", tags=["Charts"])


def datetime_to_quarter(ts: datetime) -> str:
    """Convert datetime to quarter string format YYYY-Q"""
    quarter = ((ts.month - 1) // 3) + 1
    return f"{ts.year}-{quarter}"


def quarter_to_index(t: str) -> int:
    """Convert quarter string to monotonic integer index"""
    year, quarter = parse_quarter_string(t)
    return year * 4 + quarter


@router.get("/portfolio-equity")
async def get_portfolio_equity_chart(current_user: dict = Depends(get_current_user)):
    """
    Get portfolio equity over time for charting
    
    Returns time series of:
    - Total portfolio value (cash + holdings value)
    - By quarter
    """
    db = get_database()
    
    # Get user's portfolio
    portfolio = await db.portfolios.find_one({"userId": current_user["_id"]})
    if not portfolio:
        return []

    portfolio_id = portfolio["_id"]
    current_quarter = await get_current_quarter(db)

    # Fetch trades chronologically to reconstruct portfolio state
    trades = await db.trades.find({
        "portfolioId": portfolio_id
    }).sort("ts", 1).to_list(length=None)

    # If no trades exist yet, fall back to current snapshot
    if not trades:
        holdings = await db.holdings.find({"portfolioId": portfolio_id}).to_list(length=None)
        equity_value = 0.0
        for holding in holdings:
            equity_value += await get_property_current_price(db, holding["propertyId"], current_quarter)

        cash_value = float(portfolio.get("cash", 0.0))
        total_value = cash_value + equity_value
        return [{
            "quarter": current_quarter,
            "equity": round(equity_value, 2),
            "cash": round(cash_value, 2),
            "total": round(total_value, 2)
        }]

    # Map trades by quarter and gather metadata
    trades_by_quarter = defaultdict(list)
    trade_quarters: List[str] = []
    property_ids = set()

    for trade in trades:
        ts = trade.get("ts")
        if isinstance(ts, datetime):
            trade_quarter = datetime_to_quarter(ts)
        else:
            # Fallback for malformed data
            trade_quarter = trade.get("quarter") or current_quarter

        trade["_quarter"] = trade_quarter
        trades_by_quarter[trade_quarter].append(trade)
        trade_quarters.append(trade_quarter)
        property_ids.add(trade["propertyId"])

    # Ensure trades are ordered within each quarter
    for quarter, quarter_trades in trades_by_quarter.items():
        quarter_trades.sort(key=lambda t: t.get("ts", datetime.min))

    # Determine starting cash by reversing trades
    cash_now = float(portfolio.get("cash", 0.0))
    initial_cash = cash_now
    for trade in reversed(trades):
        price = float(trade.get("price", 0.0))
        fees = float(trade.get("fees", 0.0))
        if trade.get("side") == "buy":
            initial_cash += price + fees
        else:
            initial_cash -= max(0.0, price - fees)

    # Determine time window (start quarter one period before first trade)
    earliest_trade_quarter = min(trade_quarters, key=quarter_to_index)
    start_quarter = add_quarters(earliest_trade_quarter, -1)

    # Clamp to earliest available market data
    first_market = await db.marketindex.find_one(sort=[("t", 1)])
    if first_market:
        min_index = quarter_to_index(first_market["t"])
        while quarter_to_index(start_quarter) < min_index:
            start_quarter = add_quarters(start_quarter, 1)

    end_index = quarter_to_index(current_quarter)

    # Build ordered list of quarters to evaluate
    quarter_sequence: List[str] = []
    iter_quarter = start_quarter
    while quarter_to_index(iter_quarter) <= end_index:
        quarter_sequence.append(iter_quarter)
        iter_quarter = add_quarters(iter_quarter, 1)

    # Fallback if no valid quarter sequence (edge case)
    if not quarter_sequence:
        quarter_sequence = [current_quarter]

    # Augment property set with current holdings to cover edge cases
    holdings_snapshot = await db.holdings.find({"portfolioId": portfolio_id}).to_list(length=None)
    for holding in holdings_snapshot:
        property_ids.add(holding["propertyId"])

    # Preload price history for all relevant properties within the time window
    property_price_map: Dict[str, List[tuple]] = {}
    if property_ids and quarter_sequence:
        price_history = await db.pricehistory.find({
            "propertyId": {"$in": list(property_ids)},
            "t": {"$gte": quarter_sequence[0], "$lte": current_quarter}
        }).sort("t", 1).to_list(length=None)

        for record in price_history:
            prop_key = str(record["propertyId"])
            property_price_map.setdefault(prop_key, []).append(
                (quarter_to_index(record["t"]), float(record["price"]))
            )

        for entries in property_price_map.values():
            entries.sort(key=lambda item: item[0])

    # Simulation state across quarters
    holdings_state: Dict[str, Dict[str, ObjectId]] = {}
    price_cache: Dict[tuple, float] = {}
    cash = initial_cash
    equity_history: List[Dict[str, float]] = []

    for quarter in quarter_sequence:
        quarter_index = quarter_to_index(quarter)

        # Apply trades executed in this quarter
        for trade in trades_by_quarter.get(quarter, []):
            price = float(trade.get("price", 0.0))
            fees = float(trade.get("fees", 0.0))
            prop_obj = trade["propertyId"]
            prop_key = str(prop_obj)

            if trade.get("side") == "buy":
                cash -= price + fees
                holdings_state[prop_key] = {"property_id": prop_obj}
            else:
                cash += max(0.0, price - fees)
                holdings_state.pop(prop_key, None)

        # Compute equity based on holdings
        equity_value = 0.0
        for prop_key, info in holdings_state.items():
            cache_key = (prop_key, quarter)
            price = price_cache.get(cache_key)

            if price is None:
                entries = property_price_map.get(prop_key)
                if entries:
                    for idx, entry_price in entries:
                        if idx <= quarter_index:
                            price = entry_price
                        else:
                            break

                if price is None:
                    price = await get_property_current_price(
                        db,
                        info["property_id"],
                        quarter
                    )

                price_cache[cache_key] = float(price or 0.0)

            equity_value += float(price or 0.0)

        total_value = cash + equity_value
        equity_history.append({
            "quarter": quarter,
            "equity": round(equity_value, 2),
            "cash": round(cash, 2),
            "total": round(total_value, 2)
        })

    return equity_history


@router.get("/property/{property_id}")
async def get_property_price_chart(property_id: str, current_user: dict = Depends(get_current_user)):
    """
    Get price history for a specific property
    
    Returns time series of property value by quarter
    """
    db = get_database()
    
    prop_id = parse_object_id(property_id, "property ID")
    
    # Get property
    property_data = await db.properties.find_one({"_id": prop_id})
    if not property_data:
        raise HTTPException(status_code=404, detail="Property not found")
    
    # Get price history
    price_history = await db.pricehistory.find({
        "propertyId": prop_id
    }).sort("t", 1).to_list(length=None)
    
    quarters = [ph['t'] for ph in price_history]
    prices = [ph['price'] for ph in price_history]
    
    return {
        "propertyId": property_id,
        "zone": property_data.get('zone'),
        "type": property_data.get('type'),
        "quarters": quarters,
        "prices": prices
    }
