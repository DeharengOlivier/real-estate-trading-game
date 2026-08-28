"""The account the seed prints must be an account you can actually log into.

The seed wrote the password under `password_hash` while authentication reads
`hashedPassword`, so logging in as the demo user raised KeyError inside the
handler and answered 500. The seed still printed the credentials as if they
worked, and nothing in the suite ever tried them: the seed ran against a real
MongoDB and the tests ran against an in-memory one, so the two never met.

They meet here. The demo user is created by the same function the seed calls,
against the in-memory database, and then logs in through the real endpoint.
"""
import pytest
from httpx import AsyncClient

from api.database import get_database
from api.main import app
from seed.seed_realestate import (
    DEMO_PASSWORD,
    DEMO_USERNAME,
    create_demo_user,
)


@pytest.mark.asyncio
async def test_the_seeded_account_can_log_in():
    db = get_database()
    await create_demo_user(db)

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/auth/login", json={
            "username": DEMO_USERNAME,
            "password": DEMO_PASSWORD,
        })

    assert response.status_code == 200, response.text
    assert response.json()["access_token"]


@pytest.mark.asyncio
async def test_the_token_the_seeded_account_receives_identifies_it():
    db = get_database()
    await create_demo_user(db)

    async with AsyncClient(app=app, base_url="http://test") as client:
        login = await client.post("/auth/login", json={
            "username": DEMO_USERNAME,
            "password": DEMO_PASSWORD,
        })
        token = login.json()["access_token"]
        me = await client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"}
        )

    assert me.status_code == 200
    assert me.json()["username"] == DEMO_USERNAME


@pytest.mark.asyncio
async def test_the_wrong_password_is_still_refused():
    """A login that accepts everything would pass the test above too."""
    db = get_database()
    await create_demo_user(db)

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/auth/login", json={
            "username": DEMO_USERNAME,
            "password": DEMO_PASSWORD + "wrong",
        })

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_the_seeded_account_can_reach_the_admin_surface():
    """The seed exists to demonstrate the application, admin pages included."""
    db = get_database()
    await create_demo_user(db)

    async with AsyncClient(app=app, base_url="http://test") as client:
        login = await client.post("/auth/login", json={
            "username": DEMO_USERNAME,
            "password": DEMO_PASSWORD,
        })
        token = login.json()["access_token"]
        response = await client.get(
            "/admin/renovations", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_the_seeded_account_stores_its_password_where_login_reads_it():
    """Names the defect directly, so a rename cannot quietly reintroduce it."""
    db = get_database()
    await create_demo_user(db)

    user = await db.users.find_one({"username": DEMO_USERNAME})
    assert "hashedPassword" in user
    assert user["hashedPassword"] != DEMO_PASSWORD
