"""
Pytest configuration and fixtures.

The test suite runs with NO external services: MongoDB is replaced by
``mongomock-motor`` (an in-memory async Motor-compatible client) and Redis by
``fakeredis``. Both are wired in by monkeypatching the connection helpers in
``api.database`` so the application code (and its ``get_database`` /
``get_redis_client`` accessors) work unchanged.
"""
import asyncio
import os
from datetime import datetime

# api.auth refuses to import without a usable SECRET_KEY, which is the point of
# the check. Provide one before anything imports the application. setdefault,
# not assignment: a developer running with a real key in their environment
# keeps it, and the suite still exercises the same code path.
os.environ.setdefault(
    "SECRET_KEY", "test-only-signing-key-do-not-use-outside-the-test-suite"
)

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient
import fakeredis.aioredis as fakeredis

import api.database as database
from api.auth import create_access_token, get_password_hash

# Reusable singletons for the whole test session. Keeping a single mongomock
# client means data inserted by a fixture is visible to the request handlers,
# while we reset collections between tests for isolation.
_mock_mongo_client = AsyncMongoMockClient()
_mock_db_name = "realestate_test"

# Collections that get wiped between tests.
_COLLECTIONS = [
    "users",
    "portfolios",
    "holdings",
    "trades",
    "properties",
    "listings",
    "marketindex",
    "renovations",
    "pricehistory",
]


# How long a lone arrival waits for a partner that is never coming. Short
# enough to keep the suite fast, long enough that a genuine second request
# would have arrived.
LONE_ARRIVAL_GRACE_SECONDS = 0.25


class Rendezvous:
    """Hold the first arrivals until ``party`` of them are inside.

    An arrival that waits out ``LONE_ARRIVAL_GRACE_SECONDS`` alone continues
    anyway, and this is deliberate: with the guards in place the loser of a
    race is refused *before* it reaches the rendezvous, so exactly one request
    ever gets here. Deadlocking on that would turn "the fix works" into a
    timeout. Reintroduce the read-check-write pattern and both requests arrive
    again, the wait ends immediately, and the battery goes red.
    """

    def __init__(self, party: int):
        self.party = party
        self.arrived = 0
        self.everybody_is_here = asyncio.Event()

    async def wait(self):
        self.arrived += 1
        if self.arrived >= self.party:
            self.everybody_is_here.set()
        try:
            await asyncio.wait_for(
                self.everybody_is_here.wait(), timeout=LONE_ARRIVAL_GRACE_SECONDS
            )
        except asyncio.TimeoutError:
            pass


async def _fake_connect_to_mongo():
    """Mongomock-backed replacement for api.database.connect_to_mongo.

    It creates the indexes too, because the constraints they carry are part of
    what the application is: a suite running without them would be testing a
    different database from the one that ships.
    """
    database.mongodb_client = _mock_mongo_client
    database.mongodb_db = _mock_mongo_client[_mock_db_name]
    await database.ensure_indexes(database.mongodb_db)


async def _fake_connect_to_redis():
    """fakeredis-backed replacement for api.database.connect_to_redis."""
    if database.redis_client is None:
        database.redis_client = fakeredis.FakeRedis(decode_responses=True)


async def _fake_close_mongo_connection():
    """No-op: keep the in-memory client alive across tests."""
    return None


async def _fake_close_redis_connection():
    """No-op: keep the in-memory Redis alive across tests."""
    return None


@pytest.fixture(scope="session", autouse=True)
def patch_external_services():
    """Patch the database/redis connection helpers for the whole session."""
    original = {
        "connect_to_mongo": database.connect_to_mongo,
        "connect_to_redis": database.connect_to_redis,
        "close_mongo_connection": database.close_mongo_connection,
        "close_redis_connection": database.close_redis_connection,
    }
    database.connect_to_mongo = _fake_connect_to_mongo
    database.connect_to_redis = _fake_connect_to_redis
    database.close_mongo_connection = _fake_close_mongo_connection
    database.close_redis_connection = _fake_close_redis_connection

    yield

    for name, fn in original.items():
        setattr(database, name, fn)


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the whole test session."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


