"""
API Package - Real Estate Game Backend

This package contains the FastAPI backend application for the Real Estate Game.

Purpose:
    - Provides RESTful API endpoints for the frontend
    - Manages user authentication and authorization
    - Handles property trading, portfolio management, and game mechanics
    - Integrates with MongoDB for data persistence
    - Uses Redis for caching and rate limiting (optional)

Package Structure:
    - main.py: Application entry point and router registration
    - auth.py: JWT authentication and password hashing
    - database.py: Database connection management
    - models.py: Pydantic models for request/response validation
    - services.py: Business logic and pricing calculations
    - routers/: API endpoint modules organized by feature
    - tests/: Pytest test suite

Why this __init__.py file exists:
    In Python, __init__.py files serve to mark a directory as a Python package.
    This allows the directory to be imported as a module, enabling imports like:

        from api.database import get_database
        from api.auth import get_current_user

    Without this file, Python would not recognize 'api/' as a package, and
    imports would fail with "ModuleNotFoundError: No module named 'api'".

    This is a fundamental part of Python's package system and is required
    for proper module organization and dependency management.

Technical Details:
    - Python 3.9+ required
    - FastAPI framework for async API development
    - MongoDB for NoSQL data storage
    - Redis for caching (optional, graceful degradation)
    - JWT tokens for stateless authentication
    - Bcrypt for password hashing

Author: ECAM Real Estate Game Team
"""
