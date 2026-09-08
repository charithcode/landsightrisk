import React, { useState, useEffect } from 'react'

const API_BASE = 'http://localhost:8000'

export default function HierarchySelector({ onLocationSelect, currentSelected }) {
  const [catalog, setCatalog] = useState([])
  const [selectedState, setSelectedState] = useState('')
  const [selectedDistrict, setSelectedDistrict] = useState('')
  const [selectedPlace, setSelectedPlace] = useState('')
  const [loading, setLoading] = useState(false)

  // Load location hierarchy on mount
  useEffect(() => {
    async function fetchHierarchy() {
      try {
        const res = await fetch(`${API_BASE}/locations/hierarchy`)
        if (res.ok) {
          const data = await res.json()
          setCatalog(data.catalog || [])
          // Set default selection if available
          if (data.catalog?.length > 0) {
            setSelectedState('Assam')
            const assam = data.catalog.find(s => s.name === 'Assam')
            if (assam && assam.districts?.length > 0) {
              setSelectedDistrict(assam.districts[0].name)
            }
          }
        }
      } catch (err) {
        console.warn('Failed to fetch location hierarchy:', err)
      }
    }
    fetchHierarchy()
  }, [])

  const currentStateObj = catalog.find(s => s.name === selectedState)
  const districts = currentStateObj?.districts || []
  const currentDistrictObj = districts.find(d => d.name === selectedDistrict)
  const places = currentDistrictObj?.places || []

  const handleStateChange = (e) => {
    const st = e.target.value
    setSelectedState(st)
    const stObj = catalog.find(s => s.name === st)
    const firstDist = stObj?.districts?.[0]?.name || ''
    setSelectedDistrict(firstDist)
    setSelectedPlace('')
  }

  const handleDistrictChange = (e) => {
    const dt = e.target.value
    setSelectedDistrict(dt)
    setSelectedPlace('')
    // If district has center coordinates, trigger overview
    const distObj = districts.find(d => d.name === dt)
    if (distObj && distObj.center) {
      const [lon, lat] = distObj.center
      handleSelectLocation({
        name: distObj.name,
        lat,
        lon,
        supported: distObj.supported,
        place_type: 'district',
      })
    }
  }

  const handlePlaceChange = (e) => {
    const plName = e.target.value
    setSelectedPlace(plName)
    const plObj = places.find(p => p.name === plName)
    if (plObj) {
      handleSelectLocation(plObj)
    }
  }

  const handleSelectLocation = async (item) => {
    setLoading(true)
    if (item.supported && item.lat && item.lon) {
      try {
        const res = await fetch(
          `${API_BASE}/locations/summary?lat=${item.lat}&lon=${item.lon}&name=${encodeURIComponent(item.name)}`
        )
        if (res.ok) {
          const summary = await res.json()
          onLocationSelect?.({ ...item, summary })
        } else {
          onLocationSelect?.({ ...item, summary: null })
        }
      } catch (e) {
        onLocationSelect?.({ ...item, summary: null })
      }
    } else {
      // Location outside active monitoring coverage
      onLocationSelect?.({
        ...item,
        summary: {
          name: item.name,
          supported: false,
          status: 'outside_aoi',
          message: `${item.name} is outside active monitoring coverage. Active coverage: Guwahati–Shillong NH-6 corridor.`,
        },
      })
    }
    setLoading(false)
  }

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      background: 'var(--bg-elevated, #131d2e)',
      border: '1px solid var(--bg-border, rgba(255,255,255,0.08))',
      borderRadius: 8,
      padding: '3px 8px',
      fontSize: 11,
    }}>
      <span style={{ color: 'var(--text-muted, #94a3b8)', fontSize: 10, fontWeight: 600, textTransform: 'uppercase' }}>
        Region:
      </span>

      {/* State Dropdown */}
      <select
        value={selectedState}
        onChange={handleStateChange}
        style={{
          background: 'var(--bg-base, #0b1120)',
          color: 'var(--text-primary, #f1f5f9)',
          border: '1px solid var(--bg-border, rgba(255,255,255,0.1))',
          borderRadius: 6,
          padding: '3px 6px',
          fontSize: 11,
          outline: 'none',
          cursor: 'pointer',
        }}
      >
        {catalog.map(st => (
          <option key={st.name} value={st.name}>
            {st.name} {st.supported ? '' : '(unsupported)'}
          </option>
        ))}
      </select>

      {/* District Dropdown */}
      <select
        value={selectedDistrict}
        onChange={handleDistrictChange}
        style={{
          background: 'var(--bg-base, #0b1120)',
          color: 'var(--text-primary, #f1f5f9)',
          border: '1px solid var(--bg-border, rgba(255,255,255,0.1))',
          borderRadius: 6,
          padding: '3px 6px',
          fontSize: 11,
          outline: 'none',
          cursor: 'pointer',
        }}
      >
        <option value="">-- District --</option>
        {districts.map(dt => (
          <option key={dt.name} value={dt.name}>
            {dt.name} {dt.supported ? '' : '(outside AOI)'}
          </option>
        ))}
      </select>

      {/* Place Dropdown */}
      <select
        value={selectedPlace}
        onChange={handlePlaceChange}
        style={{
          background: 'var(--bg-base, #0b1120)',
          color: 'var(--text-primary, #f1f5f9)',
          border: '1px solid var(--bg-border, rgba(255,255,255,0.1))',
          borderRadius: 6,
          padding: '3px 6px',
          fontSize: 11,
          outline: 'none',
          cursor: 'pointer',
        }}
      >
        <option value="">-- Place / Corridor --</option>
        {places.map(pl => (
          <option key={pl.name} value={pl.name}>
            {pl.name} {pl.supported ? '' : '(outside AOI)'}
          </option>
        ))}
      </select>

      {loading && (
        <span style={{ fontSize: 10, color: 'var(--accent-cyan, #06b6d4)' }}>
          Loading...
        </span>
      )}
    </div>
  )
}
