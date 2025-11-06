"""
Pytest configuration and fixtures
"""
import pytest
import pytest_asyncio
import asyncio
from datetime import datetime
from bson import ObjectId
import os

from api.database import connect_to_mongo, close_mongo_connection, get_database
from api.auth import create_access_token, get_password_hash


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_database():
    """Setup database connection before each test"""
    await connect_to_mongo()
    
    yield
    
    # Cleanup test data after each test
    db = get_database()
    if db is not None:
        # Clean up test users created during tests
        await db.users.delete_many({"username": {"$regex": "^(testuser|newuser|weakuser|duplicate|testlogin|ratelimit)"}})
        await db.portfolios.delete_many({})
        await db.holdings.delete_many({})
        await db.trades.delete_many({})
        # Clean up test data from tests
        await db.properties.delete_many({"zone": {"$in": ["Test Zone", "Update Test", "Delete Test", "Bruxelles-Centre", "Ixelles", "Gand-Centre", "Namur-Centre", "Liège-Centre"]}})
        await db.listings.delete_many({})
        await db.marketindex.delete_many({"t": {"$regex": "^2020-"}})
        await db.renovations.delete_many({"code": {"$regex": "^TEST_"}})
        await db.pricehistory.delete_many({})
    
    await close_mongo_connection()


@pytest_asyncio.fixture
async def test_user_and_token():
    """Create a test user and return user data with JWT token"""
    db = get_database()
    
    # Create test user with hashed password and ADMIN role
    password = "TestPassword123"
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "name": "Test User",
        "hashedPassword": get_password_hash(password),
        "cashBalance": 1000000.0,
        "roles": ["user", "admin"],  # Added admin role for tests
        "createdAt": datetime.utcnow()
    }
    
    result = await db.users.insert_one(user_data)
    user_id = result.inserted_id
    
    # Create portfolio for user
    portfolio_data = {
        "userId": user_id,
        "cash": 1000000.0,
        "createdAt": datetime.utcnow()
    }
    await db.portfolios.insert_one(portfolio_data)
    
    # Generate JWT token
    token = create_access_token(data={"sub": str(user_id)})
    headers = {"Authorization": f"Bearer {token}"}
    
    # Return user credentials and token info
    return {
        "username": "testuser",
        "password": password,
        "user_id": user_id
    }, token, headers
