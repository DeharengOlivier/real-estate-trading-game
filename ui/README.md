# React Frontend

User interface for the real estate trading game.

## Structure

```
ui/
├── index.html          Main HTML page
├── package.json        npm dependencies
├── vite.config.js      Vite configuration
└── src/
    ├── main.jsx        React entry point
    ├── App.jsx         Root component
    ├── App.css         Global styles
    ├── index.css       Base styles
    ├── api.js          API client
    └── components/
        ├── Login.jsx       Authentication
        ├── Login.css       Login styles
        ├── Market.jsx      Market and trading
        └── Portfolio.jsx   User portfolio
```

## Components

### App.jsx

Root component with global state management.

**State:**
- `user` - Logged-in user (null if logged out)
- `currentView` - Active view ("login", "market", "portfolio")

**Logic:**
- Check token on load
- Fetch user info if a token exists
- Manual router between views
- Logout (clear token)

**Navigation:**
- Buttons: Market, Portfolio, Logout
- Conditional rendering of components
- Token persistence in localStorage

### Login.jsx

Authentication and account creation.

**Modes:**
- Login (default)
- Register (toggle)

**Login fields:**
- Username
- Password

**Register fields:**
- Username (unique)
- Email (validation)
- Name
- Password

**Validation:**
- Username minimum 3 characters
- Valid email format
- Password minimum 6 characters
- Error messages displayed

**Flow:**
1. User fills out the form
2. POST /auth/login or /auth/register
3. On success: store token + redirect
4. On failure: display error

**Security:**
- Password never shown in clear text
- Token stored in localStorage
- Rate limiting on the backend side

### Market.jsx

Property listing and trading.

**Features:**
- List of available properties
- Search by zone
- Filters (type, price)
- Sorting (price, surface area)
- Pagination
- Property purchase
- Property creation
- Property deletion

**Display per property:**
- Zone and type
- Surface area in m2
- Total price and price/m2
- Characteristics (EPC, condition, kitchen, bathroom)
- Zone trend (growth/decline)
- Buy button
- Delete button (red X)

**Creation Modal:**
- Zone selection (12 Belgian zones)
- Type selection (House/Apartment)
- Surface area slider (50-400 m2)
- Auto-generated characteristics (random 0.3-0.8)
- Base price based on zone/type
- Creation confirmation

**Deletion Confirmation:**
- Dialog before deletion
- Irreversible action
- Automatic refresh afterwards

**Local state:**
- `properties` - List of properties
- `loading` - Loading in progress
- `error` - Error message
- `filters` - Active filters
- `page` - Current page
- `showCreateModal` - Modal display

**Pagination:**
- 50 results per page
- Previous/Next buttons
- Counter "X-Y of Total"

### Portfolio.jsx

View of the user's holdings.

**Sections:**

**1. Summary:**
- Available cash
- Number of properties
- Total holdings value

**2. Holdings List:**
For each owned property:
- Zone, type, surface area
- Purchase price vs current price
- Profit/Loss (P&L)
- Percentage change
- Sell button

**Calculations:**
- Current price based on market indices
- P&L = current price - purchase price - fees - renovations
- Green color (gain) or red (loss)

**Actions:**
- Sell property (confirmation)
- Refresh after sale
- Cash update

**Visual indicators:**
- Green badge if P&L positive
- Red badge if P&L negative
- Trend arrows (up/down)

## api.js

Client for communicating with the backend.

**Configuration:**
- Base URL: http://localhost:8000 (dev)
- Automatic headers (Authorization)
- HTTP error handling

**Functions:**

`login(username, password)` - Login
- POST /auth/login
- Returns: {access_token}

`register(username, email, name, password)` - Registration
- POST /auth/register
- Returns: {access_token}

`getCurrentUser(token)` - User info
- GET /auth/me
- Headers: Authorization Bearer {token}

`getPortfolioSummary(token)` - Portfolio
- GET /portfolio/summary
- Returns: {cash, holdings, totalValue}

`getListings(filters, token)` - Available properties
- GET /trading/listings?zone=...&type=...
- Returns: {items, total, page}

`buyProperty(propertyId, token)` - Buy
- POST /trading/buy
- Body: {propertyId}

`sellProperty(holdingId, token)` - Sell
- POST /trading/sell
- Body: {holdingId}

`createProperty(propertyData, token)` - Create property
- POST /admin/properties
- Body: {zone, type, surface, epc, state, kitchen, bath}

`deleteProperty(propertyId, token)` - Delete property
- DELETE /admin/properties/{id}

**Error handling:**
```javascript
if (!response.ok) {
  const error = await response.json();
  throw new Error(error.detail || 'Erreur');
}
```

## Styles

### index.css
CSS reset and global variables.
- Font: system-ui
- Base colors
- Box-sizing

### App.css
Main application styles.
- Navigation bar
- Buttons
- Cards
- Responsive layout

### Login.css
Authentication form styles.
- Centering
- Form styling
- Toggle buttons
- Error messages

## Dependencies

**package.json:**
- react: 18.x - UI library
- react-dom: 18.x - DOM rendering
- vite: 5.x - Build tool and dev server

**Dev:**
- @vitejs/plugin-react - JSX support
- ESLint - Linting (optional)

## Vite Configuration

**vite.config.js:**
```javascript
export default {
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true
  },
  plugins: [react()]
}
```

**Environment variables:**
- `VITE_API_URL` - API URL (default: http://localhost:8000)

## Development

### Local startup
```bash
cd ui
npm install
npm run dev
# http://localhost:5173
```

### Production build
```bash
npm run build
# Output in dist/
```

### Preview build
```bash
npm run preview
```

## Docker

**Dockerfile.ui:**
- Base: node:20-alpine
- Build stage: npm install + npm run build
- Serve stage: nginx with static files
- Port: 80

**docker-compose.yml:**
```yaml
ui:
  build:
    context: .
    dockerfile: infra/Dockerfile.ui
  ports:
    - "5173:80"
  environment:
    - VITE_API_URL=http://localhost:8000
```

## State and Props

**App state flow:**
```
App (user, currentView)
  ├─ Login (setUser)
  ├─ Market (user)
  └─ Portfolio (user)
```

**Props drilling:**
- user passed to all components
- setUser to update after login
- setCurrentView for navigation

## LocalStorage

**Keys used:**
- `token` - JWT access token
- Persisted between sessions
- Removed on logout

**Security:**
- No sensitive data
- Token expires on the backend side (30 days)

## Error Handling

**Patterns:**
```javascript
try {
  const response = await api.getListings();
  setProperties(response.items);
} catch (error) {
  setError(error.message);
  console.error('Erreur:', error);
}
```

**Display:**
- Error messages in red
- Automatic retry on certain actions
- Fallback UI on failure

## Responsive Design

Media queries in CSS:
- Desktop: > 768px (multi-column layout)
- Mobile: < 768px (single-column layout)
- Adaptive cards
- Burger navigation (if implemented)

## Performance

**Optimizations:**
- Lazy loading of components (possible)
- Server-side pagination
- Listings cache (manual refresh)
- Debounce on search (if implemented)

## Accessibility

**Best practices:**
- Labels on inputs
- Buttons with descriptive text
- Color contrast
- Visible focus on interactive elements

## Future Improvements

**Possible additions:**
- Charts (Chart.js, Recharts)
- WebSocket for real-time prices
- Toast notifications
- Dark mode
- Multi-language
- Transition animations
