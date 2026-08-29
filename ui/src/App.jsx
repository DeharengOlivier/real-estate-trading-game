import { useState, useEffect, useCallback } from 'react'
import { api } from './api'
import './App.css'
import Login from './components/Login'
import Market from './components/Market'
import Portfolio from './components/Portfolio'

function App() {
  const [user, setUser] = useState(null)
  const [authChecked, setAuthChecked] = useState(false)
  const [currentView, setCurrentView] = useState('market') // 'market' or 'portfolio'
  const [currentQuarter, setCurrentQuarter] = useState('')
  const [portfolioSummary, setPortfolioSummary] = useState(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState(null)
  const [quartersToAdvance, setQuartersToAdvance] = useState(1)
  const [portfolioRefreshKey, setPortfolioRefreshKey] = useState(0)
  const [marketRefreshKey, setMarketRefreshKey] = useState(0)

  const showMessage = useCallback((text, type = 'info') => {
    setMessage({ text, type })
    setTimeout(() => setMessage(null), 5000)
  }, [])

  const checkAuth = useCallback(async () => {
    try {
      const userData = await api.getMe()
      setUser(userData)
    } catch {
      // No usable session. The login form is the correct next screen, and
      // saying so in the console is noise on a first visit.
    } finally {
      setAuthChecked(true)
    }
  }, [])

  const handleLogout = useCallback(() => {
    api.logout()
    setUser(null)
    setPortfolioSummary(null)
    setCurrentQuarter('')
    showMessage('Logged out successfully', 'info')
  }, [showMessage])

  const loadData = useCallback(async () => {
    try {
      const [quarter, summary] = await Promise.all([
        api.getCurrentQuarter(),
        api.getPortfolioSummary()
      ])

      setCurrentQuarter(quarter.quarter)
      setPortfolioSummary(summary)
    } catch (error) {
      if (error.message.includes('Session expired')) {
        handleLogout()
        showMessage('Session expired, please log in again', 'error')
      } else {
        showMessage('Error loading data: ' + error.message, 'error')
      }
    }
  }, [handleLogout, showMessage])

  // The fetch-on-mount that set-state-in-effect warns about. The rule exists to
  // stop a synchronous setState from cascading renders; here the state is set
  // after an awaited request, and the project carries no data-fetching library
  // that would own this instead.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    checkAuth()
  }, [checkAuth])

  useEffect(() => {
    if (user) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadData()
    }
  }, [user, loadData])

  const handleLogin = async (credentials, isRegister) => {
    const result = isRegister
      ? await api.register(credentials)
      : await api.login(credentials)

    setUser(result.user)
    showMessage(`Welcome ${result.user.name}!`, 'success')
  }

  const handleAdvanceQuarter = async () => {
    const quarters = parseInt(quartersToAdvance) || 1
    if (quarters < 1 || quarters > 100) {
      showMessage('Please enter a number between 1 and 100', 'error')
      return
    }

    // No confirmation prompt - advance directly

    setLoading(true)
    try {
      let totalRenovationsCompleted = 0
      let finalQuarter = currentQuarter

      for (let i = 0; i < quarters; i++) {
        const result = await api.advanceQuarter()
        finalQuarter = result.quarter
        totalRenovationsCompleted += result.renovationsCompleted
      }

      setCurrentQuarter(finalQuarter)
      await loadData()
      
      // Force refresh of both views (Market and Portfolio)
      setPortfolioRefreshKey(prev => prev + 1)
      setMarketRefreshKey(prev => prev + 1)
      
      showMessage(
        `Advanced ${quarters} quarter${quarters > 1 ? 's' : ''} to ${finalQuarter}. ${totalRenovationsCompleted} renovation works completed.`,
        'success'
      )
    } catch (error) {
      showMessage('Error: ' + error.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  // What the server will allow, so the interface does not offer what it is
  // about to refuse. This is presentation, not protection: require_admin
  // decides, and it decides again for every request whatever is rendered here.
  const isAdmin = Boolean(user?.roles?.includes('admin'))

  const refreshData = () => {
    loadData()
  }

  // Show login if not authenticated
  if (!authChecked) {
    return <div className="app app-loading">Loading...</div>
  }

  if (!user) {
    return <Login onLogin={handleLogin} />
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-left">
          <h1>Real Estate Investing</h1>
          <div className="quarter-display">
            Quarter: <strong>{currentQuarter || 'Loading...'}</strong>
          </div>
        </div>
        <div className="topbar-right">
          <div className="user-info">
            <span>{user.name}</span>
            <button 
              className="btn btn-secondary" 
              onClick={handleLogout}
            >
              Log out
            </button>
          </div>
          {isAdmin && (
            <div className="quarter-advance-controls">
              <label className="visually-hidden" htmlFor="quarters-to-advance">
                Quarters to advance
              </label>
              <input
                id="quarters-to-advance"
                type="number"
                inputMode="numeric"
                min="1"
                max="100"
                value={quartersToAdvance}
                onChange={(e) => setQuartersToAdvance(e.target.value)}
                className="quarter-input"
                disabled={loading}
              />
              <button
                className="btn btn-primary"
                onClick={handleAdvanceQuarter}
                disabled={loading}
              >
                {loading ? 'Computing...' : 'Advance'}
              </button>
            </div>
          )}
        </div>
      </header>

      {message && (
        <div className={`message message-${message.type}`}>
          {message.text}
        </div>
      )}

      <nav className="navbar">
        <button 
          className={`nav-btn ${currentView === 'market' ? 'active' : ''}`}
          onClick={() => setCurrentView('market')}
        >
          Market
        </button>
        <button 
          className={`nav-btn ${currentView === 'portfolio' ? 'active' : ''}`}
          onClick={() => setCurrentView('portfolio')}
        >
          Portfolio
        </button>
      </nav>

      {portfolioSummary && (
        <div className="summary-bar">
          <div className="summary-item">
            <div className="summary-label">Cash</div>
            <div className="summary-value">{portfolioSummary.cash.toLocaleString('fr-BE')} €</div>
          </div>
          <div className="summary-item">
            <div className="summary-label">Holdings value</div>
            <div className="summary-value">{portfolioSummary.equity.toLocaleString('fr-BE')} €</div>
          </div>
          <div className="summary-item">
            <div className="summary-label">Total value</div>
            <div className="summary-value total">{portfolioSummary.totalValue.toLocaleString('fr-BE')} €</div>
          </div>
          <div className="summary-item">
            <div className="summary-label">P&L Total</div>
            <div className={`summary-value ${portfolioSummary.pnlTotal >= 0 ? 'positive' : 'negative'}`}>
              {portfolioSummary.pnlTotal >= 0 ? '+' : ''}{portfolioSummary.pnlTotal.toLocaleString('fr-BE')} €
            </div>
          </div>
        </div>
      )}

      <main className="main-content">
        {currentView === 'market' ? (
          <Market
            key={marketRefreshKey}
            onPurchase={refreshData}
            showMessage={showMessage}
            isAdmin={isAdmin}
          />
        ) : (
          <Portfolio 
            key={portfolioRefreshKey} 
            onSell={refreshData} 
            showMessage={showMessage} 
          />
        )}
      </main>
    </div>
  )
}

export default App
