import React from 'react'
import LocationControl from './LocationControl'

export default function Header({ health, onLocationSelect, currentSelected }) {
  const isSynthetic = health?.is_synthetic !== false
  const runId = health?.latest_run_id
  const hasRun = runId && runId !== 'none'

  // Extract date / time from run ID (run_YYYYMMDDTHHMMSSZ)
  let lastUpdateStr = '—'
  let dataAgeStr = ''
  if (hasRun) {
    const tsMatch = runId.match(/run_(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z/)
    if (tsMatch) {
      const [, y, mo, d, h, mi] = tsMatch
      lastUpdateStr = `${y}-${mo}-${d} ${h}:${mi} UTC`
      const runDate = new Date(`${y}-${mo}-${d}T${h}:${mi}:00Z`)
      const mins = Math.round((Date.now() - runDate.getTime()) / 60000)
      if (mins > 0) {
        dataAgeStr = mins > 1440 ? `${Math.round(mins / 1440)}d ago` : mins > 60 ? `${Math.round(mins / 60)}h ago` : `${mins}m ago`
      }
    }
  }

  // Monitoring status
  const statusKey = health?.monitoring_status || (hasRun ? 'SOURCE_UNAVAILABLE' : 'NO_DATA')
  const statusLabels = {
    CURRENT: 'Monitoring: Current',
    DATA_AGING: 'Monitoring: Data aging',
    SOURCE_UNAVAILABLE: 'Monitoring: Ready (awaiting feed)',
    UPDATE_FAILED: 'Monitoring: Update failed',
    NO_DATA: 'Monitoring: No data',
  }
  const statusColors = {
    CURRENT: '#10b981',
    DATA_AGING: '#f59e0b',
    SOURCE_UNAVAILABLE: '#64748b',
    UPDATE_FAILED: '#ef4444',
    NO_DATA: '#64748b',
  }
  const statusText = statusLabels[statusKey] || statusLabels.SOURCE_UNAVAILABLE
  const dotColor = statusColors[statusKey] || '#64748b'

  return (
    <header style={{
      height: 'var(--header-h)',
      background: 'var(--bg-base)',
      borderBottom: '1px solid var(--border-subtle)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 16px',
      flexShrink: 0,
      zIndex: 20,
    }}>
      {/* Left: Product title */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{
          width: 24,
          height: 24,
          background: 'var(--bg-surface-2)',
          border: '1px solid var(--border-medium)',
          borderRadius: 3,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'var(--font-mono)',
          fontWeight: 700,
          fontSize: 11,
          color: 'var(--text-bright)',
        }}>
          LS
        </div>
        <div>
          <div style={{
            fontSize: 13,
            fontWeight: 700,
            letterSpacing: '0.02em',
            color: 'var(--text-bright)',
            lineHeight: 1.1,
          }}>
            LANDSIGHT
          </div>
          <div style={{
            fontSize: 8.5,
            color: 'var(--text-muted)',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}>
            NH-6 Corridor · Connectivity Intelligence
          </div>
        </div>
      </div>

      {/* Center: Location selector & search */}
      <LocationControl
        onLocationSelect={onLocationSelect}
        currentSelected={currentSelected}
      />

      {/* Right: Operational telemetry */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, fontSize: 10 }}>
        {/* Monitoring status dot */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{
            width: 5,
            height: 5,
            borderRadius: '50%',
            background: dotColor,
            display: 'inline-block',
          }} />
          <span style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>
            {statusText}
          </span>
        </div>

        <span style={{ color: 'var(--border-medium)' }}>|</span>

        {/* Last update */}
        <div style={{ color: 'var(--text-muted)' }}>
          Updated: <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>{lastUpdateStr}</span>
          {dataAgeStr && <span style={{ marginLeft: 4, color: 'var(--text-muted)' }}>({dataAgeStr})</span>}
        </div>

        <span style={{ color: 'var(--border-medium)' }}>|</span>

        {/* Run */}
        <div style={{ color: 'var(--text-muted)' }}>
          Run: <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>
            {hasRun ? runId.replace('run_', '') : '—'}
          </span>
        </div>

        {/* Synthetic caution if applicable */}
        {isSynthetic && (
          <span style={{
            fontSize: 9,
            fontFamily: 'var(--font-mono)',
            fontWeight: 600,
            color: '#d97706',
            background: 'rgba(217, 119, 6, 0.08)',
            border: '1px solid rgba(217, 119, 6, 0.25)',
            padding: '1px 5px',
            borderRadius: 2,
          }}>
            SYNTHETIC
          </span>
        )}
      </div>
    </header>
  )
}
