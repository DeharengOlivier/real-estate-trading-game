"""The listing query parameters are validated, not silently reinterpreted.

`sortBy=surfce` used to sort by price and answer 200, and `sortOrder=descending`
used to sort ascending, because both were free strings compared against a
couple of known values with a fall-through default. A caller with a typo got a
correct-looking page in the wrong order and no way to notice.

Everything entering the system is parsed into a validated type at the edge.
These tests hold that for the four parameters of /trading/listings.
"""

import pytest

from api.tests.conftest import api_client


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["price", "surface", "zone"])
async def test_the_documented_sort_fields_are_accepted(test_user_and_token, field):
    _, _, headers = test_user_and_token

    async with api_client() as client:
        response = await client.get(f"/trading/listings?sortBy={field}", headers=headers)

    assert response.status_code == 200, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["surfce", "priceX", "", "lastComputedPrice", "$where"])
async def test_an_unknown_sort_field_is_refused(test_user_and_token, field):
    """A typo, an internal field name, and an operator: all 422, none sorted by price."""
    _, _, headers = test_user_and_token

    async with api_client() as client:
        response = await client.get(f"/trading/listings?sortBy={field}", headers=headers)

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["asc", "desc"])
async def test_the_documented_sort_orders_are_accepted(test_user_and_token, order):
    _, _, headers = test_user_and_token

    async with api_client() as client:
        response = await client.get(f"/trading/listings?sortOrder={order}", headers=headers)

    assert response.status_code == 200, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["descending", "DESC", "1", "-1", ""])
async def test_an_unknown_sort_order_is_refused(test_user_and_token, order):
    """Including the spellings that look right: the API has one spelling each."""
    _, _, headers = test_user_and_token

    async with api_client() as client:
        response = await client.get(f"/trading/listings?sortOrder={order}", headers=headers)

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["page=0", "page=-1", "limit=0", "limit=201", "limit=100000"])
async def test_pagination_bounds_are_enforced(test_user_and_token, query):
    """A caller cannot ask for page zero, nor for more rows than the cap."""
    _, _, headers = test_user_and_token

    async with api_client() as client:
        response = await client.get(f"/trading/listings?{query}", headers=headers)

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_the_maximum_page_size_is_accepted(test_user_and_token):
    """The boundary itself is valid: 200 is the cap, not one past it."""
    _, _, headers = test_user_and_token

    async with api_client() as client:
        response = await client.get("/trading/listings?limit=200", headers=headers)

    assert response.status_code == 200, response.text
