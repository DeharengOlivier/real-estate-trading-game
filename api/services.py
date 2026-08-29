"""
Business logic and pricing calculations
"""

import math
import random

from bson import ObjectId

from simulation.constants import (
    A_CONF,
    A_INC,
    A_INF,
    A_POL,
    A_RATE,
    A_UNEMP,
    B_ACC,
    B_ATTR,
    B_NUI,
    B_TENS,
    W_BATH,
    W_EPC,
    W_KITCHEN,
    W_STATE,
    ZONES,
)

# Per-zone appreciation trends (% per quarter), calibrated on real Belgian data.
# These are structural trends layered on top of random drift so prices move
# differently across zones rather than all following the same macro signal.
ZONE_TRENDS = {
    "Bruxelles-Centre": 0.006,  # +0.6% per quarter = +2.4%/yr (realistic for a premium zone)
    "Ixelles": 0.005,  # +0.5% per quarter = +2.0%/yr (trendy neighborhood)
    "Uccle": 0.004,  # +0.4% per quarter = +1.6%/yr (upscale residential)
    "Schaerbeek": 0.003,  # +0.3% per quarter = +1.2%/yr (gradual gentrification)
    "Gand-Centre": 0.004,  # +0.4% per quarter = +1.6%/yr (university city)
    "Anvers-Sud": 0.003,  # +0.3% per quarter = +1.2%/yr (developing area)
    "Namur-Est": 0.002,  # +0.2% per quarter = +0.8%/yr (suburban)
    "Namur-Centre": 0.002,  # +0.2% per quarter = +0.8%/yr (stable)
    "Liège-Centre": 0.002,  # +0.2% per quarter = +0.8%/yr (modest growth)
    "Anvers-Nord": 0.001,  # +0.1% per quarter = +0.4%/yr (industrial area)
    "Liège-Sud": 0.001,  # +0.1% per quarter = +0.4%/yr (weak demand)
    "Charleroi-Ville": 0.000,  # +0.0% per quarter = stagnation (realistic for Charleroi)
}


def compute_macro_index(market_index: dict) -> float:
    """Compute MacroIndex(t) from market data"""
    exponent = (
        A_INF * market_index["inflation"]
        - A_RATE * market_index["rate"]
        + A_INC * market_index["income"]
        - A_UNEMP * market_index["unemployment"]
        + A_CONF * market_index["confidence"]
        + A_POL * market_index["policy"]
    )
    return math.exp(exponent)


def compute_local_index(local_data: dict) -> float:
    """Compute LocalIndex(zone, t) from local data"""
    exponent = (
        B_ACC * local_data["access"]
        + B_ATTR * local_data["attract"]
        - B_NUI * local_data["nuisance"]
        + B_TENS * local_data["tension"]
    )
    return math.exp(exponent)


def compute_property_price(
    property_data: dict, market_index: dict, add_noise: bool = False
) -> float:
    """
    Compute property price at quarter t

    price_b(t) = base_ppm * surface
                 * (1 + w_epc*EPC) * (1 + w_state*State)
                 * (1 + w_kitchen*Kitchen) * (1 + w_bath*Bath)
                 * MacroIndex(t) * LocalIndex(zone, t) * Noise(t)
    """
    # Base price
    base_price = property_data["base_ppm"] * property_data["surface"]

    # Property characteristics multipliers
    char_multiplier = (
        (1 + W_EPC * property_data["epc"])
        * (1 + W_STATE * property_data["state"])
        * (1 + W_KITCHEN * property_data["kitchen"])
        * (1 + W_BATH * property_data["bath"])
    )

    # Macro index
    macro_idx = compute_macro_index(market_index)

    # Local index
    local_data = None
    for loc in market_index["locals"]:
        if loc["zone"] == property_data["zone"]:
            local_data = loc
            break

    if not local_data:
        raise ValueError(f"No local data for zone {property_data['zone']}")

    local_idx = compute_local_index(local_data)

    # Noise (not used in API, only in seed)
    noise = 1.0

    price = base_price * char_multiplier * macro_idx * local_idx * noise
    return max(0, price)


