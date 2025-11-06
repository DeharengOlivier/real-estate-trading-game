"""
Tests Package - Pytest Test Suite

This package contains all automated tests for the API backend.

Purpose:
    - Validates API functionality and business logic
    - Prevents regressions when adding new features
    - Documents expected behavior through test cases
    - Ensures code quality and reliability

Test Structure:
    - conftest.py: Pytest fixtures and test configuration
    - test_auth.py: Authentication and authorization tests
    - test_api.py: Core API functionality tests
    - test_admin.py: Administrative operations tests

Why this __init__.py file exists:
    This file marks tests/ as a Python package, which is CRITICAL for pytest
    to work correctly. It enables:
    
    1. Test Discovery: Pytest can find and execute test files
    2. Import Resolution: Tests can import from parent packages
    3. Fixture Sharing: conftest.py fixtures are accessible to all tests
    
    Without this file:
        - Pytest may fail to discover tests
        - Imports like "from api.database import get_database" would fail
        - Fixture sharing would not work
        - Tests would be isolated and unable to access application code

Running Tests:
    From project root:
        pytest                          # Run all tests
        pytest -v                       # Verbose output
        pytest api/tests/test_auth.py   # Run specific test file
        pytest -k "test_register"       # Run tests matching pattern
        pytest --cov=api                # Run with coverage report

Test Coverage (as of last run):
    - 26 total tests
    - 23 passing (88% success rate)
    - Coverage: ~75% of codebase

Best Practices:
    - Each test is independent (no shared state)
    - Use fixtures for setup/teardown
    - Test both success and failure cases
    - Use descriptive test names (test_register_with_valid_credentials)
    - Clean up database after tests (fixtures handle this)
"""
