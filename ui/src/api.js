const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Get token from localStorage
const getToken = () => localStorage.getItem('token');

// Set token in localStorage
export const setToken = (token) => localStorage.setItem('token', token);

// Remove token from localStorage
export const removeToken = () => localStorage.removeItem('token');

// Create headers with authentication
const getHeaders = () => {
  const headers = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
};

export const api = {
  // Authentication
  register: async (userData) => {
    const res = await fetch(`${API_URL}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(userData)
    });
    
    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || 'Registration failed');
    }
    
    const data = await res.json();
    setToken(data.access_token);
    return data;
  },

  login: async (credentials) => {
    const res = await fetch(`${API_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(credentials)
    });
    
    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || 'Login failed');
    }
    
    const data = await res.json();
    setToken(data.access_token);
    return data;
  },

  getMe: async () => {
    const res = await fetch(`${API_URL}/auth/me`, {
      headers: getHeaders()
    });
    
    if (!res.ok) {
      if (res.status === 401) {
        removeToken();
        throw new Error('Session expired');
      }
      throw new Error('Failed to get user info');
    }
    
    return res.json();
  },

  logout: () => {
    removeToken();
  },

  // Health
  health: async () => {
    const res = await fetch(`${API_URL}/health`);
    return res.json();
  },

  // Current quarter
  getCurrentQuarter: async () => {
    const res = await fetch(`${API_URL}/game/current-quarter`);
    return res.json();
  },

  // Listings
  getListings: async (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.zone) params.append('zone', filters.zone);
    if (filters.type) params.append('type', filters.type);
    if (filters.minPrice) params.append('minPrice', filters.minPrice);
    if (filters.maxPrice) params.append('maxPrice', filters.maxPrice);
    if (filters.page) params.append('page', filters.page);
    if (filters.limit) params.append('limit', filters.limit);
    
    const res = await fetch(`${API_URL}/trading/listings?${params}`);
    const data = await res.json();
    return data;
  },

  // Portfolio
  getPortfolioSummary: async () => {
    const res = await fetch(`${API_URL}/portfolio/summary`, {
      headers: getHeaders()
    });
    
    if (!res.ok) {
      if (res.status === 401) {
        removeToken();
        throw new Error('Session expired');
      }
      throw new Error('Failed to get portfolio summary');
    }
    
    return res.json();
  },

  getHoldings: async () => {
    const res = await fetch(`${API_URL}/portfolio/holdings`, {
      headers: getHeaders()
    });
    
    if (!res.ok) {
      if (res.status === 401) {
        removeToken();
        throw new Error('Session expired');
      }
      throw new Error('Failed to get holdings');
    }
    
    return res.json();
  },

  // Buy/Sell
  buyProperty: async (propertyId) => {
    const res = await fetch(`${API_URL}/trading/buy`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ propertyId })
    });
    
    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || 'Purchase failed');
    }
    
    return res.json();
  },

  sellProperty: async (propertyId) => {
    const res = await fetch(`${API_URL}/trading/sell`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ propertyId })
    });
    
    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || 'Sale failed');
    }
    
    return res.json();
  },

  // Renovations
  getRenovations: async () => {
    const res = await fetch(`${API_URL}/game/renovations`);
    return res.json();
  },

  startRenovation: async (holdingId, renoCode) => {
    const res = await fetch(`${API_URL}/game/renovate`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ holdingId, renoCode })
    });
    
    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || 'Renovation failed');
    }
    
    return res.json();
  },

  // Time
  advanceQuarter: async () => {
    const res = await fetch(`${API_URL}/game/advance-quarter`, {
      method: 'POST',
      headers: getHeaders()
    });
    
    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || 'Failed to advance quarter');
    }
    
    return res.json();
  },

  // Charts
  getPortfolioEquityChart: async () => {
    const res = await fetch(`${API_URL}/charts/portfolio-equity`, {
      headers: getHeaders()
    });
    return res.json();
  },

  getPropertyPriceChart: async (propertyId) => {
    const res = await fetch(`${API_URL}/charts/property/${propertyId}`, {
      headers: getHeaders()
    });
    return res.json();
  },

  // Admin - Delete property
  deleteProperty: async (propertyId) => {
    const res = await fetch(`${API_URL}/admin/properties/${propertyId}`, {
      method: 'DELETE',
      headers: getHeaders()
    });
    
    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || 'Deletion failed');
    }
    
    return res.json();
  },

  // Admin - Create property
  createProperty: async (propertyData) => {
    const res = await fetch(`${API_URL}/admin/properties`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(propertyData)
    });
    
    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || 'Creation failed');
    }
    
    return res.json();
  }
};
