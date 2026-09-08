import React, { useState, useEffect, useRef } from 'react'

const API_BASE = 'http://localhost:8000'

export default function LocationControl({ onLocationSelect, currentSelected }) {
  const [catalog, setCatalog] = useState([])
  const [selectedState, setSelectedState] = useState('')
  const [selectedDistrict, setSelectedDistrict] = useState('')
  const [selectedPlace, setSelectedPlace] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [isSearching, setIsSearching] = useState(false)
  const [showDropdown, setShowDropdown] = useState(false)

  const searchInputRef = useRef(null)
  const dropdownRef = useRef(null)
  const debounceRef = useRef(null)

  // Fetch catalog on mount
  useEffect(() => {
    async function loadCatalog() {
      try {
        const res = await fetch(`${API_BASE}/locations/hierarchy`)
        if (res.ok) {
          const data = await res.json()
          const cat = data.catalog || []
          setCatalog(cat)
          // Default selection to Meghalaya / Ri-Bhoi / Byrnihat or first supported
          const meghalaya = cat.find(s => s.name.toLowerCase() === 'meghalaya')
          if (meghalaya) {
            setSelectedState('Meghalaya')
            const ribhoi = meghalaya.districts?.find(d => d.name.toLowerCase().includes('ri-bhoi'))
            if (ribhoi) {
              setSelectedDistrict(ribhoi.name)
              const byrnihat = ribhoi.places?.find(p => p.name.toLowerCase().includes('byrnihat'))
              if (byrnihat) setSelectedPlace(byrnihat.name)
            }
          }
        }
      } catch (err) {
        console.warn('Failed to load locations catalog:', err)
      }
    }
    loadCatalog()
  }, [])

  // Close search dropdown on click outside
  useEffect(() => {
    const handleClick = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target) &&
          searchInputRef.current && !searchInputRef.current.contains(e.target)) {
        setShowDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const currentStateObj = catalog.find(s => s.name === selectedState)
  const districts = currentStateObj?.districts || []
  const currentDistrictObj = districts.find(d => d.name === selectedDistrict)
  const places = currentDistrictObj?.places || []

  // Execute location selection
  const handleSelectLocation = async (item) => {
    setShowDropdown(false)
    setSearchQuery('')
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
      // Explicitly outside active analysis coverage
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
  }

  // Hierarchy dropdown handlers
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
    const distObj = districts.find(d => d.name === dt)
    if (distObj?.center) {
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

  // Free text search
  const handleSearchInput = (e) => {
    const val = e.target.value
    setSearchQuery(val)
    clearTimeout(debounceRef.current)
    if (val.trim().length === 0) {
      setSearchResults([])
      setShowDropdown(false)
      return
    }
    debounceRef.current = setTimeout(async () => {
      setIsSearching(true)
      try {
        const res = await fetch(`${API_BASE}/locations/search?q=${encodeURIComponent(val)}`)
        if (res.ok) {
          const data = await res.json()
          setSearchResults(data.results || [])
          setShowDropdown(true)
        }
      } catch (err) {
        // ignore
      }
      setIsSearching(false)
    }, 200)
  }

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      background: 'var(--bg-surface)',
      border: '1px solid var(--border-medium)',
      borderRadius: 4,
      padding: '3px 10px',
      fontSize: 11,
      position: 'relative',
      maxWidth: 580,
    }}>
      {/* Label */}
      <span style={{
        fontSize: 9,
        fontWeight: 700,
        letterSpacing: '0.08em',
        color: 'var(--text-muted)',
        textTransform: 'uppercase',
      }}>
        Location
      </span>

      {/* State / District / Place Cascade Breadcrumbs */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <select
          value={selectedState}
          onChange={handleStateChange}
          style={{
            background: 'transparent',
            color: 'var(--text-primary)',
            border: 'none',
            fontSize: 11,
            fontWeight: 500,
            cursor: 'pointer',
            outline: 'none',
            paddingRight: 2,
          }}
        >
          {catalog.map(s => (
            <option key={s.name} value={s.name} style={{ background: '#0d121c', color: '#e2e8f0' }}>
              {s.name}
            </option>
          ))}
        </select>

        <span style={{ color: 'var(--text-dim)', fontSize: 11 }}>/</span>

        <select
          value={selectedDistrict}
          onChange={handleDistrictChange}
          style={{
            background: 'transparent',
            color: 'var(--text-primary)',
            border: 'none',
            fontSize: 11,
            fontWeight: 500,
            cursor: 'pointer',
            outline: 'none',
            paddingRight: 2,
          }}
        >
          <option value="" style={{ background: '#0d121c', color: '#64748b' }}>District</option>
          {districts.map(d => (
            <option key={d.name} value={d.name} style={{ background: '#0d121c', color: '#e2e8f0' }}>
              {d.name}
            </option>
          ))}
        </select>

        <span style={{ color: 'var(--text-dim)', fontSize: 11 }}>/</span>

        <select
          value={selectedPlace}
          onChange={handlePlaceChange}
          style={{
            background: 'transparent',
            color: selectedPlace ? 'var(--text-bright)' : 'var(--text-muted)',
            border: 'none',
            fontSize: 11,
            fontWeight: selectedPlace ? 600 : 400,
            cursor: 'pointer',
            outline: 'none',
          }}
        >
          <option value="" style={{ background: '#0d121c', color: '#64748b' }}>Corridor / Place</option>
          {places.map(p => (
            <option key={p.name} value={p.name} style={{ background: '#0d121c', color: '#e2e8f0' }}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      <div style={{ width: 1, height: 16, background: 'var(--border-medium)' }} />

      {/* Professional GIS search box */}
      <div style={{ position: 'relative', flex: 1, minWidth: 140 }}>
        <input
          ref={searchInputRef}
          type="text"
          value={searchQuery}
          onChange={handleSearchInput}
          placeholder="Search place..."
          onFocus={() => searchResults.length > 0 && setShowDropdown(true)}
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--text-primary)',
            fontSize: 11,
            width: '100%',
            outline: 'none',
            padding: '2px 0',
          }}
        />

        {/* Search Results Dropdown */}
        {showDropdown && searchResults.length > 0 && (
          <div
            ref={dropdownRef}
            style={{
              position: 'absolute',
              top: 'calc(100% + 8px)',
              left: 0,
              width: 260,
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-bright)',
              borderRadius: 4,
              boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
              zIndex: 100,
              maxHeight: 220,
              overflowY: 'auto',
            }}
          >
            <div style={{ padding: '4px 8px', fontSize: 9, color: 'var(--text-muted)', borderBottom: '1px solid var(--border-subtle)', fontWeight: 600 }}>
              MATCHED LOCATIONS
            </div>
            {searchResults.map((item, idx) => (
              <div
                key={idx}
                onClick={() => handleSelectLocation(item)}
                style={{
                  padding: '6px 10px',
                  cursor: 'pointer',
                  borderBottom: '1px solid var(--border-subtle)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'var(--bg-hover)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
              >
                <div>
                  <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-bright)' }}>
                    {item.name}
                  </div>
                  <div style={{ fontSize: 9, color: 'var(--text-muted)' }}>
                    {item.district ? `${item.district}, ` : ''}{item.state}
                  </div>
                </div>
                <span style={{
                  fontSize: 8,
                  fontFamily: 'var(--font-mono)',
                  fontWeight: 600,
                  padding: '1px 4px',
                  borderRadius: 2,
                  color: item.supported ? 'var(--accent-teal)' : 'var(--text-muted)',
                  border: `1px solid ${item.supported ? 'rgba(13,148,136,0.3)' : 'var(--border-subtle)'}`,
                }}>
                  {item.supported ? 'ACTIVE AOI' : 'EXTERNAL'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
