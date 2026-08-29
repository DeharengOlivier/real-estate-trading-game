"""What must always be true is enforced by the database, not by an if.

Registration checked for an existing username with find_one and then inserted.
Two requests that overlap both find nothing and both insert: the account name
that the login endpoint looks up with find_one is then ambiguous, and which of
the two people owns it depends on insertion order.

An application-level check is advisory. A unique index is the constraint.
"""

import asyncio

import pytest

import api.routers.auth as auth_router
from api.database import get_database
from api.tests.conftest import Rendezvous, api_client


class _HoldAfterUserLookup:
    """Wrap a collection so that a lookup does not return until its twin has
    also looked. Everything else is forwarded untouched."""

    def __init__(self, collection, rendezvous):
        self._collection = collection
        self._rendezvous = rendezvous

    def __getattr__(self, name):
        return getattr(self._collection, name)

    async def find_one(self, *args, **kwargs):
        result = await self._collection.find_one(*args, **kwargs)
        await self._rendezvous.wait()
        return result


class _DatabaseHoldingUserLookups:
    """A database whose ``users`` collection holds its lookups."""

    def __init__(self, db, rendezvous):
        self._db = db
        self._rendezvous = rendezvous

    def __getattr__(self, name):
        if name == "users":
            return _HoldAfterUserLookup(self._db.users, self._rendezvous)
        return getattr(self._db, name)

    def __getitem__(self, name):
        if name == "users":
            return _HoldAfterUserLookup(self._db["users"], self._rendezvous)
        return self._db[name]


@pytest.fixture
def overlap_two_registrations(monkeypatch):
    """Make two registrations pass the duplicate check before either inserts.

    That check is a find_one on users, and the insert follows it. Holding both
    requests until both have looked reproduces exactly the window the check
    leaves open, rather than hoping two requests happen to overlap there.
    """
    rendezvous = Rendezvous(party=2)
    real_get_database = auth_router.get_database

    def held_database():
        return _DatabaseHoldingUserLookups(real_get_database(), rendezvous)

    monkeypatch.setattr(auth_router, "get_database", held_database)
    return rendezvous


async def _register(client, username, email=None):
    return await client.post(
        "/auth/register",
        json={
            "username": username,
            "email": email or f"{username}@example.com",
            "name": "Somebody",
            "password": "SomePassword123",
        },
    )


@pytest.mark.asyncio
async def test_the_username_carries_a_unique_index():
    db = get_database()
    indexes = await db.users.index_information()

    unique_on_username = [
        spec for spec in indexes.values() if spec.get("unique") and spec["key"] == [("username", 1)]
    ]
    assert unique_on_username, f"no unique index on username: {indexes}"


@pytest.mark.asyncio
async def test_the_email_carries_a_unique_index():
    db = get_database()
    indexes = await db.users.index_information()

    unique_on_email = [
        spec for spec in indexes.values() if spec.get("unique") and spec["key"] == [("email", 1)]
    ]
    assert unique_on_email, f"no unique index on email: {indexes}"


@pytest.mark.asyncio
async def test_two_overlapping_registrations_produce_one_account(
    overlap_two_registrations,
):
    """The check and the insert are two operations; the constraint is one."""
    async with api_client() as client:
        responses = await asyncio.gather(
            _register(client, "twin"),
            _register(client, "twin"),
        )

    db = get_database()
    assert await db.users.count_documents({"username": "twin"}) == 1
    assert sorted(r.status_code for r in responses) == [201, 409]


@pytest.mark.asyncio
async def test_the_losing_registration_leaves_no_portfolio_behind(
    overlap_two_registrations,
):
    """A refused registration must not leave an orphan portfolio funded."""
    async with api_client() as client:
        await asyncio.gather(
            _register(client, "twin"),
            _register(client, "twin"),
        )

    db = get_database()
    assert await db.portfolios.count_documents({}) == 1


@pytest.mark.asyncio
async def test_a_duplicate_email_is_refused_too():
    async with api_client() as client:
        first = await _register(client, "alice", email="shared@example.com")
        second = await _register(client, "bob", email="shared@example.com")

    assert first.status_code == 201
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_a_sequential_duplicate_still_says_what_is_wrong():
    async with api_client() as client:
        await _register(client, "taken")
        second = await _register(client, "taken")

    assert second.status_code == 409
    assert "already" in second.json()["detail"].lower()


@pytest.mark.asyncio
async def test_two_different_names_both_register():
    """The constraint must refuse the duplicate without refusing the ordinary."""
    async with api_client() as client:
        responses = await asyncio.gather(
            _register(client, "one"),
            _register(client, "two"),
        )

    assert [r.status_code for r in responses] == [201, 201]
    db = get_database()
    assert await db.users.count_documents({}) == 2
    assert await db.portfolios.count_documents({}) == 2
