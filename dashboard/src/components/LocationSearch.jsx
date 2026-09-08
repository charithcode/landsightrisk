import React, { useState, useRef, useEffect } from 'react'

const API_BASE = 'http://localhost:8000'

export default function LocationSearch({ onLocationSelect }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [showResults, setShowResults] = useState(false)
  const [selectedSummary, setSelectedSummary] = useState(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const inputRef = useRef(null)
  const dropdownRef = useRef(null)
  const debounceRef = useRef(null)

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)
          && inputRef.current && !inputRef.current.contains(e.target)) {
        setShowResults(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const doSearch = async (q) => {
    if (q.length < 1) { setResults([]); return }
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/locations/search?q=${encodeURIComponent(q)}`)
      if (res.ok) {
        const data = await res.json()
        setResults(data.results || [])
        setShowResults(true)
      }
    } catch (e) { /* ignore */ }
    setLoading(false)
  }

  const handleInput = (e) => {
    const val = e.target.value
    setQuery(val)
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => doSearch(val), 250)
  }

  const selectLocation = async (item) => {
    setQuery(item.display_name || item.name)
    setShowResults(false)

    if (item.supported && item.lat && item.lon) {
      // Fetch real local summary
      setSummaryLoading(true)
      try {
        const res = await fetch(
          `${API_BASE}/locations/summary?lat=${item.lat}&lon=${item.lon}&name=${encodeURIComponent(item.name)}`
        )
        if (res.ok) {
          const summary = await res.json()
          setSelectedSummary(summary)
          onLocationSelect?.({ ...item, summary })
        }
      } catch (e) {
        setSelectedSummary({ supported: false, message: 'Failed to load summary.' })
      }
      setSummaryLoading(false)
    } else {
      setSelectedSummary({
        name: item.name,
        supported: false,
        status: 'outside_aoi',
        message: `${item.name} is outside active monitoring coverage. Active coverage: Guwahati–Shillong NH-6 corridor.`,
      })
      onLocationSelect?.({ ...item, summary: null })
    }
  }

  const closeSummary = () => setSelectedSummary(null)

  const tierColors = {
    respond: '#ef4444', alert: '#f97316', watch: '#3b82f6', none: '#64748b',
  }

  return (
    <div style={{ position: 'relative' }}>
      {/* Search input */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        background: 'var(--bg-elevated)', borderRadius: 8,
        padding: '4px 8px', border: '1px solid var(--bg-border)',
      }}>
        <span style={{ fontSize: 13, opacity: 0.6 }}>📍</span>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={handleInput}
          onFocus={() => results.length > 0 && setShowResults(true)}
          placeholder="Search place, district, road…"
          style={{
            background: 'transparent', border: 'none', outline: 'none',
            color: 'var(--text-primary)', fontSize: 11, flex: 1,
            fontFamily: 'var(--font-sans)',
          }}
          id="location-search-input"
        />
        {loading && <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>…</span>}
      </div>

      {/* Results dropdown */}
      {showResults && results.length > 0 && (
        <div ref={dropdownRef} style={{
          position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 100,
          background: 'var(--bg-card)', border: '1px solid var(--bg-border)',
          borderRadius: 8, marginTop: 4, maxHeight: 240, overflowY: 'auto',
          boxShadow: 'var(--shadow-card)',
        }}>
          {results.map((item, i) => (
            <div
              key={i}
              onClick={() => selectLocation(item)}
              style={{
                padding: '8px 10px', cursor: 'pointer', fontSize: 11,
                borderBottom: '1px solid var(--bg-border)',
                display: 'flex', alignItems: 'center', gap: 8,
                transition: 'background 0.15s',
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = 'var(--bg-elevated)'}
              onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
              id={`search-result-${i}`}
            >
              <span style={{ fontSize: 14 }}>
                {item.type === 'state' ? '🗺' : item.type === 'district' ? '📌' : '📍'}
              </span>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                  {item.display_name || item.name}
                </div>
                {item.type && (
                  <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 1 }}>
                    {item.type}
                  </div>
                )}
              </div>
              <span style={{
                fontSize: 8, padding: '2px 6px', borderRadius: 4,
                background: item.supported ? 'rgba(34,197,94,0.12)' : 'rgba(148,163,184,0.12)',
                color: item.supported ? '#22c55e' : '#94a3b8',
                fontWeight: 600,
              }}>
                {item.supported ? 'ACTIVE' : 'PENDING'}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Location summary panel */}
      {selectedSummary && (
        <div className="fade-in" style={{
          position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 99,
          background: 'var(--bg-card)', border: '1px solid var(--bg-border)',
          borderRadius: 8, marginTop: 4, padding: '10px 12px',
          boxShadow: 'var(--shadow-card)',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)' }}>
              {selectedSummary.name || 'Location'}
            </span>
            <button onClick={closeSummary} style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--text-muted)', fontSize: 14,
            }}>✕</button>
          </div>

          {summaryLoading && (
            <div style={{ fontSize: 10, color: 'var(--text-muted)', padding: 8 }}>Loading…</div>
          )}

          {!summaryLoading && !selectedSummary.supported && (
            <div style={{
              fontSize: 10, color: '#94a3b8', lineHeight: 1.6,
              background: 'rgba(148,163,184,0.06)', borderRadius: 6, padding: 8,
            }}>
              ⚠ {selectedSummary.message}
            </div>
          )}

          {!summaryLoading && selectedSummary.supported && (
            <div style={{ fontSize: 10, lineHeight: 1.8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <span className={`tier-badge tier-${selectedSummary.local_tier || 'none'}`}>
                  {selectedSummary.local_tier || 'none'}
                </span>
                <span style={{ color: 'var(--text-muted)' }}>
                  max risk: <span style={{
                    fontFamily: 'var(--font-mono)',
                    color: tierColors[selectedSummary.local_tier] || '#64748b',
                  }}>{(selectedSummary.max_risk_in_radius || 0).toFixed(3)}</span>
                </span>
              </div>
              <div style={{ color: 'var(--text-secondary)' }}>
                Exposed roads nearby: <strong>{selectedSummary.nearby_exposed_roads_count || 0}</strong>
                <br/>
                Communities nearby: <strong>{selectedSummary.nearby_communities_count || 0}</strong>
              </div>
              {selectedSummary.nearby_roads?.length > 0 && (
                <div style={{ marginTop: 6 }}>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}>
                    Nearest roads:
                  </div>
                  {selectedSummary.nearby_roads.slice(0, 3).map((r, i) => (
                    <div key={i} style={{ color: 'var(--text-muted)', paddingLeft: 8 }}>
                      {r.name || r.highway || `seg ${r.seg_id}`}
                      — risk: <span style={{ fontFamily: 'var(--font-mono)' }}>{(r.risk_max || 0).toFixed(3)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
