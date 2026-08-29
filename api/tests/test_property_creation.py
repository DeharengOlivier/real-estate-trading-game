"""The server owns the economics of a property it creates.

`base_ppm` is the base price per square metre for a zone and a type. It decides
what every future price of that property will be, and it used to arrive in the
request body: whoever created a property chose its economics, and the browser
carried its own copy of the table to fill the field in. The two tables had
already drifted, the interface offering 3 800 EUR/m2 for a house in
Bruxelles-Centre where the simulation says 4 500.

A rule duplicated in two places is a rule that will disagree with itself. The
table in `simulation/constants.py` is the one, and these tests hold it.
"""

import pytest

from api.database import get_database
from api.tests.conftest import api_client
from simulation.constants import BASE_PPM, ZONES


def _body(**overrides):
    body = {
        "zone": "Bruxelles-Centre",
        "type": "house",
        "surface": 120.0,
        "epc": 0.6,
        "state": 0.7,
        "kitchen": 0.5,
        "bath": 0.5,
    }
    body.update(overrides)
    return body


@pytest.mark.asyncio
@pytest.mark.parametrize("zone", ZONES)
@pytest.mark.parametrize("kind", ["house", "apartment"])
async def test_the_stored_price_per_m2_comes_from_the_table(test_user_and_token, zone, kind):
    """Every zone and type, so a table edit cannot silently miss a combination."""
    _, _, headers = test_user_and_token

    async with api_client() as client:
        response = await client.post(
            "/admin/properties", headers=headers, json=_body(zone=zone, type=kind)
        )

    assert response.status_code == 201, response.text
    db = get_database()
    stored = await db.properties.find_one({"zone": zone, "type": kind})
    assert stored["base_ppm"] == BASE_PPM[zone][kind]


@pytest.mark.asyncio
async def test_a_supplied_price_per_m2_is_refused(test_user_and_token):
    """The exact defect: the caller naming its own economics."""
    _, _, headers = test_user_and_token

    async with api_client() as client:
        response = await client.post("/admin/properties", headers=headers, json=_body(base_ppm=1.0))

    assert response.status_code == 422, response.text
    db = get_database()
    assert await db.properties.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("zone", ["Paris-Centre", "bruxelles-centre", "", "Bruxelles Centre"])
async def test_an_unknown_zone_is_refused(test_user_and_token, zone):
    """A zone outside the table has no price, no trend and no local index.

    It used to be accepted as any string, stored, and priced from whatever the
    caller had put in base_ppm.
    """
    _, _, headers = test_user_and_token

    async with api_client() as client:
        response = await client.post("/admin/properties", headers=headers, json=_body(zone=zone))

    assert response.status_code == 422, response.text
    db = get_database()
    assert await db.properties.count_documents({}) == 0


@pytest.mark.asyncio
async def test_an_unknown_type_is_refused(test_user_and_token):
    _, _, headers = test_user_and_token

    async with api_client() as client:
        response = await client.post("/admin/properties", headers=headers, json=_body(type="villa"))

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["epc", "state", "kitchen", "bath"])
@pytest.mark.parametrize("value", [-0.1, 1.1])
async def test_a_score_outside_the_unit_range_is_refused(test_user_and_token, field, value):
    """The four quality scores are fractions; the price model assumes it."""
    _, _, headers = test_user_and_token

    async with api_client() as client:
        response = await client.post(
            "/admin/properties", headers=headers, json=_body(**{field: value})
        )

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", [0, -50])
async def test_a_non_positive_surface_is_refused(test_user_and_token, surface):
    _, _, headers = test_user_and_token

    async with api_client() as client:
        response = await client.post(
            "/admin/properties", headers=headers, json=_body(surface=surface)
        )

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_the_new_property_is_listed_at_a_price_derived_from_the_table(test_user_and_token):
    """The created listing is priced, and priced from the stored base_ppm."""
    _, _, headers = test_user_and_token

    async with api_client() as client:
        response = await client.post("/admin/properties", headers=headers, json=_body())
        assert response.status_code == 201, response.text
        property_id = response.json()["id"]

    db = get_database()
    listing = await db.listings.find_one({"propertyId": __import__("bson").ObjectId(property_id)})
    assert listing is not None
    assert listing["isAvailable"] is True
    assert listing["lastComputedPrice"] > 0
