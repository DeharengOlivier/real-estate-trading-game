"""
Authentication router - Handles user registration, login, and profile
Single Responsibility: User authentication and authorization
"""
from fastapi import APIRouter, HTTPException, Depends, status
from datetime import datetime, timedelta
from collections import defaultdict
from itertools import count
import time
import logging

from api.database import get_database, get_redis_client
from seed.constants import INITIAL_CASH
from api.models import UserRegister, UserLogin, Token
from api.auth import (
    create_access_token, get_password_hash, authenticate_user,
    get_current_user, ACCESS_TOKEN_EXPIRE_MINUTES, DEFAULT_ROLES
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])

# Constants for rate limiting
LOGIN_ATTEMPT_LIMIT = 5
LOGIN_ATTEMPT_TIMEFRAME = 300  # 5 minutes in seconds
fallback_login_attempts = defaultdict(list)

# Monotonic counter used to build unique sorted-set members so that several
# attempts within the same second are counted individually (the score still
# carries the timestamp used for time-window pruning).
_attempt_sequence = count()


async def check_rate_limit(username: str) -> bool:
    """Check if a user has exceeded login rate limits using Redis"""
    redis = get_redis_client()
    now = time.time()

    if redis is None:
        # Fallback to in-memory rate limiting if Redis is unavailable
        attempts = [t for t in fallback_login_attempts[username] if now - t < LOGIN_ATTEMPT_TIMEFRAME]
        attempts.append(now)
        fallback_login_attempts[username] = attempts

        if len(attempts) > LOGIN_ATTEMPT_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Try again in 5 minutes."
            )
        return True

    key = f"login_attempts:{username}"

    # Use a unique member per attempt (timestamp + monotonic counter) so that
    # multiple attempts within the same second are not collapsed into a single
    # sorted-set entry. The score stays as the timestamp for window pruning.
    member = f"{now:.6f}:{next(_attempt_sequence)}"

    # Start a transaction
    async with redis.pipeline(transaction=True) as pipe:
        # Remove timestamps older than the timeframe
        pipe.zremrangebyscore(key, 0, now - LOGIN_ATTEMPT_TIMEFRAME)
        # Add the current login attempt
        pipe.zadd(key, {member: now})
        # Set an expiration on the key to auto-clean old data
        pipe.expire(key, LOGIN_ATTEMPT_TIMEFRAME)
        # Get the count of recent attempts
        pipe.zcard(key)

        results = await pipe.execute()

    attempt_count = results[-1]

    if attempt_count > LOGIN_ATTEMPT_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again in 5 minutes."
        )

    return True


def validate_password_strength(password: str) -> None:
    """
    Validate password strength
    Requirements:
    - At least 8 characters
    - Contains uppercase and lowercase
    - Contains a number
    """
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long"
        )
    
    if not any(c.isupper() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one uppercase letter"
        )
    
    if not any(c.islower() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one lowercase letter"
        )
    
    if not any(c.isdigit() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one number"
        )


async def _cash_of(db, user_id) -> float:
    """Read a user's balance from the portfolio, the only thing that holds it.

    Trading moves ``portfolios.cash`` and nothing else. Any second copy of the
    number is stale from the first purchase onwards, so there is no second copy
    to read: this is the one place the balance comes from.
    """
    portfolio = await db.portfolios.find_one({"userId": user_id})
    return portfolio["cash"] if portfolio else 0.0


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister):
    """
    Register a new user
    
    Creates a new user with:
    - Unique username
    - Strong password (hashed with bcrypt)
    - A portfolio holding the starting cash
    - Default role: "user"
    """
    db = get_database()
    
    # Validate password strength
    validate_password_strength(user_data.password)
    
    # Check if username already exists
    existing_user = await db.users.find_one({"username": user_data.username})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already registered"
        )
    
    # Hash password
    hashed_password = get_password_hash(user_data.password)
    
    # Create user document
    # The role is decided here, by the server, and never read from the request
    # body: a registration payload carrying "roles" is ignored by UserRegister,
    # which has no such field.
    user_doc = {
        "username": user_data.username,
        "email": user_data.email,
        "name": user_data.name,
        "hashedPassword": hashed_password,
        "roles": list(DEFAULT_ROLES),
        "createdAt": datetime.utcnow()
    }
    
    result = await db.users.insert_one(user_doc)
    user_id = result.inserted_id
    
    # Create portfolio for the new user
    portfolio_data = {
        "userId": user_id,
        "cash": float(INITIAL_CASH),
        "createdAt": datetime.utcnow()
    }
    await db.portfolios.insert_one(portfolio_data)
    
    logger.info(f"New user registered: {user_data.username}")
    
    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user_id)}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user_id),
            "username": user_data.username,
            "email": user_data.email,
            "name": user_data.name,
            "cashBalance": float(INITIAL_CASH),
            "roles": list(DEFAULT_ROLES)
        }
    }


@router.post("/login", response_model=Token)
async def login(user_data: UserLogin):
    """
    Login a user
    - Rate limited to 5 attempts per 5 minutes
    - Authenticates user
    - Returns JWT token
    """
    # Check rate limit before hitting the database
    await check_rate_limit(user_data.username)
    
    user = await authenticate_user(user_data.username, user_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # Generate JWT token
    access_token = create_access_token(data={"sub": str(user["_id"])})
    
    logger.info(f"User logged in: {user_data.username}")
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user["_id"]),
            "username": user["username"],
            "email": user.get("email", ""),
            "name": user.get("name", ""),
            "cashBalance": await _cash_of(get_database(), user["_id"]),
            "roles": user.get("roles", list(DEFAULT_ROLES))
        }
    }


@router.get("/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """
    Get current logged-in user information
    
    Returns:
    - User ID
    - Username
    - Cash balance
    - Roles
    """
    return {
        "id": str(current_user["_id"]),
        "username": current_user["username"],
        "cashBalance": await _cash_of(get_database(), current_user["_id"]),
        "roles": current_user.get("roles", list(DEFAULT_ROLES))
    }
