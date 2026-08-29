"""
Health check router - System health and status endpoints
Single Responsibility: Monitor system health and dependencies
"""
import logging

from fastapi import APIRouter

from api.database import get_database, get_redis

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """
    Health check endpoint

    Verifies:
    - MongoDB connection
    - Redis connection
    - API responsiveness

    Returns:
    - Overall status
    - Individual service statuses
    - Timestamp
    """
    from datetime import datetime

    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": {}
    }

    # Check MongoDB
    try:
        db = get_database()
        await db.command("ping")
        health_status["dependencies"]["mongodb"] = "connected"
    except Exception as e:
        logger.error(f"MongoDB health check failed: {e}")
        health_status["dependencies"]["mongodb"] = "disconnected"
        health_status["status"] = "unhealthy"

    # Check Redis
    try:
        redis = get_redis()
        await redis.ping()
        health_status["dependencies"]["redis"] = "connected"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        health_status["dependencies"]["redis"] = "disconnected"
        health_status["status"] = "degraded"

    return health_status
