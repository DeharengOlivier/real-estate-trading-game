"""An identifier that is not an identifier is a bad request, never a crash.

Every request that carries a MongoDB object id (in the path, in the body, or
inside a token) reaches ``ObjectId(...)`` sooner or later, and that constructor
raises ``bson.errors.InvalidId`` on anything malformed. Left unguarded the
exception escapes the handler, the global handler turns it into a 500, and the
caller learns that their input travelled further into the system than it should
have. Ids are parsed at the boundary instead, so past the boundary an id is an
id.
"""
import pytest
from bson import ObjectId
from httpx import AsyncClient
from jose import jwt

from api.auth import ALGORITHM, SECRET_KEY
from api.main import app

MALFORMED_IDS = [
    "not-an-object-id",
    "",
    "12345",
    "zzzzzzzzzzzzzzzzzzzzzzzz",  # right length, not hexadecimal
    "../../etc/passwd",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", MALFORMED_IDS)
async def test_buying_a_malformed_property_id_is_a_client_error(
    test_user_and_token, malformed
):
    _, _, headers = test_user_and_token

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/trading/buy", headers=headers, json={"propertyId": malformed}
        )

    assert response.status_code < 500, response.text
    assert response.status_code in (400, 404, 422)


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", MALFORMED_IDS)
async def test_selling_a_malformed_property_id_is_a_client_error(
    test_user_and_token, malformed
):
    _, _, headers = test_user_and_token

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/trading/sell", headers=headers, json={"propertyId": malformed}
        )

    assert response.status_code < 500, response.text
    assert response.status_code in (400, 404, 422)


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", MALFORMED_IDS)
async def test_renovating_a_malformed_holding_id_is_a_client_error(
    test_user_and_token, malformed
):
    _, _, headers = test_user_and_token

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/game/renovate",
            headers=headers,
            json={"holdingId": malformed, "renoCode": "R_KITCHEN"},
        )

    assert response.status_code < 500, response.text
    assert response.status_code in (400, 404, 422)


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", MALFORMED_IDS)
async def test_a_malformed_token_subject_answers_401_not_500(malformed):
    """The subject comes from a signed token, so it is trusted input that is
    still attacker-chosen whenever the signing key leaks or a test key is used.
    """
    token = jwt.encode({"sub": malformed}, SECRET_KEY, algorithm=ALGORITHM)

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", MALFORMED_IDS)
async def test_a_malformed_property_id_in_a_chart_path_is_a_client_error(
    test_user_and_token, malformed
):
    _, _, headers = test_user_and_token
    if not malformed or "/" in malformed:
        pytest.skip("not addressable as a single path segment")

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            f"/charts/property/{malformed}", headers=headers
        )

    assert response.status_code == 400, response.text


@pytest.mark.asyncio
async def test_a_well_formed_but_unknown_id_is_still_a_clean_404(
    test_user_and_token,
):
    """Well formed and absent must stay distinguishable from malformed."""
    _, _, headers = test_user_and_token

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/trading/buy", headers=headers, json={"propertyId": str(ObjectId())}
        )

    assert response.status_code == 404
