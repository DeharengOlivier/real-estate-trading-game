"""
Database connection and utilities
"""
import os
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
import redis.asyncio as redis

# MongoDB client
mongodb_client: Optional[AsyncIOMotorClient] = None
mongodb_db = None

# Redis client (optional)
redis_client = None


async def connect_to_mongo():
    """Connect to MongoDB"""
    global mongodb_client, mongodb_db
    
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    mongodb_db_name = os.getenv("MONGODB_DB", "realestate")
    
    mongodb_client = AsyncIOMotorClient(mongodb_url)
    mongodb_db = mongodb_client[mongodb_db_name]
    
    print(f"✓ Connected to MongoDB: {mongodb_db_name}")


async def connect_to_redis():
    """Connect to Redis (optional, for caching)"""
    global redis_client
    
    try:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        redis_client = await redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        await redis_client.ping()
        print(f"✓ Connected to Redis")
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
