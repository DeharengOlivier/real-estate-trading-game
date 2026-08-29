"""Negative permission tests: authentication is not authorization.

Every endpoint that changes the shared world, or reads data belonging to
somebody else, is exercised here with a valid token that must not be enough.
A permission path only ever walked by the permitted user has not been tested.

The battery covers three separate ways a caller can be wrong:

- authenticated but not entitled (an ordinary player on the admin surface);
- entitled by omission (a user document written before ``roles`` existed);
- not authenticated at all (missing, forged, expired or malformed token).
"""

from datetime import datetime, timedelta

import jwt
import pytest
from bson import ObjectId

from api.auth import ALGORITHM, SECRET_KEY, create_access_token
from api.database import get_database
from api.tests.conftest import api_client

# Every write on the admin surface, as (method, path, json body).
# The path placeholders are filled in per test with a real id where one is
# needed; the authorization check must fire before the resource is looked up,
# so a syntactically valid id that does not exist is enough.
ADMIN_ENDPOINTS = [
    (
        "post",
        "/admin/properties",
        {
            "zone": "Bruxelles-Centre",
            "type": "house",
            "surface": 120,
            "epc": 0.6,
            "state": 0.7,
            "kitchen": 0.6,
            "bath": 0.6,
            "base_ppm": 3000,
        },
    ),
    ("get", "/admin/properties", None),
    ("get", "/admin/properties/{property_id}", None),
    ("put", "/admin/properties/{property_id}", {"surface": 130}),
    ("delete", "/admin/properties/{property_id}", None),
    (
        "post",
        "/admin/renovations",
        {
            "code": "TEST_RENO",
            "label": "Test renovation",
            "cost": 10000,
            "durationQ": 2,
            "delta": {"state": 0.1},
        },
    ),
    ("get", "/admin/renovations", None),
    ("put", "/admin/renovations/R_KITCHEN", {"cost": 1}),
    ("delete", "/admin/renovations/R_KITCHEN", None),
    ("get", "/admin/trades", None),
]


async def _call(client, method, path, body, headers):
    """Issue one request, passing a JSON body only where the verb takes one."""
    if body is None:
        return await getattr(client, method)(path, headers=headers)
    return await getattr(client, method)(path, headers=headers, json=body)


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,body", ADMIN_ENDPOINTS)
async def test_ordinary_player_is_refused_on_every_admin_endpoint(
    ordinary_user_and_token, method, path, body
):
    """A registered player holds a valid token and still may not administer."""
    _, _, headers = ordinary_user_and_token
    path = path.format(property_id=str(ObjectId()))

    async with api_client() as client:
        response = await _call(client, method, path, body, headers)

    assert response.status_code == 403, f"{method.upper()} {path} let an ordinary player through"


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,body", ADMIN_ENDPOINTS)
async def test_a_user_without_the_roles_field_is_refused(legacy_user_and_token, method, path, body):
    """A missing permission is an absent permission, never a wildcard."""
    _, _, headers = legacy_user_and_token
    path = path.format(property_id=str(ObjectId()))

    async with api_client() as client:
        response = await _call(client, method, path, body, headers)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_an_admin_still_gets_through(test_user_and_token):
    """The gate must refuse the player without also refusing the administrator."""
    _, _, headers = test_user_and_token

    async with api_client() as client:
        response = await client.post(
            "/admin/properties",
            headers=headers,
            json={
                "zone": "Bruxelles-Centre",
                "type": "house",
                "surface": 120,
                "epc": 0.6,
                "state": 0.7,
                "kitchen": 0.6,
                "bath": 0.6,
                "base_ppm": 3000,
            },
        )

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_an_ordinary_player_cannot_read_everybody_elses_trades(
    ordinary_user_and_token, test_user_and_token
):
    """/admin/trades is a cross-tenant read: it must never answer a player."""
    _, _, player_headers = ordinary_user_and_token
    admin_user, _, _ = test_user_and_token

    db = get_database()
    portfolio = await db.portfolios.find_one({"userId": admin_user["user_id"]})
    await db.trades.insert_one(
        {
            "portfolioId": portfolio["_id"],
            "propertyId": ObjectId(),
            "side": "buy",
            "price": 250000.0,
            "fees": 6250.0,
            "quarter": "2020-1",
        }
    )

    async with api_client() as client:
        response = await client.get("/admin/trades", headers=player_headers)

    assert response.status_code == 403
    assert "250000" not in response.text


