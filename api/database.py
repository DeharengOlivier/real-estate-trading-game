"""
Database connection and utilities
"""

import os
from typing import Any

import redis.asyncio as redis
from motor.motor_asyncio import AsyncIOMotorClient

# MongoDB client and database. Motor exports AsyncIOMotorClient as a value
# rather than a class a type checker can use, so the handles are held loosely
# and the code around them stays checked.
mongodb_client: Any = None
mongodb_db: Any = None

# Redis client (optional)
redis_client = None


async def connect_to_mongo():
    """Connect to MongoDB"""
    global mongodb_client, mongodb_db

    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    mongodb_db_name = os.getenv("MONGODB_DB", "realestate")

    mongodb_client = AsyncIOMotorClient(mongodb_url)
    mongodb_db = mongodb_client[mongodb_db_name]

    await ensure_indexes(mongodb_db)

    print(f"✓ Connected to MongoDB: {mongodb_db_name}")


async def ensure_indexes(db) -> None:
    """Create the indexes the application depends on, if they are missing.

    Two kinds live here, and they are not interchangeable:

    - the unique ones are *constraints*. `find_one` then `insert_one` is
      advisory, because two requests can both find nothing; the index is what
      actually makes a username belong to one person.
    - the others exist for the query patterns the routers issue.

    createIndex is idempotent, so this runs on every start. It is called here
    rather than only in the seed, because a database that was never seeded, or
    was seeded by an older version, must still get them.
    """
    await db.users.create_index("username", unique=True)
    await db.users.create_index("email", unique=True)
    await db.portfolios.create_index("userId", unique=True)
    await db.properties.create_index([("zone", 1), ("type", 1)])
    await db.marketindex.create_index("t", unique=True)
    await db.listings.create_index("propertyId", unique=True)
    await db.listings.create_index("isAvailable")
    await db.holdings.create_index("portfolioId")
    await db.holdings.create_index([("portfolioId", 1), ("propertyId", 1)], unique=True)
    await db.trades.create_index([("portfolioId", 1), ("ts", -1)])
    await db.pricehistory.create_index([("propertyId", 1), ("t", 1)])


async def connect_to_redis():
    """Connect to Redis (optional, for caching)"""
    global redis_client

    try:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        redis_client = await redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        await redis_client.ping()
        print("✓ Connected to Redis")
    except Exception as e:
        print(f"⚠ Redis connection failed (optional): {e}")
        redis_client = None


async def close_mongo_connection():
    """Close MongoDB connection"""
    global mongodb_client
    if mongodb_client:
        mongodb_client.close()
        print("✓ MongoDB connection closed")


async def close_redis_connection():
    """Close Redis connection"""
    global redis_client
    if redis_client:
        await redis_client.close()
        print("✓ Redis connection closed")


def get_database():
    """Get MongoDB database instance"""
    return mongodb_db


def get_redis():
    """Get Redis client instance (legacy helper)"""
    return redis_client


def get_redis_client():
    """Alias for get_redis to provide explicit naming"""
    return redis_client
