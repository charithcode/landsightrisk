import React, { useEffect, useRef, useState } from 'react'

// MapLibre GL JS — free, no token
const MAPLIBRE_CDN = 'https://unpkg.com/maplibre-gl@4.1.0/dist/maplibre-gl.js'
const MAPLIBRE_CSS = 'https://unpkg.com/maplibre-gl@4.1.0/dist/maplibre-gl.css'

const API_BASE = 'http://localhost:8000'

// NH-6 corridor center
const MAP_CENTER = [91.82, 25.92]
const MAP_ZOOM   = 9.5

function loadMapLibre(cb) {
  if (window.maplibregl) { cb(); return }
  const link = document.createElement('link')
  link.rel = 'stylesheet'; link.href = MAPLIBRE_CSS
  document.head.appendChild(link)
  const script = document.createElement('script')
  script.src = MAPLIBRE_CDN; script.onload = cb
  document.head.appendChild(script)
}

export default function RiskMap({
  riskData, reportsData, impactData, exposedData,
  activeLayer, onLayerChange,
  onCellSelect, selectedCell,
  focusLocation,
}) {
  const mapContainer = useRef(null)
  const map = useRef(null)
  const [mapReady, setMapReady] = useState(false)
  const [popup, setPopup] = useState(null)
  const [rasterBounds, setRasterBounds] = useState(null)

  // Fetch raster bounds once on mount
  useEffect(() => {
    fetch(`${API_BASE}/risk/bounds`)
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setRasterBounds(d))
      .catch(() => {})
  }, [])

  // Fly-to when a location is selected from search
  useEffect(() => {
    if (!mapReady || !map.current || !focusLocation) return
    const { lat, lon } = focusLocation
    if (lat && lon) {
      map.current.flyTo({
        center: [+lon, +lat],
        zoom: 12,
        duration: 1200,
        essential: true,
      })
    }
  }, [mapReady, focusLocation])

  // Initialise map
  useEffect(() => {
    loadMapLibre(() => {
      const ml = window.maplibregl
      if (map.current || !mapContainer.current) return

      map.current = new ml.Map({
        container: mapContainer.current,
        style: {
          version: 8,
          sources: {
            osm: {
              type: 'raster',
              tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
              tileSize: 256,
              attribution: '© OpenStreetMap contributors',
            },
          },
          layers: [{
            id: 'osm-tiles',
            type: 'raster',
            source: 'osm',
            paint: {
              'raster-brightness-min': 0,
              'raster-brightness-max': 0.25,
              'raster-saturation': -0.85,
              'raster-opacity': 0.65,
            },
          }],
        },
        center: MAP_CENTER,
        zoom: MAP_ZOOM,
        attributionControl: false,
      })

      map.current.addControl(new ml.NavigationControl({ showCompass: false }), 'top-right')
      map.current.addControl(new ml.ScaleControl({ unit: 'metric' }), 'bottom-right')
      map.current.on('load', () => setMapReady(true))
    })
  }, [])

  // Add raster overlay sources + layers (risk + confidence) once bounds are known
  useEffect(() => {
    if (!mapReady || !map.current || !rasterBounds) return
    const m = map.current
    const b = rasterBounds
    const coords = [
      [b.west, b.north],
      [b.east, b.north],
      [b.east, b.south],
      [b.west, b.south],
    ]

    if (!m.getSource('risk-raster-src')) {
      m.addSource('risk-raster-src', {
        type: 'image',
        url: `${API_BASE}/risk/raster.png`,
        coordinates: coords,
      })
      m.addLayer({
        id: 'risk-raster-layer',
        type: 'raster',
        source: 'risk-raster-src',
        paint: {
          'raster-opacity': 0.72,
          'raster-fade-duration': 300,
        },
        layout: { visibility: activeLayer === 'risk' ? 'visible' : 'none' },
      })
    }

    if (!m.getSource('conf-raster-src')) {
      m.addSource('conf-raster-src', {
        type: 'image',
        url: `${API_BASE}/risk/raster.png?band=confidence`,
        coordinates: coords,
      })
      m.addLayer({
        id: 'conf-raster-layer',
        type: 'raster',
        source: 'conf-raster-src',
        paint: {
          'raster-opacity': 0.68,
          'raster-fade-duration': 300,
        },
        layout: { visibility: activeLayer === 'confidence' ? 'visible' : 'none' },
      })
    }
  }, [mapReady, rasterBounds])

  // Add risk cells layer
  useEffect(() => {
    if (!mapReady || !map.current || !riskData) return
    const m = map.current

    const geojson = {
      type: 'FeatureCollection',
      features: (riskData.features || []).map(f => ({
        ...f,
        properties: {
          ...f.properties,
          cell_id: f.id ?? f.properties?.cell_id,
        },
      })),
    }

    if (m.getSource('risk-cells')) {
      m.getSource('risk-cells').setData(geojson)
    } else {
      m.addSource('risk-cells', { type: 'geojson', data: geojson })
      m.addLayer({
        id: 'risk-fill',
        type: 'fill',
        source: 'risk-cells',
        filter: ['in', '$type', 'Polygon'],
        paint: {
          'fill-color': [
            'match', ['get', 'risk_tier'],
            'respond', '#e11d48',
            'alert',   '#ea580c',
            'watch',   '#2563eb',
            '#1e293b',
          ],
          'fill-opacity': [
            'match', ['get', 'risk_tier'],
            'respond', 0.65,
            'alert',   0.55,
            'watch',   0.4,
            0.15,
          ],
        },
        layout: { visibility: 'visible' },
      })

      m.addLayer({
        id: 'risk-points',
        type: 'circle',
        source: 'risk-cells',
        filter: ['in', '$type', 'Point'],
        paint: {
          'circle-radius': ['match', ['get', 'risk_tier'], 'respond', 6, 'alert', 5, 'watch', 3.5, 2.5],
          'circle-color': [
            'match', ['get', 'risk_tier'],
            'respond', '#e11d48',
            'alert',   '#ea580c',
            'watch',   '#2563eb',
            '#1e293b',
          ],
          'circle-opacity': 0.8,
          'circle-stroke-width': 1,
          'circle-stroke-color': '#ffffff',
        },
        layout: { visibility: 'visible' },
      })

      const handleCellClick = (e) => {
        const feat = e.features?.[0]
        if (!feat) return
        const p = feat.properties
        setPopup({ lng: e.lngLat.lng, lat: e.lngLat.lat, props: p })
        onCellSelect?.(p.cell_id)
      }

      m.on('click', 'risk-fill', handleCellClick)
      m.on('click', 'risk-points', handleCellClick)
      m.on('mouseenter', 'risk-fill', () => { m.getCanvas().style.cursor = 'pointer' })
      m.on('mouseleave', 'risk-fill', () => { m.getCanvas().style.cursor = '' })
      m.on('mouseenter', 'risk-points', () => { m.getCanvas().style.cursor = 'pointer' })
      m.on('mouseleave', 'risk-points', () => { m.getCanvas().style.cursor = '' })
    }
  }, [mapReady, riskData, onCellSelect])

  // Add field reports layer
  useEffect(() => {
    if (!mapReady || !map.current || !reportsData) return
    const m = map.current

    const geojson = {
      type: 'FeatureCollection',
      features: (reportsData.features || []).filter(f => f.geometry),
    }

    if (m.getSource('reports')) {
      m.getSource('reports').setData(geojson)
    } else {
      m.addSource('reports', { type: 'geojson', data: geojson })
      m.addLayer({
        id: 'reports-circles',
        type: 'circle',
        source: 'reports',
        paint: {
          'circle-radius': 5,
          'circle-color': [
            'interpolate', ['linear'], ['get', 'trust'],
            0, '#475569', 0.5, '#f59e0b', 1, '#10b981',
          ],
          'circle-stroke-width': 1.5,
          'circle-stroke-color': '#080c14',
        },
      })

      m.on('click', 'reports-circles', (e) => {
        const p = e.features?.[0]?.properties
        if (p) setPopup({ lng: e.lngLat.lng, lat: e.lngLat.lat, props: p, popupType: 'report' })
      })
      m.on('mouseenter', 'reports-circles', () => { m.getCanvas().style.cursor = 'pointer' })
      m.on('mouseleave', 'reports-circles', () => { m.getCanvas().style.cursor = '' })
    }
  }, [mapReady, reportsData])

  // Add exposed roads + communities layer
  useEffect(() => {
    if (!mapReady || !map.current) return
    const m = map.current

    fetch(`${API_BASE}/connectivity/exposed?run=latest`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data || !m) return

        // Roads
        if (data.roads?.features?.length > 0) {
          if (m.getSource('exposed-roads')) {
            m.getSource('exposed-roads').setData(data.roads)
          } else {
            m.addSource('exposed-roads', { type: 'geojson', data: data.roads })
            m.addLayer({
              id: 'exposed-roads-line',
              type: 'line',
              source: 'exposed-roads',
              paint: {
                'line-color': [
                  'step', ['coalesce', ['get', 'risk_max'], 0],
                  '#3b82f6', 0.45,
                  '#ea580c', 0.70,
                  '#e11d48',
                ],
                'line-width': [
                  'interpolate', ['linear'], ['zoom'],
                  8, 1.5,
                  12, 3.5,
                  15, 6,
                ],
                'line-opacity': 0.85,
              },
              layout: { visibility: activeLayer === 'roads' ? 'visible' : 'none' },
            })

            m.on('click', 'exposed-roads-line', (e) => {
              const p = e.features?.[0]?.properties
              if (p) setPopup({ lng: e.lngLat.lng, lat: e.lngLat.lat, props: p, popupType: 'road' })
            })
            m.on('mouseenter', 'exposed-roads-line', () => { m.getCanvas().style.cursor = 'pointer' })
            m.on('mouseleave', 'exposed-roads-line', () => { m.getCanvas().style.cursor = '' })
          }
        }

        // Communities
        if (data.communities?.features?.length > 0) {
          if (m.getSource('exposed-communities')) {
            m.getSource('exposed-communities').setData(data.communities)
          } else {
            m.addSource('exposed-communities', { type: 'geojson', data: data.communities })
            m.addLayer({
              id: 'exposed-comm-circle',
              type: 'circle',
              source: 'exposed-communities',
              paint: {
                'circle-radius': [
                  'interpolate', ['linear'], ['zoom'],
                  8, 3.5,
                  12, 6,
                  15, 9,
                ],
                'circle-color': '#f59e0b',
                'circle-stroke-width': 1.5,
                'circle-stroke-color': '#080c14',
                'circle-opacity': 0.9,
              },
              layout: { visibility: activeLayer === 'roads' ? 'visible' : 'none' },
            })

            m.on('click', 'exposed-comm-circle', (e) => {
              const p = e.features?.[0]?.properties
              if (p) setPopup({ lng: e.lngLat.lng, lat: e.lngLat.lat, props: p, popupType: 'community' })
            })
            m.on('mouseenter', 'exposed-comm-circle', () => { m.getCanvas().style.cursor = 'pointer' })
            m.on('mouseleave', 'exposed-comm-circle', () => { m.getCanvas().style.cursor = '' })
          }
        }
      })
      .catch(() => {})
  }, [mapReady])

  // Layer visibility switcher
  useEffect(() => {
    if (!mapReady || !map.current) return
    const m = map.current

    if (m.getLayer('risk-raster-layer')) {
      m.setLayoutProperty('risk-raster-layer', 'visibility', activeLayer === 'risk' ? 'visible' : 'none')
    }
    if (m.getLayer('conf-raster-layer')) {
      m.setLayoutProperty('conf-raster-layer', 'visibility', activeLayer === 'confidence' ? 'visible' : 'none')
    }

    const roadsVis = activeLayer === 'roads' ? 'visible' : 'none'
    if (m.getLayer('exposed-roads-line'))  m.setLayoutProperty('exposed-roads-line',  'visibility', roadsVis)
    if (m.getLayer('exposed-comm-circle')) m.setLayoutProperty('exposed-comm-circle', 'visibility', roadsVis)
  }, [mapReady, activeLayer])

  // Legend items
  const legendItems = activeLayer === 'roads'
    ? [
        { label: 'High risk corridor', color: '#e11d48' },
        { label: 'Alert corridor',     color: '#ea580c' },
        { label: 'Watch corridor',     color: '#2563eb' },
        { label: 'Community node',     color: '#f59e0b' },
      ]
    : activeLayer === 'confidence'
    ? [
        { label: 'High confidence',  color: '#0d9488' },
        { label: 'Medium confidence',color: '#0891b2' },
        { label: 'Low confidence',   color: '#1e3a8a' },
      ]
    : [
        { label: 'High (p ≥ 0.20)',   color: '#e11d48' },
        { label: 'Alert (p ≥ 0.15)',  color: '#ea580c' },
        { label: 'Watch (p ≥ 0.05)',  color: '#2563eb' },
      ]

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      {/* MapLibre DOM Node */}
      <div ref={mapContainer} style={{ width: '100%', height: '100%' }} />

      {/* Restrained Map Control Toolbar (Top Left) */}
      <div className="map-ctrl-bar">
        <button
          className={`map-ctrl-btn ${activeLayer === 'risk' ? 'active' : ''}`}
          onClick={() => onLayerChange('risk')}
          id="layer-btn-risk"
        >
          RISK
        </button>
        <button
          className={`map-ctrl-btn ${activeLayer === 'confidence' ? 'active' : ''}`}
          onClick={() => onLayerChange('confidence')}
          id="layer-btn-confidence"
        >
          CONFIDENCE
        </button>
        <button
          className={`map-ctrl-btn ${activeLayer === 'roads' ? 'active' : ''}`}
          onClick={() => onLayerChange('roads')}
          id="layer-btn-roads"
        >
          ROADS & COMMUNITIES
        </button>
      </div>

      {/* Unobtrusive Map Legend (Bottom Left) */}
      <div className="map-legend-box">
        <div className="map-legend-title">
          {activeLayer === 'roads' ? 'Road Network' : activeLayer === 'confidence' ? 'Confidence' : 'Susceptibility'}
        </div>
        {legendItems.map(({ label, color }) => (
          <div key={label} className="map-legend-row">
            <div style={{ width: 8, height: 8, borderRadius: 1.5, background: color, flexShrink: 0 }} />
            <span>{label}</span>
          </div>
        ))}
      </div>

      {/* Compact Technical Map Popup */}
      {popup && (
        <div style={{
          position: 'absolute',
          bottom: 48,
          right: 14,
          zIndex: 25,
          width: 240,
        }} className="map-popup-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-bright)' }}>
                {popup.popupType === 'road' ? (popup.props.name || 'NH-6 Corridor')
                  : popup.popupType === 'community' ? (popup.props.name || 'Settlement')
                  : popup.popupType === 'report' ? 'Field Observation'
                  : 'Cell Detail'}
              </div>
              <div style={{ fontSize: 8.5, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                {popup.popupType === 'road' ? (popup.props.highway ? `${popup.props.highway} road` : 'Secondary highway')
                  : popup.popupType === 'community' ? (popup.props.place_type || 'Village')
                  : popup.popupType === 'report' ? (popup.props.reporter_type || 'Observer')
                  : `ID: ${popup.props.cell_id ?? '—'}`}
              </div>
            </div>
            <button
              onClick={() => setPopup(null)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 13 }}
            >
              ✕
            </button>
          </div>

          {/* Road popup details */}
          {popup.popupType === 'road' && (
            <div>
              <div className="popup-row">
                <span className="popup-row-lbl">Risk Max</span>
                <span className="popup-row-val" style={{ color: '#e11d48' }}>
                  {(+(popup.props.risk_max || 0)).toFixed(3)}
                </span>
              </div>
              <div className="popup-row">
                <span className="popup-row-lbl">Criticality</span>
                <span className="popup-row-val" style={{ color: '#0891b2' }}>
                  {(+(popup.props.criticality || 0)).toFixed(3)}
                </span>
              </div>
              <div className="popup-row">
                <span className="popup-row-lbl">Length</span>
                <span className="popup-row-val">
                  {popup.props.length ? `${(+popup.props.length).toFixed(0)}m` : '—'}
                </span>
              </div>
              {popup.props.speed_kmh && (
                <div className="popup-row">
                  <span className="popup-row-lbl">Design Speed</span>
                  <span className="popup-row-val">{popup.props.speed_kmh} km/h</span>
                </div>
              )}
            </div>
          )}

          {/* Community popup details */}
          {popup.popupType === 'community' && (
            <div>
              <div className="popup-row">
                <span className="popup-row-lbl">Status</span>
                <span className="popup-row-val" style={{
                  color: popup.props.isolation_flag === 'isolated' ? '#e11d48' : '#10b981',
                }}>
                  {(popup.props.isolation_flag || 'Accessible').toUpperCase()}
                </span>
              </div>
              {popup.props.pop_est && (
                <div className="popup-row">
                  <span className="popup-row-lbl">Population</span>
                  <span className="popup-row-val">{(+popup.props.pop_est).toLocaleString()}</span>
                </div>
              )}
              {popup.props.baseline_tt_min !== undefined && (
                <div className="popup-row">
                  <span className="popup-row-lbl">Hospital Access</span>
                  <span className="popup-row-val">{(+popup.props.baseline_tt_min).toFixed(1)} min</span>
                </div>
              )}
            </div>
          )}

          {/* Default / Cell popup */}
          {(!popup.popupType || popup.popupType === 'report') && (
            <div>
              {popup.props.description && (
                <div style={{ fontSize: 9.5, color: 'var(--text-secondary)', marginBottom: 6, lineHeight: 1.3 }}>
                  {popup.props.description}
                </div>
              )}
              <div className="popup-row">
                <span className="popup-row-lbl">Risk Tier</span>
                <span className="popup-row-val" style={{ textTransform: 'uppercase', color: 'var(--text-bright)' }}>
                  {popup.props.risk_tier || 'None'}
                </span>
              </div>
              {popup.props.p !== undefined && (
                <div className="popup-row">
                  <span className="popup-row-lbl">Probability (p)</span>
                  <span className="popup-row-val">{(+popup.props.p).toFixed(3)}</span>
                </div>
              )}
              {popup.props.confidence !== undefined && (
                <div className="popup-row">
                  <span className="popup-row-lbl">Confidence</span>
                  <span className="popup-row-val">{(+popup.props.confidence).toFixed(3)}</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
