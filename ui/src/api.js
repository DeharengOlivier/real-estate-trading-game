const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Every call is bounded. A fetch with no timeout waits as long as the network
// lets it, which on a phone that has just lost signal is minutes of a spinner
// with no way back. Advancing a quarter recomputes every price, so it gets
// longer than the rest rather than no limit at all.
const DEFAULT_TIMEOUT_MS = 10000
const SLOW_TIMEOUT_MS = 60000

const getToken = () => localStorage.getItem('token')
export const setToken = (token) => localStorage.setItem('token', token)
export const removeToken = () => localStorage.removeItem('token')

const authHeaders = () => {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/**
 * One request, bounded in time, with one way of reporting failure.
 *
 * Written once rather than seventeen times: before this, each call spelled out
 * its own error handling and none of them had a timeout.
 */
async function request(path, { method = 'GET', body, auth = false, timeout = DEFAULT_TIMEOUT_MS, onFailure } = {}) {
  const controller = new AbortController()
  const expired = setTimeout(() => controller.abort(), timeout)

  let response
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers: {
        ...(body ? { 'Content-Type': 'application/json' } : {}),
        ...(auth ? authHeaders() : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error(`The server did not answer within ${Math.round(timeout / 1000)} seconds. Check your connection and try again.`)
    }
    throw new Error('Could not reach the server. Check your connection and try again.')
  } finally {
    clearTimeout(expired)
  }

  if (response.ok) {
    return response.status === 204 ? null : response.json()
  }

  // 401 means the token is gone or no longer valid: drop it, so the next
  // render asks for a login rather than retrying with a credential that has
  // already been refused.
  if (response.status === 401) {
    removeToken()
    throw new Error('Session expired')
  }

  throw new Error(await failureMessage(response, onFailure))
}

async function failureMessage(response, fallback) {
  try {
    const problem = await response.json()
    if (typeof problem.detail === 'string') return problem.detail
    // FastAPI reports validation errors as a list of field problems.
    if (Array.isArray(problem.detail)) {
      return problem.detail.map((item) => item.msg).join('. ')
    }
  } catch {
    // Not JSON. Fall through to the caller's wording.
  }
  return fallback || `Request failed (${response.status})`
}

export const api = {
  register: async (userData) => {
    const data = await request('/auth/register', { method: 'POST', body: userData, onFailure: 'Registration failed' })
    setToken(data.access_token)
    return data
  },

  login: async (credentials) => {
    const data = await request('/auth/login', { method: 'POST', body: credentials, onFailure: 'Login failed' })
    setToken(data.access_token)
    return data
  },

  getMe: () => request('/auth/me', { auth: true }),

  logout: () => removeToken(),

  health: () => request('/health'),

  getCurrentQuarter: () => request('/game/current-quarter'),

  getListings: (filters = {}) => {
    const params = new URLSearchParams()
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null && value !== '') params.append(key, value)
    }
    return request(`/trading/listings?${params}`)
  },

  getPortfolioSummary: () => request('/portfolio/summary', { auth: true }),

  getHoldings: () => request('/portfolio/holdings', { auth: true }),

  buyProperty: (propertyId) =>
    request('/trading/buy', { method: 'POST', body: { propertyId }, auth: true, onFailure: 'Purchase failed' }),

  sellProperty: (propertyId) =>
    request('/trading/sell', { method: 'POST', body: { propertyId }, auth: true, onFailure: 'Sale failed' }),

  getRenovations: () => request('/game/renovations'),

  startRenovation: (holdingId, renoCode) =>
    request('/game/renovate', { method: 'POST', body: { holdingId, renoCode }, auth: true, onFailure: 'Renovation failed' }),

  // Recomputes the price of every property, so it is allowed longer.
  advanceQuarter: () =>
    request('/game/advance-quarter', { method: 'POST', auth: true, timeout: SLOW_TIMEOUT_MS, onFailure: 'Failed to advance quarter' }),

  getPortfolioEquityChart: () => request('/charts/portfolio-equity', { auth: true }),

  getPropertyPriceChart: (propertyId) => request(`/charts/property/${propertyId}`, { auth: true }),

  deleteProperty: (propertyId) =>
    request(`/admin/properties/${propertyId}`, { method: 'DELETE', auth: true, onFailure: 'Deletion failed' }),

  createProperty: (propertyData) =>
    request('/admin/properties', { method: 'POST', body: propertyData, auth: true, onFailure: 'Creation failed' }),
}
