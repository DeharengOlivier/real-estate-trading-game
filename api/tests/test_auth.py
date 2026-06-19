"""
Tests for authentication endpoints
"""
import pytest
from httpx import AsyncClient
from api.main import app
from api.database import get_database
import api.database as database


@pytest.mark.asyncio
async def test_register_user_success():
    """Test successful user registration"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/auth/register", json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "SecurePass123",
            "name": "New User"
        })
        
        assert response.status_code == 201  # Changed from 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["username"] == "newuser"
        assert data["user"]["email"] == "newuser@example.com"


@pytest.mark.asyncio
async def test_register_weak_password():
    """Test registration with weak password fails"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/auth/register", json={
            "username": "weakuser",
            "email": "weak@example.com",
            "password": "weak",  # Too short, no uppercase, no digit
            "name": "Weak User"
        })
        
        assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_register_duplicate_username():
    """Test registration with existing username fails"""
    db = get_database()
    
    # First registration
    async with AsyncClient(app=app, base_url="http://test") as client:
        await client.post("/auth/register", json={
            "username": "duplicate",
            "email": "first@example.com",
            "password": "SecurePass123",
            "name": "First User"
        })
        
        # Try to register again with same username
        response = await client.post("/auth/register", json={
            "username": "duplicate",
            "email": "second@example.com",
            "password": "SecurePass456",
            "name": "Second User"
        })
        
        assert response.status_code == 409  # 409 Conflict is correct for duplicate
        # Check that error message mentions username
        assert "username" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_success(test_user_and_token):
    """Test successful login"""
    user_data, token, headers = test_user_and_token
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/auth/login", json={
            "username": user_data["username"],
            "password": user_data["password"]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["username"] == user_data["username"]


@pytest.mark.asyncio
async def test_login_wrong_password():
    """Test login with incorrect password"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # First create a user
        await client.post("/auth/register", json={
            "username": "testlogin",
            "email": "testlogin@example.com",
            "password": "CorrectPass123",
            "name": "Test Login"
        })
        
        # Try to login with wrong password
        response = await client.post("/auth/login", json={
            "username": "testlogin",
            "password": "WrongPass123"
        })
        
        assert response.status_code == 401
        assert "incorrect" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_nonexistent_user():
    """Test login with non-existent username"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/auth/login", json={
            "username": "nonexistent",
            "password": "AnyPass123"
        })
        
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_rate_limiting_on_login():
    """Test that login endpoint is rate limited"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Make multiple failed login attempts
        for i in range(6):  # MAX_LOGIN_ATTEMPTS is 5
            response = await client.post("/auth/login", json={
                "username": "ratelimit",
                "password": "WrongPass123"
            })
            
            if i < 5:
                # First 5 attempts should get 401 or 429 (depending on IP tracking)
                assert response.status_code in [401, 429]
            else:
                # 6th attempt should be rate limited
                assert response.status_code == 429
                assert "too many" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_protected_endpoint_without_token():
    """Test that protected endpoints require authentication"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/portfolio/summary")
        
        # FastAPI returns 403 when credentials are not provided
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_protected_endpoint_with_invalid_token():
    """Test that protected endpoints reject invalid tokens"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/portfolio/summary",
            headers={"Authorization": "Bearer invalid_token_here"}
        )
        
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_with_valid_token(test_user_and_token):
    """Test that protected endpoints work with valid tokens"""
    user_data, token, headers = test_user_and_token

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/portfolio/summary", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert "cash" in data
        assert "totalValue" in data


@pytest.mark.asyncio
async def test_me_returns_current_user(test_user_and_token):
    """The /auth/me endpoint returns the authenticated user's profile."""
    user_data, token, headers = test_user_and_token

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/auth/me", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == user_data["username"]
        assert data["id"] == str(user_data["user_id"])
        assert "cashBalance" in data
        assert "roles" in data


@pytest.mark.asyncio
async def test_register_then_login_roundtrip():
    """A freshly registered user can immediately log in."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        register = await client.post("/auth/register", json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "SecurePass123",
            "name": "New User",
        })
        assert register.status_code == 201

        login = await client.post("/auth/login", json={
            "username": "newuser",
            "password": "SecurePass123",
        })
        assert login.status_code == 200
        assert login.json()["user"]["username"] == "newuser"


@pytest.mark.asyncio
async def test_rate_limiting_fallback_without_redis(monkeypatch):
    """Rate limiting also trips on the in-memory fallback path (no Redis)."""
    # Force the Redis-less code path.
    monkeypatch.setattr(database, "redis_client", None)

    async with AsyncClient(app=app, base_url="http://test") as client:
        statuses = []
        for _ in range(6):
            response = await client.post("/auth/login", json={
                "username": "ratelimit", "password": "WrongPass123"
            })
            statuses.append(response.status_code)

    assert statuses[-1] == 429
    assert statuses[0] == 401


@pytest.mark.asyncio
async def test_rate_limit_is_per_username():
    """Hitting the limit for one user does not block a different user."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        for _ in range(6):
            await client.post("/auth/login", json={
                "username": "ratelimit", "password": "WrongPass123"
            })
        # A different username is still allowed (gets 401, not 429).
        response = await client.post("/auth/login", json={
            "username": "otheruser", "password": "WrongPass123"
        })
        assert response.status_code == 401
