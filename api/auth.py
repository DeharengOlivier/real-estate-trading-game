"""
Authentication utilities for Real Estate Simulation
Simple JWT-based authentication
"""

import os
from datetime import datetime, timedelta

import bcrypt
from bson import ObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from api.database import get_database

# Configuration
# HS256 signs with the key itself, so the key is the whole secret: anyone
# holding it can mint a token for any user id. 256 bits is the floor.
MINIMUM_SECRET_KEY_LENGTH = 32

# Values that have shipped in this repository, in .env.example or in
# docker-compose.yml. They are published, so they are not secrets.
PUBLISHED_PLACEHOLDER_KEYS = frozenset(
    {
        "change-me-please",
        "change-me-in-production",
        "please-set-secret-key-in-env-file",
        "your-secret-key",
        "secret",
    }
)

_KEY_HELP = (
    "Set SECRET_KEY to at least "
    f"{MINIMUM_SECRET_KEY_LENGTH} characters of random material. Generate one "
    "with:\n"
    "    openssl rand -hex 32\n"
    "or, without openssl:\n"
    '    python -c "import secrets; print(secrets.token_hex(32))"'
)


def _read_secret_key() -> str:
    """Read the JWT signing key from the environment, or refuse to start.

    There is deliberately no default. A fallback key turns a forgotten
    environment variable into a fully working API whose tokens anyone reading
    this repository can forge, and nothing about the running system would look
    wrong. Failing here means the mistake is visible at the first start rather
    than after the first breach.

    Raises:
        RuntimeError: The variable is unset, blank, too short, or one of the
            placeholder values published in this repository.
    """
    raw = os.getenv("SECRET_KEY", "").strip()

    if not raw:
        raise RuntimeError(f"SECRET_KEY is not set. {_KEY_HELP}")

    if raw in PUBLISHED_PLACEHOLDER_KEYS:
        raise RuntimeError(
            f"SECRET_KEY is set to {raw!r}, a placeholder published in this "
            f"repository. Anyone can forge a token with it. {_KEY_HELP}"
        )

    if len(raw) < MINIMUM_SECRET_KEY_LENGTH:
        raise RuntimeError(
            f"SECRET_KEY is {len(raw)} characters, below the "
            f"{MINIMUM_SECRET_KEY_LENGTH} required. {_KEY_HELP}"
        )

    return raw


SECRET_KEY = _read_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# The two roles the game knows about. Every account gets PLAYER_ROLE at
# registration; ADMIN_ROLE is granted out of band and is never accepted from a
# request body.
PLAYER_ROLE = "user"
ADMIN_ROLE = "admin"
DEFAULT_ROLES = [PLAYER_ROLE]

# HTTP Bearer token scheme
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    """Hash a password"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency resolving the bearer token to the user document it names.

    This answers "who is calling", and nothing else. Entitlement is a separate
    question, asked by :func:`require_admin`.

    Every way the token can be wrong (bad signature, expired, no subject, a
    subject that is not an object id, an account that no longer exists) is the
    same answer to the caller: 401. In particular the subject is parsed before
    it reaches the database, because ``ObjectId("not-an-id")`` raises
    ``InvalidId`` and an unguarded parse turns a bad credential into a 500.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        # `from None`: a caller with a bad token learns their token is bad, and
        # nothing about why the library rejected it.
        raise credentials_exception from None

    if not ObjectId.is_valid(user_id):
        raise credentials_exception

    db = get_database()
    user = await db.users.find_one({"_id": ObjectId(user_id)})

    if user is None:
        raise credentials_exception

    return user


def has_role(user: dict, role: str) -> bool:
    """Whether ``user`` carries ``role``.

    A user document with no ``roles`` key predates the field. It is read as
    holding no role at all: an absent permission is an absent permission, never
    a wildcard, so an old account cannot silently become an administrator.
    """
    return role in user.get("roles", [])


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency admitting only users carrying the ``admin`` role.

    Used on the endpoints that change the shared world (the property and
    renovation catalogs, the game clock) or read across every player's data.
    Authentication alone is not enough for any of them: an ordinary player
    holds a perfectly valid token.
    """
    if not has_role(current_user, ADMIN_ROLE):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation requires the admin role",
        )
    return current_user


async def authenticate_user(username: str, password: str) -> dict | None:
    """Authenticate a user by username and password"""
    db = get_database()
    user = await db.users.find_one({"username": username})

    if not user:
        return None

    if not verify_password(password, user["hashedPassword"]):
        return None

    return user
