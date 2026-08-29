# 2. Authorization is decided server-side, per request, per resource

Date: 2026-08-29

## Status

Accepted.

## Context

The application has two kinds of caller: a player, who trades with their own
money, and an administrator, who creates and deletes properties, edits the
renovation catalog, reads every trade, and advances the simulated clock.

Originally there was no distinction. Registration stored no role, every
`/admin/*` route was reachable by any authenticated user, and `/game/advance-quarter`
moved the entire market forward for everyone at the request of anyone. The
frontend drew the admin controls for every session, which is how it was
discovered: the buttons were there for a player, and they worked.

## Decision

Roles live on the user document, are read from the token subject on every
request, and are checked by a dependency, not by the caller.

- `require_admin` is a FastAPI dependency mounted on the `/admin` router itself
  and on `/game/advance-quarter`. It answers 403 for an identified caller
  without the role and 401 when there is no credential at all, and it logs the
  refusal as a structured security event.
- Ownership is separate from role and is checked per resource. `/trading/sell`
  and `/game/renovate` resolve a holding inside the caller's own portfolio
  rather than resolving it globally and comparing owners afterwards, so a
  holding belonging to somebody else is not found rather than forbidden.
- The frontend reads the same roles from `/auth/me` and hides the controls a
  player cannot use. This is presentation. It is written in the component that
  does it, so nobody mistakes it for the check.

## Consequences

The negative tests are the ones that matter, and they exist:
`api/tests/test_authorization.py` walks every admin route with no token, with a
player's token, and with an admin's token, and asserts 401, 403 and 200
respectively. A route added to the admin router inherits the dependency; a
route added anywhere else does not, which is why the file also asserts the
status of `/game/advance-quarter` by name.

Hiding a control in the browser has no security value and this is stated in
both the component and `SECURITY.md`, so that a future change to the frontend
is never argued about as if it were a security change.