@pytest.mark.asyncio
async def test_an_ordinary_player_cannot_advance_the_game_clock(
    ordinary_user_and_token,
):
    """Advancing the quarter rewrites the world for every player at once."""
    _, _, headers = ordinary_user_and_token

    async with api_client() as client:
        response = await client.post("/game/advance-quarter", headers=headers)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_the_clock_did_not_move_when_the_player_was_refused(
    ordinary_user_and_token,
):
    """A refused call must leave no trace: no new quarter, no new prices."""
    db = get_database()
    quarters_before = await db.marketindex.count_documents({})
    _, _, headers = ordinary_user_and_token

    async with api_client() as client:
        await client.post("/game/advance-quarter", headers=headers)

    assert await db.marketindex.count_documents({}) == quarters_before


@pytest.mark.asyncio
async def test_an_admin_can_still_advance_the_game_clock(test_user_and_token):
    _, _, headers = test_user_and_token

    async with api_client() as client:
        response = await client.post("/game/advance-quarter", headers=headers)

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_registration_persists_the_role_it_reports():
    """The role returned by /auth/register must exist in the stored document.

    Reporting a field the database does not hold is how a permission model ends
    up decorative: every later read falls back to a default and the check that
    was supposed to use it silently passes.
    """
    async with api_client() as client:
        response = await client.post(
            "/auth/register",
            json={
                "username": "freshplayer",
                "email": "fresh@example.com",
                "name": "Fresh Player",
                "password": "FreshPassword123",
            },
        )

    assert response.status_code == 201
    assert response.json()["user"]["roles"] == ["user"]

    db = get_database()
    stored = await db.users.find_one({"username": "freshplayer"})
    assert stored["roles"] == ["user"]


@pytest.mark.asyncio
async def test_a_freshly_registered_player_cannot_administer():
    """The full path, end to end: register, then try the admin surface."""
    async with api_client() as client:
        registration = await client.post(
            "/auth/register",
            json={
                "username": "sneaky",
                "email": "sneaky@example.com",
                "name": "Sneaky Player",
                "password": "SneakyPassword123",
            },
        )
        token = registration.json()["access_token"]

        response = await client.delete(
            f"/admin/properties/{ObjectId()}",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_a_player_cannot_grant_themselves_a_role_at_registration():
    """The role is assigned by the server, never accepted from the request."""
    async with api_client() as client:
        response = await client.post(
            "/auth/register",
            json={
                "username": "selfpromoted",
                "email": "selfpromoted@example.com",
                "name": "Self Promoted",
                "password": "SelfPromoted123",
                "roles": ["user", "admin"],
            },
        )

    assert response.status_code == 201

    db = get_database()
    stored = await db.users.find_one({"username": "selfpromoted"})
    assert stored["roles"] == ["user"]


# --- the token itself -------------------------------------------------------


@pytest.mark.asyncio
async def test_a_token_signed_with_another_key_is_refused(test_user_and_token):
    """A forged signature is an authentication failure, not an admin."""
    user_data, _, _ = test_user_and_token
    # As long as the real key: an attacker forging a token would use a
    # plausible one, and a short key only makes PyJWT warn about the test.
    forged = jwt.encode(
        {"sub": str(user_data["user_id"])},
        "not-the-real-key-but-just-as-long-as-one",
        algorithm=ALGORITHM,
    )

    async with api_client() as client:
        response = await client.get("/admin/trades", headers={"Authorization": f"Bearer {forged}"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_a_token_with_no_subject_is_refused():
    token = jwt.encode({"nothing": "here"}, SECRET_KEY, algorithm=ALGORITHM)

    async with api_client() as client:
        response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_a_token_for_a_deleted_user_is_refused():
    """The account can disappear while its token is still inside its lifetime."""
    db = get_database()
    result = await db.users.insert_one(
        {
            "username": "ghost",
            "email": "ghost@example.com",
            "name": "Ghost",
            "hashedPassword": "irrelevant",
            "roles": ["user", "admin"],
        }
    )
    token = create_access_token(data={"sub": str(result.inserted_id)})
    await db.users.delete_one({"_id": result.inserted_id})

    async with api_client() as client:
        response = await client.get("/admin/trades", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_an_expired_token_is_refused(test_user_and_token):
    user_data, _, _ = test_user_and_token
    expired = create_access_token(
        data={"sub": str(user_data["user_id"])},
        expires_delta=timedelta(minutes=-5),
    )

    async with api_client() as client:
        response = await client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})

    assert response.status_code == 401


# --- authentication and authorization answer different questions ------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/admin/trades"),
        ("post", "/game/advance-quarter"),
        ("get", "/portfolio/summary"),
    ],
)
async def test_no_credential_is_401_and_a_wrong_one_is_403(ordinary_user_and_token, method, path):
    """Two different refusals, and they must stay different.

    A caller with no Authorization header has not said who they are: 401, with
    the challenge. A caller holding a valid token who lacks the role has said
    who they are and been refused: 403. Collapsing the two tells an anonymous
    caller they are forbidden, and an unauthorised one that their credentials
    were not understood.
    """
    _, _, headers = ordinary_user_and_token

    async with api_client() as client:
        anonymous = await getattr(client, method)(path)
        identified = await getattr(client, method)(path, headers=headers)

    assert anonymous.status_code == 401
    assert anonymous.headers.get("www-authenticate")
    # /portfolio/summary is a player endpoint, so an ordinary player is allowed
    # in; the admin ones refuse them.
    assert identified.status_code in (200, 403)
    if path.startswith("/admin") or path == "/game/advance-quarter":
        assert identified.status_code == 403


