# Real Estate Trading Game

A real-estate trading game with an economic simulation of the Belgian housing market.

## Features

### Authentication
- Account creation (username, email, password)
- Login with JWT tokens
- Anti-bruteforce rate limiting (5 attempts / 5 min)
- Initial balance: 1,000,000

### Market
- 300+ properties across 12 Belgian zones
- Filters: zone, type (house/apartment), price
- Sorting: price, surface, zone
- Pagination (50 results per page)
- Property creation (admin)
- Property deletion (admin)

### Trading
- Buying with a 2.5% fee
- Selling with a 2.5% commission
- Price computed from market indices
- Available-balance check

### Portfolio
- Cash + total value of properties
- List of owned properties
- Per-property P&L calculation
- Performance indicators

### Administration
- Full CRUD on properties
- Renovation catalog management
- Transaction history


## Tech Stack

**Backend:**
- FastAPI (Python)
- MongoDB (9 collections)
- Redis (rate limiting)
- JWT auth

**Frontend:**
- React 18 + Vite
- Fetch API client

**Infrastructure:**
- Docker Compose (4 containers: api, ui, mongo, redis)
- Automatic seeding on startup

## Getting Started

### Prerequisites
- Docker Desktop installed and running

### Full Launch
```bash
# Start everything with a single command
docker-compose up --build -d

# Watch the seed logs (takes ~30 sec)
docker-compose logs -f seed

# Verify that everything is up
docker-compose ps
```

### Access
- **Frontend:** http://localhost:5173
- **API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health

### First Account
1. Go to http://localhost:5173
2. Click "Sign up"
3. Fill in username, email, name, password
4. You are logged in automatically with 1,000,000 in cash

## Structure

```
api/
  routers/          7 routers (auth, portfolio, trading, game, charts, admin, health)
  tests/            Pytest tests (23/26 passing)
  models.py         Pydantic schemas
  services.py       Business logic (price calculation)
  database.py       MongoDB + Redis
  auth.py           JWT + rate limiting

seed/
  seed_realestate.py    Generates 300 properties + indices

ui/src/
  components/       Login, Market, Portfolio
  api.js            Fetch client

infra/              Dockerfiles (api, ui, seed)
docs/               Technical documentation
```

## MongoDB Collections

1. **users** - User accounts
2. **portfolios** - Cash per user
3. **properties** - 300+ properties (zone, type, surface, characteristics)
4. **listings** - Market availability
5. **holdings** - Owned properties
6. **trades** - Transaction history
7. **marketindex** - Economic indices per quarter/zone
8. **pricehistory** - Price evolution
9. **renovations** - Renovation catalog

## Useful Commands

```bash
# Start
docker-compose up --build -d

# Live logs
docker-compose logs -f api
docker-compose logs -f ui

# Container status
docker-compose ps

# Tests
docker exec realestate-api pytest api/tests/ -v

# Stop
docker-compose down

# Full reset (deletes data)
docker-compose down -v
```

## Environment Variables

Configured in `docker-compose.yml`:
- MONGODB_URL=mongodb://mongo:27017
- REDIS_URL=redis://redis:6379
- SECRET_KEY=dev-secret-key-change-in-production
- VITE_API_URL=http://localhost:8000

See `.env.example` for the full list of variables. Never commit a real `.env`.

## Academic Project

ECAM - NoSQL Databases
Developed with AI assistance (GitHub Copilot). See `docs/AI-USAGE.md`.


## Tests

### Running the tests

```bash
# From the API container
docker compose exec api pytest

# Or locally if you have a Python environment
cd api
pip install -r requirements.txt
pytest
```

### Included tests

- `test_buy_reduces_cash_and_creates_holding()` - Checks buying
- `test_sell_creates_trade_and_removes_holding()` - Checks selling
- `test_renovation_applies_deltas_after_duration()` - Checks renovation works
- `test_advance_quarter_updates_prices()` - Checks time advancement
- `test_listings_filters()` - Checks search filters

