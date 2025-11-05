"""
Portfolio router - Portfolio management and holdings
Single Responsibility: Portfolio operations and reporting
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List
from datetime import datetime
import logging

from api.database import get_database
from api.models import PortfolioSummary, HoldingDetail
from api.auth import get_current_user
from api.services import get_current_quarter, get_property_current_price, parse_quarter_string

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(current_user: dict = Depends(get_current_user)):
    """
    Get portfolio summary with cash, equity, total value, and P&L
    
    P&L Calculation Logic:
    - Initial capital: 1,000,000 €
    - Total P&L = (Current cash + Current value of holdings) - Initial capital
    - P&L accounts for:
      * Purchase fees (2.5%)
      * Sale fees (2.5%)
      * Renovation costs
      * Realized gains/losses on sales
      * Unrealized gains/losses on held properties
    
    Returns:
    - cash: Available cash balance
    - equity: Current value of all holdings
    - totalValue: cash + equity
    - pnlTotal: Total profit/loss vs initial capital (1M€)
    - pnlYTD: Year-to-date profit/loss
    """
    db = get_database()
    
    # Get the user's portfolio
    portfolio = await db.portfolios.find_one({"userId": current_user["_id"]})
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    portfolio_id = portfolio['_id']
    cash = portfolio['cash']
    
    # Initial capital (starting amount granted to every new account)
    INITIAL_CAPITAL = 1000000.0
    
    # Get current quarter
    current_t = await get_current_quarter(db)
    
    # Get all current holdings
    holdings = await db.holdings.find({"portfolioId": portfolio_id}).to_list(length=None)
    
    # Calculate equity (current value of holdings)
    equity = 0.0
    unrealized_pnl = 0.0  # Unrealized P&L on held properties
    
    for holding in holdings:
        property_id = holding['propertyId']
        buy_price = holding['buyPrice']
        
        # Get current price
        current_price = await get_property_current_price(db, property_id, current_t)
        equity += current_price
        
        # Unrealized P&L = current value - buy price (the buy price excludes fees).
        # Purchase fees were already deducted from cash, so they are already
        # reflected in the total P&L.
        unrealized_pnl += (current_price - buy_price)
    
    # Calculate realized P&L from all trades (buys + sells)
    all_trades = await db.trades.find({
        "portfolioId": portfolio_id
    }).to_list(length=None)
    
    realized_pnl = 0.0
    buy_prices = {}  # Map propertyId -> buy price for P&L calculation
    
    for trade in all_trades:
        prop_id_str = str(trade['propertyId'])
        
        if trade['side'] == 'buy':
            # Buy: store the buy price (excluding fees)
            buy_prices[prop_id_str] = trade['price']
            # Purchase fees are an immediate loss
            realized_pnl -= trade['fees']

        elif trade['side'] == 'sell':
            # Sell: P&L = sale price - fees - buy price
            sell_price = trade['price']
            sell_fees = trade['fees']
            original_buy_price = buy_prices.get(prop_id_str, 0)

            # P&L for this sale
            trade_pnl = (sell_price - sell_fees) - original_buy_price
            realized_pnl += trade_pnl
    
    # Calculate renovation costs (money spent on renovation works)
    all_holdings = await db.holdings.find({
        "portfolioId": portfolio_id
    }).to_list(length=None)
    
    renovation_costs = 0.0
    for holding in all_holdings:
        for work in holding.get('works', []):
            reno = await db.renovations.find_one({"_id": work['renoId']})
            if reno:
                renovation_costs += reno['cost']
    
    # Total P&L = Current total value - Initial capital
    total_value = cash + equity
    pnl_total = total_value - INITIAL_CAPITAL
    
    # Alternative calculation (should give same result):
    # pnl_total = realized_pnl + unrealized_pnl - renovation_costs
    
    # Calculate YTD P&L (trades from the current year)
    current_year = parse_quarter_string(current_t)[0]
    year_start = datetime(current_year, 1, 1)
    
    trades_ytd = await db.trades.find({
        "portfolioId": portfolio_id,
        "ts": {"$gte": year_start}
    }).to_list(length=None)
    
    pnl_ytd = 0.0
    ytd_buy_prices = {}
    
    for trade in trades_ytd:
        prop_id_str = str(trade['propertyId'])
        
        if trade['side'] == 'buy':
            ytd_buy_prices[prop_id_str] = trade['price']
            pnl_ytd -= trade['fees']
        elif trade['side'] == 'sell':
            sell_price = trade['price']
            sell_fees = trade['fees']
            # Check if bought this year or before
            original_buy_price = ytd_buy_prices.get(prop_id_str) or buy_prices.get(prop_id_str, 0)
            trade_pnl = (sell_price - sell_fees) - original_buy_price
            pnl_ytd += trade_pnl
    
    return PortfolioSummary(
        cash=round(cash, 2),
        equity=round(equity, 2),
        totalValue=round(total_value, 2),
        pnlTotal=round(pnl_total, 2),
        pnlYTD=round(pnl_ytd, 2)
    )


@router.get("/holdings", response_model=List[HoldingDetail])
async def get_holdings(current_user: dict = Depends(get_current_user)):
    """
    Get detailed list of holdings with current prices and P&L
    
    P&L Calculation per property:
    - P&L = Current value - (Buy price + Purchase fees + Renovation costs)
    - Includes all real acquisition and improvement costs
    
    Returns for each holding:
    - Property details (zone, type, surface)
    - Buy price vs current price
    - Unrealized P&L (amount and percentage) including all costs
    - Number of ongoing renovation works
    """
    db = get_database()
    
    # Get the user's portfolio
    portfolio = await db.portfolios.find_one({"userId": current_user["_id"]})
    if not portfolio:
        return []
    
    portfolio_id = portfolio['_id']
    current_t = await get_current_quarter(db)
    
    # Get all holdings
    holdings = await db.holdings.find({"portfolioId": portfolio_id}).to_list(length=None)
    
    # Get all trades to find buy fees
    all_trades = await db.trades.find({
        "portfolioId": portfolio_id
    }).to_list(length=None)
    
    # Map propertyId -> buy fees
    buy_fees_map = {}
    for trade in all_trades:
        if trade['side'] == 'buy':
            prop_id_str = str(trade['propertyId'])
            buy_fees_map[prop_id_str] = trade.get('fees', 0)
    
    results = []
    for holding in holdings:
        property_id = holding['propertyId']
        prop_id_str = str(property_id)
        buy_price = holding['buyPrice']
        
        # Get property details
        prop = await db.properties.find_one({"_id": property_id})
        if not prop:
            continue
        
        # Get current price
        current_price = await get_property_current_price(db, property_id, current_t)
        
        # Calculate total cost basis
        buy_fees = buy_fees_map.get(prop_id_str, 0)
        
        # Add renovation costs
        renovation_costs = 0.0
        for work in holding.get('works', []):
            reno = await db.renovations.find_one({"_id": work['renoId']})
            if reno:
                renovation_costs += reno['cost']
        
        # Total invested = buy price + purchase fees + renovation works
        total_invested = buy_price + buy_fees + renovation_costs

        # P&L = current value - total invested
        pnl = current_price - total_invested
        pnl_pct = (pnl / total_invested * 100) if total_invested > 0 else 0
        
        # Count ongoing works
        ongoing_works = sum(1 for w in holding.get('works', []) if w['status'] == 'ongoing')
        
        results.append(HoldingDetail(
            holdingId=str(holding['_id']),
            propertyId=str(property_id),
            zone=prop['zone'],
            type=prop['type'],
            surface=prop['surface'],
            buyPrice=round(buy_price, 2),
            buyFees=round(buy_fees, 2),
            renovationCosts=round(renovation_costs, 2),
            totalInvested=round(total_invested, 2),
            currentPrice=round(current_price, 2),
            pnl=round(pnl, 2),
            pnlPct=round(pnl_pct, 2),
            ongoingWorks=ongoing_works
        ))
    
    return results
