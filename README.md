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

### Configuration

The API signs its JWTs with `SECRET_KEY` and refuses to start without one:
there is no default, because a fallback key turns a forgotten variable into a
working API whose tokens anyone reading this repository can forge.

```bash
cp .env.example .env
echo "SECRET_KEY=$(openssl rand -hex 32)" >> .env
```

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

## Roles and the demo account

There are two roles. A **player** trades with their own money. An
**administrator** also creates and deletes properties, edits the renovation
catalogue, reads every trade, and advances the simulated clock for everybody.

Registration through the interface always creates a player. The seed inserts
one administrator so that the project is usable straight after a clone:

| username | password | roles |
|---|---|---|
| `demo` | `demo123` | player, admin |

Those credentials are published, deliberately, and the account exists only in a
freshly seeded local database. Do not seed a deployment that anyone else can
reach.

Every admin route is behind a server-side dependency that answers 403 to a
player and 401 to a request with no credential. The interface hides the
controls a player cannot use, which is presentation only: hiding a button
changes nothing about what the API accepts. See
`docs/adr/0002-authorization-is-server-side-only.md`.

## Structure

```
api/
  routers/          7 routers (auth, portfolio, trading, game, charts, admin, health)
  tests/            23 files, 244 tests, no external services
  models.py         Pydantic schemas, validated at the boundary
  services.py       Pricing model
  auth.py           JWT, roles, rate limiting
  database.py       MongoDB + Redis, and the unique indexes
  clock.py          One source of "now", timezone aware
  cors.py           Allowed origins, parsed from the environment
  identifiers.py    Object ids parsed at the boundary, 400 rather than 500
  observability.py  Request ids, structured logging, security events

simulation/         Economic constants, imported by both the API and the seed
seed/               Generates 300 properties, market indices and the demo account
scripts/smoke.py    Guard checks against a running stack, run by CI

ui/src/
  components/       Login, Market, Portfolio
  api.js            Fetch client with timeouts on every call

infra/              Dockerfiles (api, ui, seed)
docs/adr/           Architecture decision records
.github/workflows/  CI and CodeQL
```

## MongoDB Collections

1. **users** - accounts and roles (unique index on username and on email)
2. **portfolios** - cash per user (unique index on userId)
3. **properties** - 300+ properties (zone, type, surface, characteristics)
4. **listings** - market availability (unique index on propertyId)
5. **holdings** - owned properties (unique index on portfolioId + propertyId)
6. **trades** - transaction history
7. **marketindex** - economic indices per quarter (unique index on t)
8. **pricehistory** - price evolution
9. **renovations** - renovation catalogue

The unique indexes are the integrity layer. An application-level "does it
already exist?" check is advisory: two concurrent requests both pass it. The
indexes are created at startup by `ensure_indexes`, and a violation surfaces as
a 409, not a duplicate row.

## Useful Commands

```bash
# Start (SECRET_KEY must be set, see Configuration)
docker compose up --build -d

# Live logs
docker compose logs -f api
docker compose logs -f ui

# API tests, in the container
docker compose exec api pytest

# Frontend lint, tests and build
cd ui && npm ci && npm run lint && npm test && npm run build

# Guard checks against the running stack
python -m scripts.smoke

# Stop, and stop with the data
docker compose down
docker compose down -v
```

## Environment Variables

| Variable | Default | Meaning |
|---|---|---|
| `SECRET_KEY` | **none, required** | JWT signing key. At least 32 characters. The API refuses to import without it, and refuses the placeholder keys published in this repository. |
| `MONGODB_URL` | `mongodb://mongo:27017` | Database server. |
| `MONGODB_DB` | `realestate` | Database name. |
| `REDIS_URL` | `redis://redis:6379` | Rate-limiter store. Without it the limiter falls back to a per-process counter, which protects a single replica only. |
| `CORS_ALLOWED_ORIGINS` | the local frontend | Comma-separated browser origins allowed to call the API. A wildcard is refused: this API answers with credentials, and browsers do not send credentials to a wildcard origin. |
| `VITE_API_URL` | `http://localhost:8000` | API base URL baked into the frontend build. |

`.env.example` is the full list. Never commit a real `.env`.

## Tests

### API

