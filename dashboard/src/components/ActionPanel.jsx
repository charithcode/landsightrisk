import React, { useState } from 'react'

const TIER_ORDER = ['verify', 'ready', 'respond', 'monitor', 'none']

export default function ActionPanel({ data = [], loading }) {
  const [selectedTier, setSelectedTier] = useState('all')
  const [activeActionId, setActiveActionId] = useState(null)

  // Count actions by tier
  const counts = {
    verify:  data.filter(a => a.tier === 'verify' || a.tier === 'alert').length,
    ready:   data.filter(a => a.tier === 'ready').length,
    respond: data.filter(a => a.tier === 'respond').length,
    monitor: data.filter(a => a.tier === 'monitor' || a.tier === 'watch').length,
  }

  // Filter actions
  const filtered = data.filter(a => {
    if (selectedTier === 'all') return true
    if (selectedTier === 'verify') return a.tier === 'verify' || a.tier === 'alert'
    if (selectedTier === 'ready') return a.tier === 'ready'
    if (selectedTier === 'respond') return a.tier === 'respond'
    if (selectedTier === 'monitor') return a.tier === 'monitor' || a.tier === 'watch'
    return true
  }).slice(0, 8)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'hidden' }}>
      {/* Header */}
      <div className="panel-hdr">
        <span className="panel-hdr-title">Action Recommendations</span>
        <span className="panel-hdr-count">{data.length}</span>
      </div>

      {/* Queue Filter Bar */}
      <div style={{
        display: 'flex',
        borderBottom: '1px solid var(--border-subtle)',
        background: 'var(--bg-surface)',
        padding: '4px 8px',
        gap: 4,
        flexShrink: 0,
      }}>
        <button
          onClick={() => setSelectedTier('all')}
          style={{
            flex: 1,
            background: selectedTier === 'all' ? 'var(--bg-active)' : 'transparent',
            border: `1px solid ${selectedTier === 'all' ? 'var(--border-bright)' : 'transparent'}`,
            borderRadius: 3,
            padding: '3px 0',
            fontSize: 9,
            fontWeight: 600,
            color: selectedTier === 'all' ? 'var(--text-bright)' : 'var(--text-muted)',
            cursor: 'pointer',
            fontFamily: 'var(--font-sans)',
          }}
        >
          ALL {data.length}
        </button>

        <button
          onClick={() => setSelectedTier('verify')}
          style={{
            flex: 1.2,
            background: selectedTier === 'verify' ? 'rgba(234, 88, 12, 0.12)' : 'transparent',
            border: `1px solid ${selectedTier === 'verify' ? '#ea580c' : 'transparent'}`,
            borderRadius: 3,
            padding: '3px 0',
            fontSize: 9,
            fontWeight: 600,
            color: selectedTier === 'verify' ? '#ea580c' : 'var(--text-muted)',
            cursor: 'pointer',
            fontFamily: 'var(--font-sans)',
          }}
        >
          VERIFY {counts.verify}
        </button>

        <button
          onClick={() => setSelectedTier('ready')}
          style={{
            flex: 1.2,
            background: selectedTier === 'ready' ? 'rgba(217, 119, 6, 0.12)' : 'transparent',
            border: `1px solid ${selectedTier === 'ready' ? '#d97706' : 'transparent'}`,
            borderRadius: 3,
            padding: '3px 0',
            fontSize: 9,
            fontWeight: 600,
            color: selectedTier === 'ready' ? '#d97706' : 'var(--text-muted)',
            cursor: 'pointer',
            fontFamily: 'var(--font-sans)',
          }}
        >
          READY {counts.ready}
        </button>

        <button
          onClick={() => setSelectedTier('monitor')}
          style={{
            flex: 1.2,
            background: selectedTier === 'monitor' ? 'rgba(37, 99, 235, 0.12)' : 'transparent',
            border: `1px solid ${selectedTier === 'monitor' ? '#2563eb' : 'transparent'}`,
            borderRadius: 3,
            padding: '3px 0',
            fontSize: 9,
            fontWeight: 600,
            color: selectedTier === 'monitor' ? '#2563eb' : 'var(--text-muted)',
            cursor: 'pointer',
            fontFamily: 'var(--font-sans)',
          }}
        >
          MONITOR {counts.monitor}
        </button>
      </div>

      {/* Operations List */}
      <div className="ops-list">
        {filtered.length === 0 && (
          <div style={{ padding: '24px 12px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 11 }}>
            No recommendations in queue.
          </div>
        )}

        {filtered.map((action, idx) => {
          const isSelected = activeActionId === idx
          const tier = action.tier || 'none'
          const ev = action.evidence || {}
          const axes = ev.confidence_axes || {}

          const pVal = axes.p ?? ev.risk_p ?? 0
          const confVal = axes.confidence ?? ev.confidence ?? 0
          const critVal = ev.criticality ?? 0

          const tierTheme = {
            respond: { color: '#e11d48', bg: 'rgba(225, 29, 72, 0.1)' },
            verify:  { color: '#ea580c', bg: 'rgba(234, 88, 12, 0.1)' },
            ready:   { color: '#d97706', bg: 'rgba(217, 119, 6, 0.1)' },
            monitor: { color: '#2563eb', bg: 'rgba(37, 99, 235, 0.1)' },
            none:    { color: '#64748b', bg: 'rgba(100, 116, 139, 0.1)' },
          }[tier] || { color: '#64748b', bg: 'rgba(100, 116, 139, 0.1)' }

          return (
            <div
              key={idx}
              className={`ops-item ${isSelected ? 'active' : ''}`}
              onClick={() => setActiveActionId(isSelected ? null : idx)}
            >
              {/* Row Header */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 3 }}>
                <span style={{
                  fontSize: 9,
                  fontFamily: 'var(--font-mono)',
                  fontWeight: 700,
                  letterSpacing: '0.04em',
                  color: tierTheme.color,
                  background: tierTheme.bg,
                  padding: '1px 5px',
                  borderRadius: 2,
                }}>
                  {tier.toUpperCase()}
                </span>

                <span style={{ fontSize: 9.5, color: 'var(--text-muted)' }}>
                  {ev.road_seg_ids?.length ?? 1} segment · {ev.cell_ids?.length ?? 0} cells
                </span>
              </div>

              {/* Title / Description */}
              <div style={{ fontSize: 10.5, fontWeight: 500, color: 'var(--text-bright)', marginBottom: 4, lineHeight: 1.3 }}>
                {action.rationale || 'Corridor risk advisory'}
              </div>

              {/* Metrics row */}
              <div className="font-mono" style={{ display: 'flex', gap: 12, fontSize: 9.5, color: 'var(--text-secondary)' }}>
                <span>Risk: <strong style={{ color: 'var(--text-bright)' }}>{(+pVal).toFixed(2)}</strong></span>
                <span>Conf: <strong style={{ color: 'var(--text-bright)' }}>{(+confVal).toFixed(2)}</strong></span>
                {critVal > 0 && <span>Crit: <strong style={{ color: 'var(--text-bright)' }}>{(+critVal).toFixed(2)}</strong></span>}
              </div>

              {/* Expandable operational details */}
              {isSelected && (
                <div style={{
                  marginTop: 8,
                  paddingTop: 8,
                  borderTop: '1px solid var(--border-subtle)',
                  fontSize: 10,
                }}>
                  <div style={{ marginBottom: 6 }}>
                    <div style={{ fontSize: 8.5, fontWeight: 700, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 2 }}>
                      Recommended Procedure
                    </div>
                    <div style={{ color: 'var(--text-primary)', lineHeight: 1.4 }}>
                      {action.action || 'Dispatch reconnaissance vehicle to inspect roadway drainage and slope stability.'}
                    </div>
                  </div>

                  {/* Evidence Chain */}
                  {ev.driving_factors?.length > 0 && (
                    <div style={{ marginBottom: 6 }}>
                      <div style={{ fontSize: 8.5, fontWeight: 700, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 3 }}>
                        Evidence Chain
                      </div>
                      {ev.driving_factors.map((f, fi) => (
                        <div key={fi} style={{
                          fontSize: 9.5,
                          color: 'var(--text-secondary)',
                          paddingLeft: 6,
                          borderLeft: '2px solid var(--border-bright)',
                          marginBottom: 3,
                          lineHeight: 1.3,
                        }}>
                          {f}
                        </div>
                      ))}
                    </div>
                  )}

                  <div style={{
                    fontSize: 8.5,
                    color: 'var(--text-muted)',
                    fontStyle: 'italic',
                    marginTop: 4,
                  }}>
                    Human authorization required before field execution.
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