@pytest.mark.asyncio
async def test_a_player_cannot_renovate_somebody_elses_property(
    test_user_and_token, ordinary_user_and_token
):
    """Ownership is checked per resource, and here is the test that tries it.

    /game/renovate is the one endpoint that resolves the holding to a portfolio
    and compares it to the caller. Nothing exercised that path with the wrong
    caller, so the check could have been deleted without a single test noticing.

    The refusal is a 404 rather than a 403, matching /trading/sell: a 403 would
    tell the caller that the holding id it guessed is a real one.
    """
    owner, _, _ = test_user_and_token
    _, _, intruder_headers = ordinary_user_and_token

    db = get_database()
    portfolio = await db.portfolios.find_one({"userId": owner["user_id"]})
    renovation = await db.renovations.find_one({})
    prop = await db.properties.insert_one(
        {
            "zone": "Bruxelles-Centre",
            "type": "house",
            "surface": 100,
            "epc": 0.5,
            "state": 0.5,
            "kitchen": 0.5,
            "bath": 0.5,
            "base_ppm": 3000,
        }
    )
    holding = await db.holdings.insert_one(
        {
            "portfolioId": portfolio["_id"],
            "propertyId": prop.inserted_id,
            "buyPrice": 250_000.0,
            "buyDate": datetime(2020, 1, 1),
            "works": [],
        }
    )

    async with api_client() as client:
        response = await client.post(
            "/game/renovate",
            headers=intruder_headers,
            json={
                "holdingId": str(holding.inserted_id),
                "renoCode": renovation["code"],
            },
        )

    assert response.status_code == 404

    # And nothing happened: no work queued, no money moved.
    stored = await db.holdings.find_one({"_id": holding.inserted_id})
    assert stored["works"] == []
    owner_portfolio = await db.portfolios.find_one({"_id": portfolio["_id"]})
    assert owner_portfolio["cash"] == pytest.approx(portfolio["cash"])


@pytest.mark.asyncio
async def test_the_owner_can_renovate_their_own_property(test_user_and_token):
    """The ownership check must refuse the intruder without refusing the owner."""
    owner, _, headers = test_user_and_token

    db = get_database()
    portfolio = await db.portfolios.find_one({"userId": owner["user_id"]})
    renovation = await db.renovations.find_one({})
    prop = await db.properties.insert_one(
        {
            "zone": "Bruxelles-Centre",
            "type": "house",
            "surface": 100,
            "epc": 0.5,
            "state": 0.5,
            "kitchen": 0.5,
            "bath": 0.5,
            "base_ppm": 3000,
        }
    )
    holding = await db.holdings.insert_one(
        {
            "portfolioId": portfolio["_id"],
            "propertyId": prop.inserted_id,
            "buyPrice": 250_000.0,
            "buyDate": datetime(2020, 1, 1),
            "works": [],
        }
    )

    async with api_client() as client:
        response = await client.post(
            "/game/renovate",
            headers=headers,
            json={
                "holdingId": str(holding.inserted_id),
                "renoCode": renovation["code"],
            },
        )

    assert response.status_code == 200, response.text
    stored = await db.holdings.find_one({"_id": holding.inserted_id})
    assert len(stored["works"]) == 1
