# API Tests

Unit and integration tests for the FastAPI API.

## Structure

```
tests/
├── __init__.py       Package marker
├── conftest.py       Shared pytest fixtures
└── test_api.py       Endpoint tests
```

## conftest.py

Global test configuration.

**Fixtures:**

`client` - FastAPI test client
- Scope: function (new for each test)
- Returns: TestClient(app)
- Usage: Make HTTP requests without a server

`test_db` - Test database
- Scope: function
- Creates a temporary MongoDB DB
- Name: `test_realestate_{random}`
- Automatic cleanup after each test

`test_user` - Test user
- Scope: function
- Username: `testuser{random}`
- Password: `testpass123`
- Created via POST /auth/register
- Returns: dict with token and user_id

**Lifecycle:**
1. Before test: set up DB, create user
2. During test: execution
3. After test: clean up DB

## test_api.py

Tests for the main endpoints.

### Health Check Tests

`test_health_check()` - Check that the API responds
- GET /health
- Expect: 200 OK
- Expect: {"status": "healthy"}

### Authentication Tests

`test_register_success()` - Successful registration
- POST /auth/register with valid data
- Expect: 200 OK
- Expect: access_token returned
- Verify: user created in DB
- Verify: portfolio created with 1,000,000 cash

`test_register_duplicate()` - Prevent duplicates
- POST /auth/register with an existing username
- Expect: 409 Conflict

`test_login_success()` - Successful login
- POST /auth/login with valid credentials
- Expect: 200 OK
- Expect: access_token returned

`test_login_wrong_password()` - Reject wrong password
- POST /auth/login with wrong password
- Expect: 401 Unauthorized

`test_get_me()` - Retrieve user information
- GET /auth/me with JWT token
- Expect: 200 OK
- Expect: username, email, name

### Portfolio Tests

`test_portfolio_summary()` - Portfolio overview
- GET /portfolio/summary with auth
- Expect: 200 OK
- Expect: cash balance
- Expect: holdings array (empty at first)

`test_portfolio_unauthorized()` - Block access without auth
- GET /portfolio/summary without token
- Expect: 401 Unauthorized

### Trading Tests

`test_get_listings()` - List available properties
- GET /trading/listings
- Expect: 200 OK
- Expect: items array
- Expect: total, page, limit

`test_get_listings_filters()` - Filters work
- GET /trading/listings?zone=Bruxelles&type=house
- Expect: 200 OK
- Expect: filtered results

`test_buy_property()` - Buy a property
- POST /trading/buy with propertyId
- Expect: 200 OK
- Verify: cash deducted
- Verify: holding created
- Verify: trade recorded
- Verify: listing unavailable

`test_buy_insufficient_funds()` - Reject if not enough cash
- POST /trading/buy with price > cash
- Expect: 400 Bad Request

`test_sell_property()` - Sell a property
- POST /trading/sell with holdingId
- Expect: 200 OK
- Verify: cash added
- Verify: holding removed
- Verify: trade recorded
- Verify: listing available

### Game Tests

`test_get_quarter()` - Retrieve the current quarter
- GET /game/quarter
- Expect: 200 OK
- Expect: format "YYYY-QN"

`test_advance_quarter()` - Advance to the next quarter
- POST /game/advance
- Expect: 200 OK
- Verify: indices updated

### Admin Tests

`test_create_property()` - Create a property (admin)
- POST /admin/properties with data
- Expect: 201 Created
- Verify: property in DB
- Verify: listing created

`test_delete_property()` - Delete a property
- DELETE /admin/properties/{id}
- Expect: 200 OK
- Verify: property deleted
- Verify: listing deleted

`test_list_trades()` - Transaction history
- GET /admin/trades
- Expect: 200 OK
- Expect: array of trades

## Running the Tests

### All tests
```bash
docker exec realestate-api pytest api/tests/ -v
```

### A specific test
```bash
docker exec realestate-api pytest api/tests/test_api.py::test_buy_property -v
```

### With coverage
```bash
docker exec realestate-api pytest api/tests/ --cov=api --cov-report=term-missing
```

### Verbose mode with logs
```bash
docker exec realestate-api pytest api/tests/ -v -s
```

## Assertions Used

**Status codes:**
```python
assert response.status_code == 200
assert response.status_code == 201
assert response.status_code == 400
assert response.status_code == 401
assert response.status_code == 404
assert response.status_code == 409
```

**JSON content:**
```python
assert "access_token" in response.json()
assert response.json()["cash"] == 1000000
assert len(response.json()["items"]) > 0
```

**Database:**
```python
user = await db.users.find_one({"username": "testuser"})
assert user is not None
assert user["email"] == "test@example.com"
```

## Mocking

Redis is mocked automatically:
- Rate limiting disabled in tests
- No Redis connection required
- In-memory fallback used

Test MongoDB:
- Separate database for each test
- Complete isolation
- Automatic cleanup

## Current Coverage

About 88% (23/26 tests passing)

**Covered areas:**
- Full authentication
- Basic portfolio
- Trading buy/sell
- Game mechanics
- Admin CRUD

**Not covered:**
- Renovations
- Charts/graphs
- Complex edge cases

## Adding New Tests

Template:
```python
def test_descriptive_name(client, test_db, test_user):
    """Describe the behavior being tested"""
    # Arrange
    data = {"key": "value"}
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    
    # Act
    response = client.post("/endpoint", json=data, headers=headers)
    
    # Assert
    assert response.status_code == 200
    assert response.json()["expected_key"] == "expected_value"
```

## Debugging Tests

Show the logs:
```bash
pytest api/tests/ -v -s --log-cli-level=DEBUG
```

Stop at the first failure:
```bash
pytest api/tests/ -x
```

Interactive mode (PDB):
```python
def test_example():
    import pdb; pdb.set_trace()
    # ...
```

## Best Practices

- One test = one feature
- Descriptive names (test_action_expected_result)
- Arrange-Act-Assert pattern
- Automatic cleanup via fixtures
- Isolation between tests
- No dependencies between tests
- Mock external services