## Limitations and how I would improve this

This project was built as an academic exercise. The points below are an honest,
technical assessment of what I would harden or rework before treating it as
production-grade.

### Testing
- Currently 23 of 26 tests pass. The three failing cases should be triaged and
  fixed (or removed if obsolete) rather than left red. A green suite is a
  precondition for everything below.
- Coverage is functional but shallow on edge cases: zero/negative prices,
  selling a property with an ongoing renovation, advancing many quarters at
  once, and concurrent buys of the same listing are not exercised.
- I would add `pytest --cov` to measure coverage and gate CI on a threshold.

### Concurrency and data integrity
- Buy and sell use MongoDB multi-document transactions, but they silently fall
  back to non-transactional writes when the server is a standalone node (no
  replica set). On a single-node Docker MongoDB the atomic path is therefore not
  active, so a crash mid-trade can leave cash, holdings, listings, and trades
  out of sync. I would run MongoDB as a single-node replica set so transactions
  are always available, and make the non-transactional fallback fail loudly
  rather than degrade quietly.
- There is no optimistic concurrency control on listings. Two users buying the
  same property at the same time can both pass the availability check. I would
  use a conditional update (for example `find_one_and_update` matching
  `isAvailable: true`) so that exactly one buyer wins, and reject the loser.

### Input validation and error handling
- Validation relies on Pydantic at the edges, but several handlers assume a
  document exists after a lookup and would raise on `None` instead of returning
  a clean 404. I would add explicit existence checks and consistent error
  envelopes across all routers.
- The admin create-property endpoint trusts a `base_ppm` value computed on the
  client. I would derive it server-side from the zone/type table so the client
  cannot inject arbitrary economics.

### Performance: indexing and pagination
- The MongoDB collections have no explicit indexes. Listing queries filter and
  sort on `zone`, `type`, `price`, and `surface`, and lookups hit `propertyId`,
  `userId`, `portfolioId`, and the quarter `t`. I would add compound indexes on
  the hot query paths and confirm them with `explain()`.
- Pagination is page/limit based, which is fine here but degrades on deep pages.
  For large catalogs I would move to range/cursor-based pagination.
- The portfolio summary issues per-holding price lookups in a loop (an N+1
  pattern). I would batch these with a single aggregation.

### Security and auth hardening
- `SECRET_KEY` defaults to a placeholder in code and is set to a known dev value
  in `docker-compose.yml`. In production it must come only from the environment,
  with the app refusing to start if it is missing or left at the default.
- Tokens are long-lived (24h) with no refresh/rotation and no revocation list. I
  would add short-lived access tokens plus refresh tokens, and store nothing
  sensitive in the JWT payload beyond the subject.
- There is no role system: any authenticated user can call the "admin"
  endpoints. I would add a role claim and enforce it as a dependency.

### Rate limiting via Redis
- Login rate limiting uses a Redis sorted set with a sliding window, which is
  the right primitive, but it only protects the login endpoint. I would extend
  it to registration and to write-heavy trading endpoints, and key it on client
  IP in addition to username to blunt distributed attempts.
- The in-memory fallback is per-process, so it provides no protection across
  multiple API replicas. I would treat Redis as required in production.

### Architecture
- Business logic (P&L math, fee handling, trade orchestration) currently lives
  inside the routers. I would extract it into a service/domain layer so routers
  stay thin (HTTP in, HTTP out) and the logic is unit-testable without the web
  stack. `services.py` already exists for pricing; I would grow it into the home
  for all domain rules.

### Tooling and delivery
- No CI pipeline. I would add GitHub Actions to run linting, type checks, and
  the test suite on every push.
- No static analysis. I would add `ruff` (lint) and `mypy` (type checking) for
  Python, and ESLint/Prettier for the React app, with type hints completed
  across the backend.
- Configuration is partly hardcoded (CORS origins, secret, ports). I would move
  all of it to environment-based settings (for example a Pydantic
  `BaseSettings` object) so dev/staging/prod differ only by environment.
```
