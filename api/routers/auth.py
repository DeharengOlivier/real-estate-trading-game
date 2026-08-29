"""
Authentication router - Handles user registration, login, and profile
Single Responsibility: User authentication and authorization
"""

import logging
import time
from collections import defaultdict
from datetime import timedelta
from itertools import count

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pymongo.errors import DuplicateKeyError

from api.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    DEFAULT_ROLES,
    authenticate_user,
    create_access_token,
    get_current_user,
    get_password_hash,
)
from api.clock import utc_now
from api.database import get_database, get_redis_client
from api.models import Token, UserLogin, UserRegister
from api.observability import log_security_event
from simulation.constants import INITIAL_CASH

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])

# Constants for rate limiting
LOGIN_ATTEMPT_LIMIT = 5
LOGIN_ATTEMPT_TIMEFRAME = 300  # 5 minutes in seconds

# Registration is the more expensive of the two calls: it hashes a password
# with bcrypt and inserts a user and a portfolio holding the starting cash.
# Keyed on the caller's address rather than the username, because the username
# on a registration is whatever the caller has just invented, so limiting per
# username limits nobody.
REGISTRATION_LIMIT = 5
REGISTRATION_TIMEFRAME = 3600  # 1 hour in seconds

fallback_login_attempts: defaultdict[str, list[float]] = defaultdict(list)

# Monotonic counter used to build unique sorted-set members so that several
# attempts within the same second are counted individually (the score still
# carries the timestamp used for time-window pruning).
_attempt_sequence = count()


async def enforce_rate_limit(
    bucket: str, subject: str, limit: int, window: int, detail: str
) -> bool:
    """Count one attempt in a sliding window, and refuse past `limit`.

    `bucket` names what is being limited and keeps counters apart: a caller
    that has used up its registrations still has its login attempts. `subject`
    is what the count is per: a username for login, a client address for
    registration.

    The Redis path is the real one. The in-memory fallback exists so a stack
    without Redis is limited rather than unlimited, but it counts per process:
    with several workers or replicas each keeps its own tally, so a deployment
    that means it needs Redis present rather than optional.
    """
    redis = get_redis_client()
    now = time.time()
    key = f"{bucket}:{subject}"

    if redis is None:
        attempts = [t for t in fallback_login_attempts[key] if now - t < window]
        attempts.append(now)
        fallback_login_attempts[key] = attempts

        if len(attempts) > limit:
            log_security_event(
                logger, "rate_limit_reached", bucket=bucket, subject=subject, store="memory"
            )
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)
        return True

    # Use a unique member per attempt (timestamp + monotonic counter) so that
    # multiple attempts within the same second are not collapsed into a single
    # sorted-set entry. The score stays as the timestamp for window pruning.
    member = f"{now:.6f}:{next(_attempt_sequence)}"

    async with redis.pipeline(transaction=True) as pipe:
        # Drop what has fallen out of the window, record this attempt, let the
        # key expire on its own, and read the count back, in one round trip.
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zadd(key, {member: now})
        pipe.expire(key, window)
        pipe.zcard(key)

        results = await pipe.execute()

    if results[-1] > limit:
        log_security_event(
            logger, "rate_limit_reached", bucket=bucket, subject=subject, store="redis"
        )
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)

    return True


async def check_rate_limit(username: str) -> bool:
    """Bound login attempts per username."""
    return await enforce_rate_limit(
        "login_attempts",
        username,
        LOGIN_ATTEMPT_LIMIT,
        LOGIN_ATTEMPT_TIMEFRAME,
        "Too many login attempts. Try again in 5 minutes.",
    )


def caller_address(request: Request) -> str:
    """The address to key a per-caller limit on.

    `request.client` is the peer of the TCP connection, which is the caller
    when the API is reached directly and the proxy when it is not. A deployment
    behind a proxy has to run uvicorn with --proxy-headers and a trusted
    forwarded-allow-ips, so that the peer is resolved from the forwarding
    headers by something that knows which proxy to believe. Reading
    X-Forwarded-For here instead would let any caller choose its own key, and
    with it its own limit.
    """
    return request.client.host if request.client else "unknown"


async def check_registration_rate_limit(request: Request) -> bool:
    """Bound account creation per calling address."""
    return await enforce_rate_limit(
        "registrations",
        caller_address(request),
        REGISTRATION_LIMIT,
        REGISTRATION_TIMEFRAME,
        "Too many accounts created from this address. Try again later.",
    )


def _duplicated_field(conflict: DuplicateKeyError) -> str:
    """Name the field a unique index refused, for the message to the caller.

    Falls back to "Account" when the driver does not report a key pattern, so a
    conflict is never reported as an empty sentence.
    """
    key_pattern = (conflict.details or {}).get("keyPattern") or {}
    for field in key_pattern:
        return field.capitalize()
    return "Account"


async def _cash_of(db, user_id) -> float:
    """Read a user's balance from the portfolio, the only thing that holds it.

    Trading moves ``portfolios.cash`` and nothing else. Any second copy of the
    number is stale from the first purchase onwards, so there is no second copy
    to read: this is the one place the balance comes from.
    """
    portfolio = await db.portfolios.find_one({"userId": user_id})
    return portfolio["cash"] if portfolio else 0.0


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister, request: Request):
    """
    Register a new user

    Creates a new user with:
    - Unique username
    - Strong password (hashed with bcrypt)
    - A portfolio holding the starting cash
    - Default role: "user"

    Bounded per calling address, before any of that work is done.
    """
    # First, so a refused caller pays for no bcrypt hash and leaves no user
    # and no portfolio behind.
    await check_registration_rate_limit(request)

    db = get_database()

    # The password rule is stated once, on UserRegister, and enforced before
    # this function is entered: a request that gets here has already passed it.

    # A courtesy check, not the guarantee. It exists so the common case gets a
    # clear message without paying for a bcrypt hash; the unique index below is
    # what actually stops two people owning one username, because two requests
    # can both find nothing here.
    existing_user = await db.users.find_one({"username": user_data.username})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username already registered"
        )

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
        "createdAt": utc_now(),
    }

    try:
        result = await db.users.insert_one(user_doc)
    except DuplicateKeyError as conflict:
        # The index refused it: somebody else took the name or the address
        # between the check above and this line, or in the same instant.
        field = _duplicated_field(conflict)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"{field} already registered"
        ) from conflict

    user_id = result.inserted_id

    # Create portfolio for the new user
    portfolio_data = {
        "userId": user_id,
        "cash": float(INITIAL_CASH),
        "createdAt": utc_now(),
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
            "roles": list(DEFAULT_ROLES),
        },
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
        # Both halves of a wrong login land here, on purpose: telling the
        # caller which one was wrong tells them which usernames exist.
        log_security_event(logger, "authentication_failed", username=user_data.username)
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
            "roles": user.get("roles", list(DEFAULT_ROLES)),
        },
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
        "roles": current_user.get("roles", list(DEFAULT_ROLES)),
    }