The suite runs entirely in memory: no MongoDB, no Redis. `mongomock-motor`
stands in for MongoDB and `fakeredis` for Redis, wired through fixtures in
`api/tests/conftest.py`. 244 tests, about 45 seconds, on a bare virtual
environment.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r api/requirements.txt -r api/requirements-dev.txt
pytest
```

CI runs it on Python 3.11, 3.12 and 3.13.

What that substitution costs, and what is checked against the real stack
instead, is written down in
`docs/adr/0003-tests-run-without-external-services.md`.

### Frontend

```bash
cd ui
npm ci
npm run lint      # ESLint with react-hooks and jsx-a11y
npm test          # vitest + testing-library
```

### What is covered

- **Authorization** - every admin route with no token, with a player's token
  and with an admin's token; the ownership check on renovating and selling
  somebody else's holding; the 401-versus-403 distinction.
- **Concurrency** - two buyers racing for the same listing, driven into the
  same instant through a rendezvous: one wins, one is refused, the balance is
  debited once, exactly one buy trade exists.
- **Auth** - registration, weak passwords, duplicates (409 from the index, not
  from a check), login, `/auth/me`, JWT validation, rate limiting on both the
  Redis and the in-memory paths, and the refusal to start without a key.
- **Trading** - filters, pagination, sorting, buy and sell including the
  refusals, fees and P&L.
- **Portfolio** - summary, equity, unrealized P&L, per-holding cost basis, and
  a query budget so an N+1 cannot come back unnoticed.
- **Game** - renovation catalogue, starting a renovation, advancing quarters,
  the cost of advancing.
- **Boundaries** - malformed object ids, timezone handling, CORS parsing,
  request-id sanitising, database constraints.

## Operations

- **CI** (`.github/workflows/ci.yml`) runs ruff, ruff format, mypy, the API
  suite on three interpreters, `pip-audit` and `npm audit`, the frontend lint,
  tests and build, and finally brings the compose stack up and runs
  `scripts/smoke.py` against it. It also asserts that the stack refuses to
  start with no `SECRET_KEY`.
- **CodeQL** (`.github/workflows/codeql.yml`) scans the Python and JavaScript
  trees with the `security-extended` query set.
- **Logs** are structured and carry a request id, propagated from
  `X-Request-ID` when the caller sends a safe one. Refused authorizations,
  failed logins and rate-limit hits are logged as security events.
- **Vulnerability reports**: see `SECURITY.md`.

## Backup and restore

The seeded market can be rebuilt at any time by re-running the seed. What
cannot is everything a player did afterwards: accounts, portfolios, holdings
and trades.

```bash
scripts/backup.sh [destination]     # default ./backups, prints the archive path
scripts/restore.sh <archive.gz>     # drops and replaces, asks before it does
```

**The drill has been run, and this is its record.** A backup nobody has ever
restored is a belief, not a backup.

| Step | Result |
|---|---|
| State to save | demo account, cash 847 815.38, one holding in Charleroi-Ville bought at 148 472.80, 2 trades |
| `scripts/backup.sh` | `realestate-20260829T013720Z.archive.gz`, 90 627 bytes |
| Destruction | every holding and trade deleted, every portfolio balance set to 1 |
| State after destruction | cash 1.0, no holdings, 0 trades (confirmed through the API, not only in the shell) |
| `scripts/restore.sh` | cash 847 815.38, holding Charleroi-Ville at 148 472.80, 2 trades, 300 properties, 3 users |
| Indexes after restore | every unique index present (`username_1`, `email_1`, `userId_1`, `propertyId_1`, `portfolioId_1_propertyId_1`, `t_1`) |
| Constraint after restore | registering `demo` a second time still answers 409 |

The index check is the part worth keeping: a restore that brought the documents
back without their unique indexes would look like a success and would have
silently removed the integrity layer.

## Interface

Built for a 375px screen first; the desktop layout is added by `min-width`
queries. Every interactive element is at least 44px on its smallest side, no
affordance is hover-only, and neither the page nor any nested container scrolls
horizontally at 375px. Measured with the Chrome DevTools Protocol at a true
375px layout viewport, and again at 1440px.

The portfolio view, and with it the charting library, is loaded on demand: the
entry bundle is 162 kB rather than 545 kB, so the first screen does not pay for
a library it never calls.

## Known limits

An honest list of what is still true.

- **A purchase is four writes, not one transaction.** Each scarce claim is
  atomic on its own and a failure compensates, but a process killed mid-purchase
  can leave a holding nobody was charged for. The reasoning, and what would
  change it, is in
  `docs/adr/0001-conditional-writes-instead-of-transactions.md`.
- **Tokens live 24 hours with no rotation and no revocation list.** Logging out
  drops the token in the browser; it stays valid until it expires.
- **Rate limiting covers login only**, and its fallback is per process. A
  deployment with more than one replica needs Redis to be present, not optional.
- **Trade orchestration still lives in the routers.** The pricing model is in
  `simulation/` and `services.py`; the buy and sell flows are not yet behind a
  domain layer, so they can only be tested through HTTP.
- **Deep pagination is page-based** and degrades on a large catalogue. Fine for
  300 properties, wrong for 300 000.
- **`base_ppm` on admin property creation is supplied by the client.** It should
  be derived server-side from the zone and type table.

## Academic Project

ECAM - NoSQL Databases
Developed with AI assistance (GitHub Copilot). See `docs/AI-USAGE.md`.
