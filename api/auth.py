"""
Authentication utilities for Real Estate Simulation
Simple JWT-based authentication
"""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import bcrypt
from bson import ObjectId
import os

from api.database import get_database

# Configuration
# Read secret from environment (fallback for dev only)
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-please")
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
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def get_password_hash(password: str) -> str:
    """Hash a password"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
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

    Every way the token can be wrong (bad signature, expired, no subject, an
    account that no longer exists) is the same answer to the caller: 401.
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


async def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Authenticate a user by username and password"""
    db = get_database()
    user = await db.users.find_one({"username": username})
    
    if not user:
        return None
    
    if not verify_password(password, user["hashedPassword"]):
        return None
    
    return user
