import React, { useState } from 'react'

const COMPONENT_KEYS = [
  { key: 'RISK',    label: 'Risk',     color: '#e11d48', desc: 'Highest calibrated p in 50m buffer' },
  { key: 'SERVED',  label: 'Served',   color: '#0891b2', desc: 'Normalized villages using this segment' },
  { key: 'DETOUR',  label: 'Detour',   color: '#ea580c', desc: 'Detour penalty (no parallel corridors)' },
  { key: 'HOSPDEP', label: 'Hospital', color: '#0d9488', desc: 'Sole hospital route dependency' },
]

export default function CriticalitySidebar({ data = [], impactData, onSegmentClick }) {
  const [expandedId, setExpandedId] = useState(null)

  const segments = data
    .filter(f => f?.properties)
    .map(f => f.properties)
    .sort((a, b) => (b.criticality || 0) - (a.criticality || 0))
    .slice(0, 10)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header */}
      <div className="panel-hdr">
        <span className="panel-hdr-title">Critical Segments</span>
        <span className="panel-hdr-count">{segments.length}</span>
      </div>

      {/* Scenario impact callout if active */}
      {impactData && (
        <div style={{
          padding: '6px 12px',
          background: 'rgba(225, 29, 72, 0.06)',
          borderBottom: '1px solid rgba(225, 29, 72, 0.2)',
          fontSize: 10,
        }}>
          <div style={{ fontWeight: 600, color: 'var(--tier-respond)', marginBottom: 2 }}>
            Scenario Impact Active
          </div>
          <div className="font-mono" style={{ color: 'var(--text-secondary)', display: 'flex', gap: 10 }}>
            <span>Isolated: {impactData.n_villages_isolated ?? 0}</span>
            <span>Poor: {impactData.n_poorly_connected ?? 0}</span>
            <span>Delay: +{impactData.avg_travel_increase_min?.toFixed(0) ?? 0}m</span>
          </div>
        </div>
      )}

      {/* List */}
      <div className="ops-list">
        {segments.length === 0 && (
          <div style={{ padding: '24px 12px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 11 }}>
            No critical segments loaded.
          </div>
        )}

        {segments.map((seg, idx) => {
          const isExpanded = expandedId === idx
          const rank = String(idx + 1).padStart(2, '0')
          const roadName = seg.name || 'NH-6'
          const roadType = seg.highway ? seg.highway.charAt(0).toUpperCase() + seg.highway.slice(1) : 'Road'
          const crit = typeof seg.criticality === 'number' ? seg.criticality : 0
          const comps = seg.components || {}

          // Component values
          const riskVal = comps.risk ?? seg.risk_max ?? 0
          const servedVal = comps.served ?? 0
          const detourVal = comps.detour ?? 0
          const hospVal = comps.hospdep ?? 0

          return (
            <div
              key={idx}
              className={`ops-item ${isExpanded ? 'active' : ''}`}
              onClick={() => {
                setExpandedId(isExpanded ? null : idx)
                onSegmentClick?.(seg)
              }}
            >
              {/* Primary row: Rank + Road Name + Type + Criticality */}
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 4 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                  <span className="font-mono" style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 600 }}>
                    {rank}
                  </span>
                  <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-bright)' }}>
                    {roadName}
                  </span>
                  <span style={{ fontSize: 9.5, color: 'var(--text-muted)' }}>
                    {roadType}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                  <span className="font-mono" style={{
                    fontSize: 11,
                    fontWeight: 600,
                    color: crit >= 0.6 ? '#f43f5e' : crit >= 0.5 ? '#f59e0b' : 'var(--text-secondary)',
                  }}>
                    {crit.toFixed(3)}
                  </span>
                </div>
              </div>

              {/* 4 Mini Component Progress Bars */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 4 }}>
                <div className="mini-bar-row">
                  <span className="mini-bar-lbl">Risk</span>
                  <div className="mini-bar-track">
                    <div className="mini-bar-fill" style={{ width: `${Math.min(100, Math.round(riskVal * 100))}%`, background: '#e11d48' }} />
                  </div>
                  <span className="mini-bar-val">{riskVal.toFixed(2)}</span>
                </div>

                <div className="mini-bar-row">
                  <span className="mini-bar-lbl">Served</span>
                  <div className="mini-bar-track">
                    <div className="mini-bar-fill" style={{ width: `${Math.min(100, Math.round(servedVal * 100))}%`, background: '#0891b2' }} />
                  </div>
                  <span className="mini-bar-val">{servedVal.toFixed(2)}</span>
                </div>

                <div className="mini-bar-row">
                  <span className="mini-bar-lbl">Detour</span>
                  <div className="mini-bar-track">
                    <div className="mini-bar-fill" style={{ width: `${Math.min(100, Math.round(detourVal * 100))}%`, background: '#ea580c' }} />
                  </div>
                  <span className="mini-bar-val">{detourVal.toFixed(2)}</span>
                </div>

                <div className="mini-bar-row">
                  <span className="mini-bar-lbl">Hospital</span>
                  <div className="mini-bar-track">
                    <div className="mini-bar-fill" style={{ width: `${Math.min(100, Math.round(hospVal * 100))}%`, background: '#0d9488' }} />
                  </div>
                  <span className="mini-bar-val">{hospVal.toFixed(2)}</span>
                </div>
              </div>

              {/* Expanded detail section */}
              {isExpanded && (
                <div style={{
                  marginTop: 8,
                  paddingTop: 8,
                  borderTop: '1px solid var(--border-subtle)',
                  fontSize: 10,
                  color: 'var(--text-secondary)',
                }}>
                  <div className="popup-row">
                    <span className="popup-row-lbl">Segment ID</span>
                    <span className="popup-row-val">{seg.seg_id ?? '—'}</span>
                  </div>
                  <div className="popup-row">
                    <span className="popup-row-lbl">OSM Ref</span>
                    <span className="popup-row-val">{seg.osm_id ?? '—'}</span>
                  </div>
                  <div className="popup-row">
                    <span className="popup-row-lbl">Length</span>
                    <span className="popup-row-val">
                      {seg.length ? `${(+seg.length).toFixed(0)} m` : '—'}
                    </span>
                  </div>
                  <div className="popup-row">
                    <span className="popup-row-lbl">Speed Est</span>
                    <span className="popup-row-val">
                      {seg.speed_kmh ? `${seg.speed_kmh} km/h` : '—'}
                    </span>
                  </div>
                  <div className="popup-row">
                    <span className="popup-row-lbl">Confidence</span>
                    <span className="popup-row-val">
                      {seg.conf_min !== undefined ? (+seg.conf_min).toFixed(3) : '—'}
                    </span>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
