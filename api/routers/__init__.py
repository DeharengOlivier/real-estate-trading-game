"""
Routers Package - API Endpoint Organization

This package contains all API routers, organized by feature following the
Single Responsibility Principle (SOLID).

Purpose:
    - Separates API endpoints into logical modules
    - Improves code maintainability and readability
    - Enables team collaboration (each developer can work on different routers)
    - Facilitates testing (each router can be tested independently)

Available Routers:
    - auth.py: User registration, login, and identity management
    - portfolio.py: Portfolio value tracking and holdings
    - trading.py: Property marketplace, buying, and selling
    - game.py: Time advancement and renovation mechanics
    - charts.py: Historical data and visualization endpoints
    - admin.py: Administrative CRUD operations (requires admin role)
    - health.py: System monitoring and health checks

Why this __init__.py file exists:
    This file marks the routers/ directory as a Python sub-package, allowing
    imports like:

        from api.routers.auth import router as auth_router
        from api.routers.trading import router as trading_router

    Without this file, the routers would not be importable, and the main
    application in main.py could not register them.

Router Registration Pattern:
    Each router is registered in main.py with:

        app.include_router(auth_router, prefix="/auth", tags=["Authentication"])

    This creates URL patterns like:
        - POST /auth/register
        - POST /auth/login
        - GET /auth/me

Architecture Benefits:
    1. Modularity: Each router is self-contained
    2. Scalability: Easy to add new routers without touching existing code
    3. Clarity: API structure mirrors business domains
    4. Testing: Each router can be tested in isolation
"""
