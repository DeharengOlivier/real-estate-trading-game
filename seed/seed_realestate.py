"""
Seed script for Real Estate Simulation
Generates initial data for MongoDB with reproducible random values
"""
import os
import sys
import random
import math
from datetime import datetime
from typing import List, Dict
import asyncio

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from motor.motor_asyncio import AsyncIOMotorClient
import numpy as np
from seed.constants import *


def get_quarter_string(year: int, quarter: int) -> str:
    """Convert year and quarter to string format YYYY-Q"""
    return f"{year}-{quarter}"


def parse_quarter_string(t: str) -> tuple[int, int]:
    """Parse quarter string to (year, quarter)"""
    year, q = t.split('-')
    return int(year), int(q)


def add_quarters(t: str, n: int) -> str:
    """Add n quarters to a quarter string"""
    year, quarter = parse_quarter_string(t)
    total_quarters = (year * 4 + quarter - 1) + n
    new_year = total_quarters // 4
    new_quarter = (total_quarters % 4) + 1
    return get_quarter_string(new_year, new_quarter)


def compute_macro_index(market_index: Dict) -> float:
    """
    Compute MacroIndex(t) from market data
    
    MacroIndex(t) = exp(
        a_inf*inflation - a_rate*rate + a_inc*income
        - a_unemp*unemployment + a_conf*confidence + a_pol*policy
    )
    """
    exponent = (
        A_INF * market_index['inflation']
        - A_RATE * market_index['rate']
        + A_INC * market_index['income']
        - A_UNEMP * market_index['unemployment']
        + A_CONF * market_index['confidence']
        + A_POL * market_index['policy']
    )
    return math.exp(exponent)


def compute_local_index(local_data: Dict) -> float:
    """
    Compute LocalIndex(zone, t) from local data
    
    LocalIndex(z,t) = exp(
        b_acc*access + b_attr*attract - b_nui*nuisance + b_tens*tension
    )
    """
    exponent = (
        B_ACC * local_data['access']
        + B_ATTR * local_data['attract']
        - B_NUI * local_data['nuisance']
        + B_TENS * local_data['tension']
    )
    return math.exp(exponent)


def compute_property_price(
    property_data: Dict,
    market_index: Dict,
    add_noise: bool = True
) -> float:
    """
    Compute property price at quarter t
    
    price_b(t) = base_ppm * surface
                 * (1 + w_epc*EPC) * (1 + w_state*State)
                 * (1 + w_kitchen*Kitchen) * (1 + w_bath*Bath)
                 * MacroIndex(t) * LocalIndex(zone, t) * Noise(t)
    """
    # Base price
    base_price = property_data['base_ppm'] * property_data['surface']
    
    # Property characteristics multipliers
    char_multiplier = (
        (1 + W_EPC * property_data['epc']) *
        (1 + W_STATE * property_data['state']) *
        (1 + W_KITCHEN * property_data['kitchen']) *
        (1 + W_BATH * property_data['bath'])
    )
    
    # Macro index
    macro_idx = compute_macro_index(market_index)
    
    # Local index
    local_data = None
    for loc in market_index['locals']:
        if loc['zone'] == property_data['zone']:
            local_data = loc
            break
    
    if not local_data:
        raise ValueError(f"No local data for zone {property_data['zone']}")
    
    local_idx = compute_local_index(local_data)
    
    # Noise
    noise = 1.0
    if add_noise:
        eps = np.random.normal(0, SIGMA_NOISE)
        noise = math.exp(eps)
    
    price = base_price * char_multiplier * macro_idx * local_idx * noise
    return max(0, price)  # Ensure non-negative


def generate_properties(num: int) -> List[Dict]:
    """Generate random properties"""
    properties = []
    
    for i in range(num):
        zone = random.choice(ZONES)
        prop_type = random.choice(["house", "apartment"])
        
        # Surface: apartments 50-200m², houses 80-350m²
        if prop_type == "apartment":
            surface = random.uniform(50, 200)
        else:
            surface = random.uniform(80, 350)
        
        # Random characteristics [0,1]
        epc = random.uniform(0.2, 0.9)
        state = random.uniform(0.3, 0.95)
        kitchen = random.uniform(0.2, 0.9)
        bath = random.uniform(0.2, 0.9)
        
        base_ppm = BASE_PPM[zone][prop_type]
        
        properties.append({
            "zone": zone,
            "type": prop_type,
            "surface": round(surface, 2),
            "epc": round(epc, 3),
            "state": round(state, 3),
            "kitchen": round(kitchen, 3),
            "bath": round(bath, 3),
            "base_ppm": base_ppm,
            "createdAt": datetime.utcnow()
        })
    
    return properties


