# Security policy

## Reporting a vulnerability

Report privately through GitHub's
[private vulnerability reporting](https://github.com/DeharengOlivier/real-estate-trading-game/security/advisories/new)
rather than by opening a public issue. Please include what you did, what you
observed, and what you expected. A first answer is sent within seven days.

This is a game with imaginary money and no real personal data, so nothing here
is worth attacking for gain. It is still an authenticated multi-user
application, and a finding that breaks one of the properties below is a real
finding.

## What the server guarantees

These are the invariants the test suite holds. A way around any of them is
what to report.

- **A token is not a role.** Every `/admin/*` route, plus `/game/advance-quarter`,
  is behind `require_admin`. An authenticated player gets 403, and a request
  with no credential gets 401. The frontend hides those controls, but that is
  presentation only: hiding a button changes nothing about what the API accepts.
- **Ownership is checked per resource, not per role.** `/game/renovate` and
  `/trading/sell` look a holding up inside the caller's own portfolio rather
  than looking it up globally and comparing owners afterwards. Knowing another
  player's holding id therefore gets you a 404, which is also the answer for an
  id that does not exist: the refusal does not confirm that the id is real.
- **The application refuses to start without a signing key.** There is no
  fallback `SECRET_KEY`, no placeholder, and a key shorter than 32 characters
  or equal to one published in this repository is rejected at import time. A
  forgotten variable is a container that will not boot, never a live API whose
  tokens a reader of this repository could forge.
- **Money never appears or disappears.** Cash moves with the affordability
  condition inside the update filter, so a balance cannot go negative however
  many requests arrive at once, and a listing is claimed with a single
  conditional write, so exactly one of two simultaneous buyers wins it. See
  `docs/adr/0001-conditional-writes-instead-of-transactions.md` for what this
  design does and does not cover.
- **Identifiers from a request are parsed, not trusted.** A malformed object id
  is a 400 with a message, never a 500 with a stack trace.
- **The two unauthenticated routes are bounded.** Login is limited to 5
  attempts per username per 5 minutes, and registration to 5 accounts per
  calling address per hour, checked before any password is hashed. Refusals are
  logged as structured security events with a request id, without the password
  or the token.

## What is deliberately out of scope

- The seeded `demo` account and its published password. It exists so the
  project runs with one command, it carries the admin role on purpose, and it
  is documented as such in the README.
- Denial of service through sheer volume against a local Docker stack.
- The economic model itself. Prices are invented; a strategy that makes a lot
  of imaginary money is a game finding, not a security one.

## Scanning

CodeQL runs on every push and pull request over both the Python and the
JavaScript trees with the `security-extended` query set. `pip-audit` and
`npm audit` run in the same workflow and fail the build on a known advisory in
a pinned dependency.

Please do not point automated scanners at anything but your own local stack.