async def _seed_baseline(db):
    """Insert a minimal, deterministic data set used by several tests.

    - A market index for "2020-1" covering every zone (so price computation and
      the current-quarter helpers work).
    - The full renovation catalog (several tests expect a non-empty catalog).

    Properties/listings are intentionally NOT seeded here so that tests which
    assert an exact item count stay deterministic; tests that need a property
    create their own.
    """
    from seed.constants import ZONES, RENOVATIONS

    locals_data = [
        {"zone": z, "access": 0.0, "attract": 0.0, "nuisance": 0.05, "tension": 0.0}
        for z in ZONES
    ]
    await db.marketindex.insert_one({
        "t": "2020-1",
        "inflation": 0.02,
        "rate": 0.015,
        "income": 0.01,
        "unemployment": 0.05,
        "confidence": 0.0,
        "policy": 0.0,
        "locals": locals_data,
    })

    await db.renovations.insert_many([dict(r) for r in RENOVATIONS])


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_database():
    """Reset and seed the in-memory database before each test."""
    await database.connect_to_mongo()
    await database.connect_to_redis()

    db = database.get_database()
    for name in _COLLECTIONS:
        await db[name].delete_many({})

    # Reset the fakeredis store and the in-memory rate-limit fallback so each
    # test starts from a clean slate.
    if database.redis_client is not None:
        await database.redis_client.flushall()
    from api.routers import auth as auth_router
    auth_router.fallback_login_attempts.clear()

    await _seed_baseline(db)

    yield

    # Nothing to tear down: collections are reset on the next setup.


@pytest_asyncio.fixture
async def test_user_and_token():
    """Create a test user (with admin role) and return creds + JWT headers."""
    db = database.get_database()

    password = "TestPassword123"
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "name": "Test User",
        "hashedPassword": get_password_hash(password),
        "roles": ["user", "admin"],
        "createdAt": datetime.utcnow(),
    }

    result = await db.users.insert_one(user_data)
    user_id = result.inserted_id

    await db.portfolios.insert_one({
        "userId": user_id,
        "cash": 1000000.0,
        "createdAt": datetime.utcnow(),
    })

    token = create_access_token(data={"sub": str(user_id)})
    headers = {"Authorization": f"Bearer {token}"}

    return {
        "username": "testuser",
        "password": password,
        "user_id": user_id,
    }, token, headers


@pytest_asyncio.fixture
async def ordinary_user_and_token():
    """Create a player with no admin role and return creds + JWT headers.

    This is the fixture every negative permission test uses: a perfectly valid,
    fully authenticated account that simply has no business touching the admin
    surface. Authentication and authorization are different questions, and only
    a user like this one can tell them apart.
    """
    db = database.get_database()

    password = "PlayerPassword123"
    result = await db.users.insert_one({
        "username": "player",
        "email": "player@example.com",
        "name": "Ordinary Player",
        "hashedPassword": get_password_hash(password),
        "roles": ["user"],
        "createdAt": datetime.utcnow(),
    })
    user_id = result.inserted_id

    await db.portfolios.insert_one({
        "userId": user_id,
        "cash": 1000000.0,
        "createdAt": datetime.utcnow(),
    })

    token = create_access_token(data={"sub": str(user_id)})
    return (
        {"username": "player", "password": password, "user_id": user_id},
        token,
        {"Authorization": f"Bearer {token}"},
    )


@pytest_asyncio.fixture
async def legacy_user_and_token():
    """Create a user document with no ``roles`` key at all.

    Accounts created before the role field existed have no ``roles``. They must
    be treated as ordinary players, never as admins: a missing permission is an
    absent permission, not a wildcard.
    """
    db = database.get_database()

    result = await db.users.insert_one({
        "username": "legacy",
        "email": "legacy@example.com",
        "name": "Legacy User",
        "hashedPassword": get_password_hash("LegacyPassword123"),
        "createdAt": datetime.utcnow(),
    })
    user_id = result.inserted_id

    await db.portfolios.insert_one({
        "userId": user_id,
        "cash": 1000000.0,
        "createdAt": datetime.utcnow(),
    })

    token = create_access_token(data={"sub": str(user_id)})
    return (
        {"username": "legacy", "user_id": user_id},
        token,
        {"Authorization": f"Bearer {token}"},
    )
