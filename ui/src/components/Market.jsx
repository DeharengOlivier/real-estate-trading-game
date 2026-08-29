import { useState, useEffect } from 'react'
import { api } from '../api'

// isAdmin decides what this component offers. It is not a security boundary:
// the server checks the role again on every request, and would refuse these
// calls from a player who reached them another way. It is here so the
// interface does not present a button that is going to answer 403.
function Market({ onPurchase, showMessage, isAdmin = false }) {
  const [listings, setListings] = useState([])
  const [filters, setFilters] = useState({
    zone: '',
    type: '',
    minPrice: '',
    maxPrice: ''
  })
  const [loading, setLoading] = useState(false)
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 50,
    total: 0,
    totalPages: 1
  })
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [newProperty, setNewProperty] = useState({
    zone: 'Bruxelles-Centre',
    type: 'apartment',
    surface: 100
  })

  useEffect(() => {
    loadListings()
  }, [])

  const loadListings = async () => {
    setLoading(true)
    try {
      const data = await api.getListings({ ...filters, page: pagination.page, limit: pagination.limit })
      setListings(data.items || [])
      setPagination({
        page: data.page || 1,
        limit: data.limit || 50,
        total: data.total || 0,
        totalPages: data.totalPages || 1
      })
    } catch (error) {
      console.error('Error loading listings:', error)
      showMessage('Error loading listings: ' + error.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleFilterChange = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }))
  }

  const handleSearch = () => {
    loadListings()
  }

  const handleBuy = async (propertyId) => {
    if (!confirm('Confirm the purchase of this property?')) return

    try {
      const result = await api.buyProperty(propertyId)
      showMessage(
        `Property purchased! Price: ${result.price.toLocaleString('fr-BE')} € • Fees: ${result.fees.toLocaleString('fr-BE')} € • Total: ${result.totalCost.toLocaleString('fr-BE')} €`,
        'success'
      )
      await loadListings()
      if (onPurchase) onPurchase()
    } catch (error) {
      showMessage('Error: ' + error.message, 'error')
    }
  }

  const handleDelete = async (propertyId) => {
    if (!confirm('Delete this property?\n\nThis action is irreversible and permanently removes the property from the game.')) return

    try {
      await api.deleteProperty(propertyId)
      showMessage('Property deleted successfully', 'success')
      await loadListings()
    } catch (error) {
      showMessage('Error: ' + error.message, 'error')
    }
  }

  const handleCreate = async () => {
    try {
      // Base PPM values for each zone and type (from constants)
      const basePPM = {
        'Bruxelles-Centre': { apartment: 4200, house: 3800 },
        'Ixelles': { apartment: 3800, house: 3500 },
        'Uccle': { apartment: 3500, house: 3200 },
        'Schaerbeek': { apartment: 2800, house: 2600 },
        'Liège-Centre': { apartment: 2400, house: 2200 },
        'Liège-Sud': { apartment: 2100, house: 1900 },
        'Namur-Est': { apartment: 2300, house: 2100 },
        'Namur-Centre': { apartment: 2500, house: 2300 },
        'Gand-Centre': { apartment: 3000, house: 2800 },
        'Anvers-Nord': { apartment: 2900, house: 2700 },
        'Anvers-Sud': { apartment: 3200, house: 3000 },
        'Charleroi-Ville': { apartment: 1800, house: 1600 }
      }

      // Generate random characteristics (0.0 to 1.0)
      const propertyData = {
        zone: newProperty.zone,
        type: newProperty.type,
        surface: parseFloat(newProperty.surface),
        base_ppm: basePPM[newProperty.zone][newProperty.type],
        epc: Math.random() * 0.5 + 0.3,        // 0.3 to 0.8
        state: Math.random() * 0.5 + 0.3,      // 0.3 to 0.8
        kitchen: Math.random() * 0.5 + 0.3,    // 0.3 to 0.8
        bath: Math.random() * 0.5 + 0.3        // 0.3 to 0.8
      }

      await api.createProperty(propertyData)
      showMessage('Property created successfully!', 'success')
      setShowCreateForm(false)
      await loadListings()
    } catch (error) {
      showMessage('Error: ' + error.message, 'error')
    }
  }

  return (
    <div>
      <div className="filters">
        <div className="filters-grid">
          <div className="filter-group">
            <label>Zone</label>
            <select 
              value={filters.zone} 
              onChange={(e) => handleFilterChange('zone', e.target.value)}
            >
              <option value="">All zones</option>
              <option value="Bruxelles-Centre">Bruxelles-Centre</option>
              <option value="Ixelles">Ixelles</option>
              <option value="Uccle">Uccle</option>
              <option value="Schaerbeek">Schaerbeek</option>
              <option value="Liège-Centre">Liège-Centre</option>
              <option value="Liège-Sud">Liège-Sud</option>
              <option value="Namur-Est">Namur-Est</option>
              <option value="Namur-Centre">Namur-Centre</option>
              <option value="Gand-Centre">Gand-Centre</option>
              <option value="Anvers-Nord">Anvers-Nord</option>
              <option value="Anvers-Sud">Anvers-Sud</option>
              <option value="Charleroi-Ville">Charleroi-Ville</option>
            </select>
          </div>

          <div className="filter-group">
            <label>Type</label>
            <select 
              value={filters.type} 
              onChange={(e) => handleFilterChange('type', e.target.value)}
            >
              <option value="">All types</option>
              <option value="house">House</option>
              <option value="apartment">Apartment</option>
            </select>
          </div>

          <div className="filter-group">
            <label>Min price (€)</label>
            <input 
              type="number" 
              value={filters.minPrice}
              onChange={(e) => handleFilterChange('minPrice', e.target.value)}
              placeholder="0"
            />
          </div>

          <div className="filter-group">
            <label>Max price (€)</label>
            <input 
              type="number" 
              value={filters.maxPrice}
              onChange={(e) => handleFilterChange('maxPrice', e.target.value)}
              placeholder="Unlimited"
            />
          </div>
        </div>
        <div className="filter-actions">
          <button 
            className="btn btn-primary" 
            onClick={handleSearch}
          >
            Search
          </button>
          {isAdmin && (
            <button
              className="btn btn-success"
              onClick={() => setShowCreateForm(true)}
            >
              Create a property
            </button>
          )}
        </div>
      </div>

      {/* Create Property Modal */}
      {showCreateForm && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-header">
              <h2 className="modal-title">Create a new property</h2>
            </div>

            <div className="modal-field">
              <label htmlFor="new-property-zone">Zone</label>
              <select
                id="new-property-zone"
                value={newProperty.zone}
                onChange={(e) => setNewProperty({ ...newProperty, zone: e.target.value })}
              >
                <option value="Bruxelles-Centre">Bruxelles-Centre</option>
                <option value="Ixelles">Ixelles</option>
                <option value="Uccle">Uccle</option>
                <option value="Schaerbeek">Schaerbeek</option>
                <option value="Liège-Centre">Liège-Centre</option>
                <option value="Liège-Sud">Liège-Sud</option>
                <option value="Namur-Est">Namur-Est</option>
                <option value="Namur-Centre">Namur-Centre</option>
                <option value="Gand-Centre">Gand-Centre</option>
                <option value="Anvers-Nord">Anvers-Nord</option>
                <option value="Anvers-Sud">Anvers-Sud</option>
                <option value="Charleroi-Ville">Charleroi-Ville</option>
              </select>
            </div>

            <div className="modal-field">
              <label htmlFor="new-property-type">Type</label>
              <select
                id="new-property-type"
                value={newProperty.type}
                onChange={(e) => setNewProperty({ ...newProperty, type: e.target.value })}
              >
                <option value="apartment">Apartment</option>
                <option value="house">House</option>
              </select>
            </div>

            <div className="modal-field">
              <label htmlFor="new-property-surface">
                Floor area: {newProperty.surface} m²
              </label>
              <input
                id="new-property-surface"
                type="range"
                min="50"
                max="400"
                step="10"
                value={newProperty.surface}
                onChange={(e) => setNewProperty({ ...newProperty, surface: e.target.value })}
              />
              <div className="modal-field-hint">
                <span>50 m²</span>
                <span>400 m²</span>
              </div>
            </div>

            <div className="modal-preview">
              <p><strong>Automatic characteristics</strong></p>
              <p>
                The characteristics (EPC, condition, kitchen, bathroom) will be generated automatically with realistic random values.
              </p>
            </div>

            <div className="modal-actions">
              <button className="btn btn-success" onClick={handleCreate}>
                Create
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => setShowCreateForm(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="empty-state">
          <div className="empty-state-icon"></div>
          <div className="empty-state-text">Loading...</div>
        </div>
      ) : listings.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon"></div>
          <div className="empty-state-text">No properties available for these criteria</div>
        </div>
      ) : (
        <>
          <div className="pagination-info">
            Showing {listings.length} of {pagination.total} properties | Page {pagination.page} / {pagination.totalPages}
          </div>
          <div className="properties-grid">
            {listings.map(property => (
              <div key={property.propertyId} className="property-card">
                {isAdmin && (
                  <button
                    className="property-delete"
                    onClick={() => handleDelete(property.propertyId)}
                    title="Delete this property"
                    aria-label={`Delete the ${property.surface} m² property in ${property.zone}`}
                  >
                    ✕
                  </button>
                )}
                <span className="property-type">
                  {property.type === 'house' ? 'House' : 'Apartment'}
                </span>
                <div className="property-zone">
                  {property.zone}
                  {property.zoneTrendAnnual > 0 && (
                    <span style={{ 
                      marginLeft: '0.5rem', 
                      fontSize: '0.85rem',
                      color: property.zoneTrendAnnual > 5 ? '#10b981' : property.zoneTrendAnnual > 3 ? '#3b82f6' : '#6b7280'
                    }}>
                      +{property.zoneTrendAnnual}%/yr
                    </span>
                  )}
                </div>
                
                <div className="property-details">
                  <div>{property.surface.toFixed(0)} m²</div>
                  <div>Quality: {property.qualityScore}%</div>
                  <div>EPC: {property.epcScore}%</div>
                  <div>Condition: {property.stateScore}%</div>
                  <div>Kitchen: {property.kitchenScore}%</div>
                  <div>Bathroom: {property.bathScore}%</div>
                </div>

                <div style={{ 
                  marginTop: '0.75rem', 
                  padding: '0.5rem', 
                  backgroundColor: '#f3f4f6', 
                  borderRadius: '4px',
                  fontSize: '0.85rem'
                }}>
                  <div style={{ fontWeight: 'bold', marginBottom: '0.25rem' }}>
                    Price: {property.price.toLocaleString('fr-BE')} €
                  </div>
                  <div style={{ color: '#6b7280' }}>
                    {property.pricePerM2.toLocaleString('fr-BE')} €/m² • Base: {property.basePpm.toLocaleString('fr-BE')} €/m²
                  </div>
                  <div style={{ 
                    marginTop: '0.5rem', 
                    paddingTop: '0.5rem', 
                    borderTop: '1px solid #d1d5db',
                    color: '#059669'
                  }}>
                    1-year estimate: {property.estimated1YearPrice.toLocaleString('fr-BE')} €
                    <div style={{ fontSize: '0.8rem', color: '#6b7280' }}>
                      Potential gain: +{property.estimated1YearGain.toLocaleString('fr-BE')} € ({property.estimated1YearGainPct}%)
                    </div>
                  </div>
                </div>

                <div className="property-actions">
                  <button 
                    className="btn btn-success"
                    onClick={() => handleBuy(property.propertyId)}
                  >
                    Buy (+ {(property.price * 0.025).toLocaleString('fr-BE')} € fees)
                  </button>
                </div>
              </div>
            ))}
          </div>
          {pagination.totalPages > 1 && (
            <div className="pagination-controls">
              <button
                className="btn btn-secondary"
                disabled={pagination.page <= 1}
                onClick={() => {
                  setPagination(prev => ({ ...prev, page: prev.page - 1 }))
                  setTimeout(loadListings, 100)
                }}
              >
                ← Previous
              </button>
              <button
                className="btn btn-secondary"
                disabled={pagination.page >= pagination.totalPages}
                onClick={() => {
                  setPagination(prev => ({ ...prev, page: prev.page + 1 }))
                  setTimeout(loadListings, 100)
                }}
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default Market
