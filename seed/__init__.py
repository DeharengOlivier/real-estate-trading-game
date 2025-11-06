"""
Seed Package - Database Initialization

This package contains scripts for initializing the game database with
realistic Belgian real estate data.

Purpose:
    - Generates initial property inventory (300 properties)
    - Creates market indices for economic simulation
    - Populates renovation catalog
    - Sets up demo user account
    - Prepares game for first-time play

Package Contents:
    - constants.py: Business constants, formulas, and Belgian market data
    - seed_realestate.py: Database seeding script

Why this __init__.py file exists:
    This file marks seed/ as a Python package, enabling:
    
    1. Module Imports: Allows constants.py to be imported:
        from seed.constants import ZONES, BASE_PPM, RENOVATIONS
    
    2. Docker Execution: The seed container can execute:
        python -m seed.seed_realestate
        
    3. Code Organization: Separates seed logic from API code
    
    Without this file:
        - Docker seed container would fail with import errors
        - Constants could not be shared between seed modules
        - Package would not be recognized by Python

Seeding Process (seed_realestate.py):
    1. Connect to MongoDB
    2. Drop existing collections (fresh start)
    3. Generate 300 properties:
        - 12 zones across Belgium
        - Mix of houses (60%) and apartments (40%)
        - Realistic surface distributions (50-250 m²)
        - Variable quality characteristics (EPC, state, kitchen, bath)
    4. Calculate initial prices using market formulas
    5. Create listings for all properties
    6. Insert market index for starting quarter (2024-Q1)
    7. Populate renovation catalog
    8. Create demo user with 1,000,000€ starting capital

Data Realism:
    - Base prices calibrated on Belgian market 2024
    - Zone appreciation rates based on historical trends
    - Economic indicators (inflation, interest rates) reflect Belgium
    - Renovation costs based on actual Belgian construction prices

Docker Usage:
    The seed script runs automatically when starting containers:
        docker-compose up
    
    Or manually:
        docker-compose run seed
"""
