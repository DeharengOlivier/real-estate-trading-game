# React frontend

The browser client for the real estate trading game. Vite, React 18, no router
and no state library: two views behind a manual switch, which is the whole app.

The API is the source of truth for everything, including what the caller is
allowed to do. This document covers what the source alone does not say.

## Running it

```bash
npm ci
npm run dev        # http://localhost:5173, expects the API on :8000
npm run lint       # ESLint: react-hooks, jsx-a11y, react
npm test           # vitest + testing-library, jsdom
npm run build      # production bundle in dist/
```

`VITE_API_URL` points the client at the API and is baked in at build time
(default `http://localhost:8000`). In the compose stack it is set for you.

CI runs lint, test and build on every push. All three must pass.

## Layout

```
src/
  main.jsx                       Entry point
  App.jsx                        Session, view switch, the summary bar
  api.js                         The only place that talks to the API
  index.css                      Reset and page-level rules
  App.css                        Everything else, mobile-first
  setupTests.js                  jest-dom matchers for vitest
  components/
    Login.jsx / Login.css        Sign in and sign up
    Market.jsx                   Listings, filters, paging, buying
    Market.pagination.test.jsx   Regression battery for the paging defect
    Portfolio.jsx                Holdings, chart, selling, renovating
```

## Conventions that are not obvious from the code

**Mobile-first, and measured.** The rules outside a media query are the 375px
layout; `min-width: 768px` adds the desktop one. Every interactive element is
at least 44px on its smallest side, nothing is hover-only, hover effects sit
inside `@media (hover: hover)` because a touch device never leaves the state a
tap put it in, and `100dvh` is used rather than `100vh` so the collapsing
mobile URL bar does not cut the page. Neither the body nor any nested container
scrolls horizontally at 375px. This is verified in a real browser through the
Chrome DevTools Protocol at a true 375px layout viewport, not by resizing a
desktop window.

**Every request is bounded.** `api.js` has one `request()` helper and every
call goes through it: an `AbortController` with a 10 second timeout, 60 seconds
for advancing a quarter, which genuinely takes that long over many quarters. It
also reads FastAPI's two failure shapes (a string `detail` and a list of
validation errors) so a failure never renders as `[object Object]`, and a 401
clears the stored token before reporting "Session expired", so the next render
returns to the login form instead of retrying with a credential the server has
already rejected.

**Role gating is presentation.** `App.jsx` derives `isAdmin` from the roles in
the `/auth/me` response and hides the advance-quarter box, the create-property
button and the per-card delete button. This is so the interface does not offer
an action the API is about to answer with a 403. It is not a security boundary;
the server checks the role again on every request. Never move a check into this
layer.

**The token lives in `localStorage`** under the key `token`, set and cleared
only by `api.js`. That makes it readable by any script running on the page, so
the absence of cross-site scripting is what protects it.

**Filters and query are separate state.** In `Market.jsx`, `filters` is what
the user is typing and `query` is what was actually asked for. Only `query`
triggers a fetch, through a single effect. Collapsing the two is what let a
page click and a stale closure disagree about which page was loading, so that
"Next" never left page 1. The battery in `Market.pagination.test.jsx` exists to
stop that returning.

## Dependencies

`react`, `react-dom`, and `recharts` for the portfolio chart. Recharts is
roughly 400 kB, so `Portfolio` is a lazy import behind a `Suspense` boundary:
the entry chunk is 162 kB instead of 545 kB, and the market view, which is
where everyone lands, does not download a charting library it never calls.

Adding a dependency here means naming the constraint that forced it.
