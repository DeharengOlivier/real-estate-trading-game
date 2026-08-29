"""
Tests for admin CRUD endpoints
"""

import pytest
from bson import ObjectId

from api.database import get_database
from api.tests.conftest import api_client


@pytest.mark.asyncio
async def test_create_property(test_user_and_token):
    """Test creating a property"""
    user_data, token, headers = test_user_and_token

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
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data


@pytest.mark.asyncio
async def test_create_property_invalid_data(test_user_and_token):
    """An unknown zone, an unknown type and a negative surface are all refused."""
    user_data, token, headers = test_user_and_token

    async with api_client() as client:
        response = await client.post(
            "/admin/properties",
            headers=headers,
            json={
                "zone": "Test Zone",
                "type": "invalid_type",  # Invalid property type
                "surface": -50,  # Negative surface
                "epc": 0.5,
                "state": 0.6,
                "kitchen": 0.6,
                "bath": 0.6,
                "base_ppm": 0,  # Invalid: must be > 0
            },
        )

        assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_get_all_properties(test_user_and_token):
    """Test retrieving all properties"""
    user_data, token, headers = test_user_and_token

    async with api_client() as client:
        # Create a property so the list is non-empty
        await client.post(
            "/admin/properties",
            headers=headers,
            json={
                "zone": "Bruxelles-Centre",
                "type": "apartment",
                "surface": 80,
                "epc": 0.5,
                "state": 0.6,
                "kitchen": 0.6,
                "bath": 0.6,
            },
        )

        response = await client.get("/admin/properties", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0


@pytest.mark.asyncio
async def test_get_property_by_id(test_user_and_token):
    """Test retrieving a specific property by ID"""
    user_data, token, headers = test_user_and_token

    async with api_client() as client:
        # Create a property to fetch
        create_response = await client.post(
            "/admin/properties",
            headers=headers,
            json={
                "zone": "Ixelles",
                "type": "house",
                "surface": 120,
                "epc": 0.6,
                "state": 0.7,
                "kitchen": 0.6,
                "bath": 0.6,
            },
        )
        property_id = create_response.json()["id"]

        response = await client.get(f"/admin/properties/{property_id}", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == property_id
        assert "zone" in data
        assert "type" in data


@pytest.mark.asyncio
async def test_get_nonexistent_property(test_user_and_token):
    """Test retrieving non-existent property returns 404"""
    user_data, token, headers = test_user_and_token
    fake_id = str(ObjectId())

    async with api_client() as client:
        response = await client.get(f"/admin/properties/{fake_id}", headers=headers)

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_property(test_user_and_token):
    """Test updating a property"""
    user_data, token, headers = test_user_and_token

    # Create a property first
    async with api_client() as client:
        create_response = await client.post(
            "/admin/properties",
            headers=headers,
            json={
                "zone": "Ixelles",
                "type": "house",
                "surface": 95,
                "epc": 0.5,
                "state": 0.6,
                "kitchen": 0.5,
                "bath": 0.5,
            },
        )
        property_id = create_response.json()["id"]

        # Update it
        response = await client.put(
            f"/admin/properties/{property_id}",
            headers=headers,
            json={
                "zone": "Ixelles",
                "type": "house",
                "surface": 95,
                "epc": 0.7,
                "state": 0.8,
                "kitchen": 0.7,
                "bath": 0.7,
            },
        )

        assert response.status_code == 200
        assert "message" in response.json()


@pytest.mark.asyncio
async def test_delete_property(test_user_and_token):
    """Test deleting a property"""
    user_data, token, headers = test_user_and_token
    db = get_database()

    # Create a property first
    async with api_client() as client:
        create_response = await client.post(
            "/admin/properties",
            headers=headers,
            json={
                "zone": "Uccle",
                "type": "apartment",
                "surface": 60,
                "epc": 0.5,
                "state": 0.6,
                "kitchen": 0.5,
                "bath": 0.5,
            },
        )
        property_id = create_response.json()["id"]

        # Delete the property
        response = await client.delete(f"/admin/properties/{property_id}", headers=headers)

        assert response.status_code == 200
        assert "message" in response.json()

        # Verify it's deleted
        deleted_prop = await db.properties.find_one({"_id": ObjectId(property_id)})
        assert deleted_prop is None


@pytest.mark.asyncio
async def test_create_renovation(test_user_and_token):
    """Test creating a renovation type"""
    user_data, token, headers = test_user_and_token

    async with api_client() as client:
        response = await client.post(
            "/admin/renovations",
            headers=headers,
            json={
                "code": "TEST_RENO",
                "label": "Test Renovation",
                "cost": 15000,
                "durationQ": 2,
                "delta": {
                    "epc": 0.10,
                    "state": 0.05,
                    "kitchen": 0.0,
                    "bath": 0.0,
                    "surfacePct": 0.0,
                },
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data


@pytest.mark.asyncio
async def test_get_all_renovations(test_user_and_token):
    """Test retrieving all renovation types"""
    user_data, token, headers = test_user_and_token

    async with api_client() as client:
        response = await client.get("/admin/renovations", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0  # Should have renovation types from seed


@pytest.mark.asyncio
async def test_update_renovation(test_user_and_token):
    """Test updating a renovation type"""
    user_data, token, headers = test_user_and_token

    # Create a renovation first
    async with api_client() as client:
        await client.post(
            "/admin/renovations",
            headers=headers,
            json={
                "code": "UPDATE_TEST",
                "label": "Update Test Reno",
                "cost": 10000,
                "durationQ": 1,
                "delta": {
                    "epc": 0.05,
                    "state": 0.03,
                    "kitchen": 0.0,
                    "bath": 0.0,
                    "surfacePct": 0.0,
                },
            },
        )

        # Update it
        response = await client.put(
            "/admin/renovations/UPDATE_TEST",
            headers=headers,
            json={
                "code": "UPDATE_TEST",
                "label": "Updated Reno",
                "cost": 12000,
                "durationQ": 2,
                "delta": {
                    "epc": 0.08,
                    "state": 0.05,
                    "kitchen": 0.0,
                    "bath": 0.0,
                    "surfacePct": 0.0,
                },
            },
        )

        assert response.status_code == 200


@pytest.mark.asyncio
async def test_delete_renovation(test_user_and_token):
    """Test deleting a renovation type"""
    user_data, token, headers = test_user_and_token

    # Create a renovation first
    async with api_client() as client:
        await client.post(
            "/admin/renovations",
            headers=headers,
            json={
                "code": "DELETE_TEST",
                "label": "Delete Test Reno",
                "cost": 8000,
                "durationQ": 1,
                "delta": {
                    "epc": 0.04,
                    "state": 0.02,
                    "kitchen": 0.0,
                    "bath": 0.0,
                    "surfacePct": 0.0,
                },
            },
        )

        # Delete it
        response = await client.delete("/admin/renovations/DELETE_TEST", headers=headers)

        assert response.status_code == 200
        assert "message" in response.json()


@pytest.mark.asyncio
async def test_admin_endpoints_require_auth():
    """Test that admin endpoints require authentication"""
    async with api_client() as client:
        # Try to access admin endpoints without token
        responses = [
            await client.get("/admin/properties"),
            await client.post("/admin/properties", json={}),
            await client.get("/admin/renovations"),
        ]

        for response in responses:
            assert response.status_code == 401
