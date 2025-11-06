import { useState, useEffect } from 'react'
import { api } from '../api'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'

function Portfolio({ onSell, showMessage }) {
  const [holdings, setHoldings] = useState([])
  const [equityData, setEquityData] = useState([])
  const [renovations, setRenovations] = useState([])
  const [selectedHolding, setSelectedHolding] = useState(null)
  const [showRenovationModal, setShowRenovationModal] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [holdingsData, equityChartData, renosData] = await Promise.all([
        api.getHoldings(),
        api.getPortfolioEquityChart(),
        api.getRenovations()
      ])
      
      setHoldings(holdingsData)
      setEquityData(equityChartData)
      setRenovations(renosData)
    } catch (error) {
      console.error('Error loading portfolio:', error)
      showMessage('Error loading portfolio: ' + error.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleSell = async (propertyId) => {
    if (!confirm('Confirm the sale of this property?')) return

    try {
      const result = await api.sellProperty(propertyId)
      showMessage(
        `Property sold! Price: ${result.sellPrice.toLocaleString('fr-BE')} € • Fees: ${result.fees.toLocaleString('fr-BE')} € • Net: ${result.netProceeds.toLocaleString('fr-BE')} € • P&L: ${result.pnl >= 0 ? '+' : ''}${result.pnl.toLocaleString('fr-BE')} €`,
        'success'
      )
      await loadData()
      if (onSell) onSell()
    } catch (error) {
      showMessage('Error: ' + error.message, 'error')
    }
  }

  const handleStartRenovation = (holding) => {
    setSelectedHolding(holding)
    setShowRenovationModal(true)
  }

  const handleRenovationSelect = async (renoCode) => {
    if (!selectedHolding) return

    try {
      const result = await api.startRenovation(selectedHolding.holdingId, renoCode)
      showMessage(
        `Renovation started: ${renoCode}. Expected completion: ${result.endQuarter}`,
        'success'
      )
      setShowRenovationModal(false)
      setSelectedHolding(null)
      await loadData()
      if (onSell) onSell()
    } catch (error) {
      showMessage('Error: ' + error.message, 'error')
    }
  }

  if (loading) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon"></div>
        <div className="empty-state-text">Loading...</div>
      </div>
    )
  }

  return (
    <div>
      {/* Equity Chart */}
      {equityData.length > 0 && (
        <div className="chart-container">
          <h2 className="chart-title">Portfolio value over time</h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={equityData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="quarter" />
              <YAxis />
              <Tooltip formatter={(value) => `${value.toLocaleString('fr-BE')} €`} />
              <Legend />
              <Line 
                type="monotone" 
                dataKey="equity" 
                stroke="#667eea" 
                strokeWidth={2}
                name="Holdings value"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Holdings */}
      <h2 className="chart-title">My properties</h2>
      
      {holdings.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon"></div>
          <div className="empty-state-text">No properties in your portfolio</div>
        </div>
      ) : (
        <div className="holdings-list">
          {holdings.map(holding => (
            <div key={holding.holdingId} className="holding-card">
              <div className="holding-header">
                <div className="holding-info">
                  <h3>
                    {holding.zone}
                  </h3>
                  <div className="holding-meta">
                    {holding.surface.toFixed(0)} m² • {holding.type === 'house' ? 'House' : 'Apartment'}
                    {holding.ongoingWorks > 0 && (
                      <span style={{ marginLeft: '1rem', color: '#f59e0b' }}>
                        🔨 {holding.ongoingWorks} renovation(s) in progress
                      </span>
                    )}
                  </div>
                </div>
              </div>

              <div className="holding-stats">
                <div className="stat-item">
                  <div className="stat-label">Buy price</div>
                  <div className="stat-value">{holding.buyPrice.toLocaleString('fr-BE')} €</div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">Purchase fees</div>
                  <div className="stat-value">{holding.buyFees.toLocaleString('fr-BE')} €</div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">Renovations</div>
                  <div className="stat-value">{holding.renovationCosts.toLocaleString('fr-BE')} €</div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">Total invested</div>
                  <div className="stat-value" style={{ fontWeight: 'bold' }}>
                    {holding.totalInvested.toLocaleString('fr-BE')} €
                  </div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">Current value</div>
                  <div className="stat-value">{holding.currentPrice.toLocaleString('fr-BE')} €</div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">P&L</div>
                  <div className={`stat-value ${holding.pnl >= 0 ? 'positive' : 'negative'}`}>
                    {holding.pnl >= 0 ? '+' : ''}{holding.pnl.toLocaleString('fr-BE')} €
                  </div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">P&L %</div>
                  <div className={`stat-value ${holding.pnlPct >= 0 ? 'positive' : 'negative'}`}>
                    {holding.pnlPct >= 0 ? '+' : ''}{holding.pnlPct.toFixed(1)}%
                  </div>
                </div>
              </div>

              <div className="holding-actions">
                <button 
                  className="btn btn-primary"
                  onClick={() => {
                    setSelectedHolding(holding)
                    setShowRenovationModal(true)
                  }}
                  disabled={holding.ongoingWorks > 0}
                >
                  Start renovation
                </button>
                <button
                  className="btn btn-danger"
                  onClick={() => handleSell(holding.propertyId)}
                  disabled={holding.ongoingWorks > 0}
                >
                  Sell
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Renovation Modal */}
      {showRenovationModal && (
        <div className="modal-overlay" onClick={() => setShowRenovationModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">🔨 Choose a renovation</h2>
              <button 
                className="modal-close"
                onClick={() => setShowRenovationModal(false)}
              >
                ×
              </button>
            </div>

            <div className="renovation-list">
              {renovations.map(reno => (
                <div 
                  key={reno.code}
                  className="renovation-item"
                  onClick={() => handleRenovationSelect(reno.code)}
                >
                  <div className="renovation-name">{reno.label}</div>
                  <div className="renovation-details">
                    {reno.cost.toLocaleString('fr-BE')} € •
                    {reno.durationQ} quarter{reno.durationQ > 1 ? 's' : ''}
                  </div>
                  <div className="renovation-details" style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}>
                    {reno.delta.epc !== 0 && `EPC: +${(reno.delta.epc * 100).toFixed(0)}% `}
                    {reno.delta.state !== 0 && `Condition: +${(reno.delta.state * 100).toFixed(0)}% `}
                    {reno.delta.kitchen !== 0 && `Kitchen: +${(reno.delta.kitchen * 100).toFixed(0)}% `}
                    {reno.delta.bath !== 0 && `Bathroom: +${(reno.delta.bath * 100).toFixed(0)}% `}
                    {reno.delta.surfacePct !== 0 && `Floor area: +${(reno.delta.surfacePct * 100).toFixed(0)}% `}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Portfolio