def generate_market_indices(num_quarters: int, start_year: int, start_quarter: int) -> List[Dict]:
    """Generate market indices for num_quarters with slow drift and low noise"""
    indices = []
    
    # Initial values (normalized around 0 for factors in exp)
    inflation = 0.02
    rate = 0.015
    income = 0.01
    unemployment = 0.05
    confidence = 0.0
    policy = 0.0
    
    # Local initial values
    local_init = {zone: {
        'access': random.uniform(-0.05, 0.05),
        'attract': random.uniform(-0.05, 0.05),
        'nuisance': random.uniform(0.0, 0.10),
        'tension': random.uniform(-0.02, 0.02)
    } for zone in ZONES}
    
    year = start_year
    quarter = start_quarter
    
    for q in range(num_quarters):
        t = get_quarter_string(year, quarter)
        
        # Slow drift with small noise
        inflation += random.uniform(-0.002, 0.002)
        rate += random.uniform(-0.001, 0.001)
        income += random.uniform(-0.001, 0.001)
        unemployment += random.uniform(-0.002, 0.002)
        confidence += random.uniform(-0.005, 0.005)
        policy += random.uniform(-0.003, 0.003)
        
        # Clamp values
        inflation = max(-0.05, min(0.10, inflation))
        rate = max(0.005, min(0.05, rate))
        income = max(-0.02, min(0.05, income))
        unemployment = max(0.02, min(0.15, unemployment))
        confidence = max(-0.10, min(0.10, confidence))
        policy = max(-0.05, min(0.05, policy))
        
        # Local indices
        locals_data = []
        for zone in ZONES:
            loc = local_init[zone]
            # Slow drift
            loc['access'] += random.uniform(-0.005, 0.005)
            loc['attract'] += random.uniform(-0.005, 0.005)
            loc['nuisance'] += random.uniform(-0.003, 0.003)
            loc['tension'] += random.uniform(-0.005, 0.005)
            
            # Clamp
            loc['access'] = max(-0.10, min(0.10, loc['access']))
            loc['attract'] = max(-0.10, min(0.10, loc['attract']))
            loc['nuisance'] = max(0.0, min(0.20, loc['nuisance']))
            loc['tension'] = max(-0.10, min(0.10, loc['tension']))
            
            locals_data.append({
                'zone': zone,
                'access': round(loc['access'], 4),
                'attract': round(loc['attract'], 4),
                'nuisance': round(loc['nuisance'], 4),
                'tension': round(loc['tension'], 4)
            })
        
        indices.append({
            't': t,
            'inflation': round(inflation, 4),
            'rate': round(rate, 4),
            'income': round(income, 4),
            'unemployment': round(unemployment, 4),
            'confidence': round(confidence, 4),
            'policy': round(policy, 4),
            'locals': locals_data
        })
        
        # Next quarter
        quarter += 1
        if quarter > 4:
            quarter = 1
            year += 1
    
    return indices


