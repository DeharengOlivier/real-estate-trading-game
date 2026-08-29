"""
Portfolio router - Portfolio management and holdings
Single Responsibility: Portfolio operations and reporting
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_current_user
from api.database import get_database
from api.models import HoldingDetail, PortfolioSummary
from api.services import (
    get_current_quarter,
    get_property_current_prices,
    parse_quarter_string,
)
from simulation.constants import INITIAL_CASH

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

    # The amount every new account starts with, named once in simulation.constants.
    INITIAL_CAPITAL = float(INITIAL_CASH)

    # Get current quarter
    current_t = await get_current_quarter(db)

    # Get all current holdings
    holdings = await db.holdings.find({"portfolioId": portfolio_id}).to_list(length=None)

    # Value the holdings. One batched price lookup for the whole portfolio,
    # not one per property: this page used to cost a round trip per holding.
    property_ids = [holding['propertyId'] for holding in holdings]
    prices = await get_property_current_prices(db, property_ids, current_t)
    equity = sum(prices.get(pid, 0) for pid in property_ids)

    # Every trade this portfolio ever made, read once. The year-to-date subset
    # is taken from it in memory rather than with a second query: it is the
    # same documents filtered on the same field.
    all_trades = await db.trades.find({
        "portfolioId": portfolio_id
    }).to_list(length=None)

    # Total P&L is the whole position measured against what the account
    # started with. Cash already carries every fee and renovation that was
    # ever paid, because each one was debited from it.
    total_value = cash + equity
    pnl_total = total_value - INITIAL_CAPITAL

    current_year = parse_quarter_string(current_t)[0]
    year_start = datetime(current_year, 1, 1)

    # A sale is scored against the purchase that opened the position, which may
    # have happened in an earlier year, so buy prices are collected from the
    # full history before the year-to-date pass reads them.
    buy_prices = {
        str(trade['propertyId']): trade['price']
        for trade in all_trades if trade['side'] == 'buy'
    }

    pnl_ytd = 0.0
    ytd_buy_prices = {}

    for trade in all_trades:
        if trade.get('ts') is None or trade['ts'] < year_start:
            continue

        prop_id_str = str(trade['propertyId'])

        if trade['side'] == 'buy':
            ytd_buy_prices[prop_id_str] = trade['price']
            pnl_ytd -= trade['fees']
        elif trade['side'] == 'sell':
            original_buy_price = (
                ytd_buy_prices.get(prop_id_str)
                or buy_prices.get(prop_id_str, 0)
            )
            pnl_ytd += (trade['price'] - trade['fees']) - original_buy_price

    return PortfolioSummary(
        cash=round(cash, 2),
        equity=round(equity, 2),
        totalValue=round(total_value, 2),
        pnlTotal=round(pnl_total, 2),
        pnlYTD=round(pnl_ytd, 2)
    )


@router.get("/holdings", response_model=list[HoldingDetail])
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

    # Everything the loop needs, read in three queries instead of three per
    # holding: the properties, their current prices, and the renovations any of
    # the works refer to.
    property_ids = [holding['propertyId'] for holding in holdings]
    properties = await db.properties.find(
        {"_id": {"$in": property_ids}}
    ).to_list(length=None)
    properties_by_id = {prop['_id']: prop for prop in properties}

    prices = await get_property_current_prices(db, property_ids, current_t)

    renovation_ids = [
        work['renoId']
        for holding in holdings
        for work in holding.get('works', [])
    ]
    renovation_costs_by_id = {}
    if renovation_ids:
        renovations = await db.renovations.find(
            {"_id": {"$in": list(set(renovation_ids))}}
        ).to_list(length=None)
        renovation_costs_by_id = {reno['_id']: reno['cost'] for reno in renovations}

    results = []
    for holding in holdings:
        property_id = holding['propertyId']
        prop_id_str = str(property_id)
        buy_price = holding['buyPrice']

        prop = properties_by_id.get(property_id)
        if not prop:
            continue

        current_price = prices.get(property_id, 0)

        # Calculate total cost basis
        buy_fees = buy_fees_map.get(prop_id_str, 0)

        renovation_costs = sum(
            renovation_costs_by_id.get(work['renoId'], 0.0)
            for work in holding.get('works', [])
        )

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