def parse_quarter_string(t: str) -> tuple:
    """Parse quarter string to (year, quarter)"""
    year, q = t.split("-")
    return int(year), int(q)


def get_quarter_string(year: int, quarter: int) -> str:
    """Convert year and quarter to string format YYYY-Q"""
    return f"{year}-{quarter}"


def add_quarters(t: str, n: int) -> str:
    """Add n quarters to a quarter string"""
    year, quarter = parse_quarter_string(t)
    total_quarters = (year * 4 + quarter - 1) + n
    new_year = total_quarters // 4
    new_quarter = (total_quarters % 4) + 1
    return get_quarter_string(new_year, new_quarter)


def apply_renovation_delta(property_data: dict, delta: dict) -> dict:
    """Apply renovation deltas to property characteristics"""
    # Apply deltas with clamping to [0, 1]
    property_data["epc"] = max(0, min(1, property_data["epc"] + delta.get("epc", 0)))
    property_data["state"] = max(0, min(1, property_data["state"] + delta.get("state", 0)))
    property_data["kitchen"] = max(0, min(1, property_data["kitchen"] + delta.get("kitchen", 0)))
    property_data["bath"] = max(0, min(1, property_data["bath"] + delta.get("bath", 0)))

    # Apply surface percentage increase
    if delta.get("surfacePct", 0) > 0:
        property_data["surface"] *= 1 + delta["surfacePct"]

    return property_data


async def get_current_quarter(db) -> str:
    """Get the latest quarter from market index"""
    latest = await db.marketindex.find_one(sort=[("t", -1)])
    if not latest:
        return "2020-1"  # Default
    return latest["t"]


async def get_property_current_price(db, property_id: ObjectId, current_t: str) -> float:
    """Get current price of a property"""
    # Try to get from price history
    price_record = await db.pricehistory.find_one({"propertyId": property_id, "t": current_t})

    if price_record:
        return price_record["price"]

    # If not found, compute it
    property_data = await db.properties.find_one({"_id": property_id})
    market_index = await db.marketindex.find_one({"t": current_t})

    if not property_data or not market_index:
        return 0

    return compute_property_price(property_data, market_index)


async def get_property_current_prices(
    db, property_ids: list[ObjectId], current_t: str
) -> dict[ObjectId, float]:
    """Current price of several properties, in a bounded number of queries.

    Same answer as calling :func:`get_property_current_price` once per id, at a
    cost that does not grow with the list: one read of the price history for
    the whole set, then, only for the ids the history does not cover, one read
    of the properties and one of the market index.

    Complexity: 1 to 3 round trips and O(n) work in memory, for any n. The
    per-id version issues 1 to 3 round trips *each*, which is what made the
    portfolio pages cost more the more a player owned.

    Args:
        db: The database handle.
        property_ids: The properties to price. Duplicates are harmless.
        current_t: The quarter to price them at.

    Returns:
        A price per id. An id that can be neither read nor computed maps to 0,
        matching the single-property helper.
    """
    unique_ids = list(dict.fromkeys(property_ids))
    if not unique_ids:
        return {}

    prices: dict[ObjectId, float] = {}

    history = await db.pricehistory.find(
        {"propertyId": {"$in": unique_ids}, "t": current_t}
    ).to_list(length=None)
    for record in history:
        prices[record["propertyId"]] = record["price"]

    missing = [pid for pid in unique_ids if pid not in prices]
    if not missing:
        return prices

    market_index = await db.marketindex.find_one({"t": current_t})
    properties = await db.properties.find({"_id": {"$in": missing}}).to_list(length=None)

    by_id = {prop["_id"]: prop for prop in properties}
    for property_id in missing:
        property_data = by_id.get(property_id)
        if not property_data or not market_index:
            prices[property_id] = 0
        else:
            prices[property_id] = compute_property_price(property_data, market_index)

    return prices