async def seed_database():
    """Main seed function"""
    print("🌱 Starting seed process...")
    
    # Set random seeds
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    
    # Connect to MongoDB
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    mongodb_db = os.getenv("MONGODB_DB", "realestate")
    
    print(f"📦 Connecting to MongoDB: {mongodb_url}")
    client = AsyncIOMotorClient(mongodb_url)
    db = client[mongodb_db]
    
    # Drop existing collections
    print("🗑️  Dropping existing collections...")
    collections = ['users', 'properties', 'marketindex', 'listings', 
                   'portfolios', 'holdings', 'renovations', 'trades', 'pricehistory']
    for coll in collections:
        await db[coll].drop()
    
    # 1. Create demo user with password
    print("👤 Creating demo user...")
    # Import password hashing
    import bcrypt
    
    password_hash = bcrypt.hashpw("demo123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    user = {
        "username": "demo",
        "email": "demo@realestate.be",
        "name": "Demo User",
        "password_hash": password_hash,
        "createdAt": datetime.utcnow()
    }
    user_result = await db.users.insert_one(user)
    user_id = user_result.inserted_id
    print(f"   ✓ User created: {user_id} (username: demo, password: demo123)")
    
    # 2. Generate properties
    print(f"🏠 Generating {NUM_PROPERTIES} properties...")
    properties = generate_properties(NUM_PROPERTIES)
    props_result = await db.properties.insert_many(properties)
    property_ids = props_result.inserted_ids
    print(f"   ✓ {len(property_ids)} properties created")
    
    # 3. Generate market indices
    print(f"📊 Generating {NUM_QUARTERS} quarters of market data...")
    market_indices = generate_market_indices(NUM_QUARTERS, START_YEAR, START_QUARTER)
    await db.marketindex.insert_many(market_indices)
    print(f"   ✓ {len(market_indices)} market indices created")
    
    # 4. Create renovations catalog
    print("🔨 Creating renovations catalog...")
    renovations = []
    for reno in RENOVATIONS:
        renovations.append({
            "code": reno['code'],
            "label": reno['label'],
            "cost": reno['cost'],
            "durationQ": reno['durationQ'],
            "delta": reno['delta']
        })
    await db.renovations.insert_many(renovations)
    print(f"   ✓ {len(renovations)} renovation types created")
    
    # 5. Create portfolio
    print("💰 Creating demo portfolio...")
    portfolio = {
        "userId": user_id,
        "cash": INITIAL_CASH,
        "createdAt": datetime.utcnow()
    }
    portfolio_result = await db.portfolios.insert_one(portfolio)
    portfolio_id = portfolio_result.inserted_id
    print(f"   ✓ Portfolio created with {INITIAL_CASH:,.0f} €")
    
    # 6. Compute price history for all properties and all quarters
    print("💵 Computing price history...")
    price_history = []
    
    # Fetch all properties for pricing
    all_properties = await db.properties.find().to_list(length=None)
    prop_dict = {str(p['_id']): p for p in all_properties}
    
    for market_idx in market_indices:
        t = market_idx['t']
        
        for prop_id, prop in prop_dict.items():
            price = compute_property_price(prop, market_idx, add_noise=True)
            price_history.append({
                "propertyId": prop['_id'],
                "t": t,
                "price": round(price, 2)
            })
    
    await db.pricehistory.insert_many(price_history)
    print(f"   ✓ {len(price_history)} price records created")
    
    # 7. Create listings (all properties available at start)
    print("📋 Creating market listings...")
    listings = []
    
    # Get first quarter
    first_t = get_quarter_string(START_YEAR, START_QUARTER)
    
    # Get first quarter prices
    first_prices = await db.pricehistory.find({"t": first_t}).to_list(length=None)
    price_map = {str(p['propertyId']): p['price'] for p in first_prices}
    
    for prop_id in property_ids:
        listings.append({
            "propertyId": prop_id,
            "isAvailable": True,
            "lastComputedPrice": price_map.get(str(prop_id), 0),
            "lastT": first_t
        })
    
    await db.listings.insert_many(listings)
    print(f"   ✓ {len(listings)} listings created")
    
    # 8. Create indices
    print("🔍 Creating database indices...")
    await db.properties.create_index([("zone", 1), ("type", 1)])
    await db.marketindex.create_index("t", unique=True)
    await db.listings.create_index("isAvailable")
    await db.holdings.create_index("portfolioId")
    await db.trades.create_index([("portfolioId", 1), ("ts", -1)])
    await db.pricehistory.create_index([("propertyId", 1), ("t", 1)])
    print("   ✓ Indices created")
    
    print("\n✅ Seed completed successfully!")
    print(f"   • {len(property_ids)} properties")
    print(f"   • {len(market_indices)} market quarters")
    print(f"   • {len(renovations)} renovation types")
    print(f"   • 1 portfolio with {INITIAL_CASH:,.0f} €")
    print(f"   • {len(price_history)} price history records")
    
    client.close()


if __name__ == "__main__":
    asyncio.run(seed_database())