async def generate_next_market_quarter(db, current_t: str) -> dict:
    """
    Generate market data for the next quarter based on the previous quarter
    with realistic drift and variations
    """
    next_t = add_quarters(current_t, 1)

    # Get current quarter data as baseline
    current_market = await db.marketindex.find_one({"t": current_t})

    if not current_market:
        # If no data exists, create initial realistic values
        inflation = 0.02
        rate = 0.015
        income = 0.01
        unemployment = 0.05
        confidence = 0.0
        policy = 0.0

        locals_data = []
        for zone in ZONES:
            locals_data.append(
                {
                    "zone": zone,
                    "access": round(random.uniform(-0.05, 0.05), 4),
                    "attract": round(random.uniform(-0.05, 0.05), 4),
                    "nuisance": round(random.uniform(0.0, 0.10), 4),
                    "tension": round(random.uniform(-0.02, 0.02), 4),
                }
            )
    else:
        # Apply realistic drift from current values
        inflation = current_market["inflation"] + random.uniform(-0.002, 0.002)
        rate = current_market["rate"] + random.uniform(-0.001, 0.001)
        income = current_market["income"] + random.uniform(-0.001, 0.001)
        unemployment = current_market["unemployment"] + random.uniform(-0.002, 0.002)
        confidence = current_market["confidence"] + random.uniform(-0.005, 0.005)
        policy = current_market["policy"] + random.uniform(-0.003, 0.003)

        # Clamp macro values to realistic ranges
        inflation = max(-0.05, min(0.10, inflation))
        rate = max(0.005, min(0.05, rate))
        income = max(-0.02, min(0.05, income))
        unemployment = max(0.02, min(0.15, unemployment))
        confidence = max(-0.10, min(0.10, confidence))
        policy = max(-0.05, min(0.05, policy))

        # Update local indices with drift AND zone-specific trends
        locals_data = []
        current_locals = {loc["zone"]: loc for loc in current_market["locals"]}

        for zone in ZONES:
            # Get zone-specific appreciation trend
            zone_trend = ZONE_TRENDS.get(zone, 0.002)  # Default +0.2%/quarter if not defined

            if zone in current_locals:
                current_loc = current_locals[zone]
                # Apply random drift (kept small to limit volatility) plus the structural trend
                access = current_loc["access"] + random.uniform(-0.002, 0.002)
                attract = current_loc["attract"] + random.uniform(-0.002, 0.002) + zone_trend
                nuisance = current_loc["nuisance"] + random.uniform(-0.001, 0.001)
                tension = (
                    current_loc["tension"] + random.uniform(-0.002, 0.002) + (zone_trend * 0.5)
                )
            else:
                access = random.uniform(-0.05, 0.05)
                attract = random.uniform(-0.05, 0.05) + zone_trend
                nuisance = random.uniform(0.0, 0.10)
                tension = random.uniform(-0.02, 0.02) + (zone_trend * 0.5)

            # Clamp local values
            access = max(-0.10, min(0.10, access))
            attract = max(-0.10, min(0.10, attract))
            nuisance = max(0.0, min(0.20, nuisance))
            tension = max(-0.10, min(0.10, tension))

            locals_data.append(
                {
                    "zone": zone,
                    "access": round(access, 4),
                    "attract": round(attract, 4),
                    "nuisance": round(nuisance, 4),
                    "tension": round(tension, 4),
                }
            )

    # Create new market index document
    new_market = {
        "t": next_t,
        "inflation": round(inflation, 4),
        "rate": round(rate, 4),
        "income": round(income, 4),
        "unemployment": round(unemployment, 4),
        "confidence": round(confidence, 4),
        "policy": round(policy, 4),
        "locals": locals_data,
    }

    # Insert into database
    await db.marketindex.insert_one(new_market)

    return new_market
