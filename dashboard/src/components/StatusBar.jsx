import React from 'react'

export default function StatusBar({ health, errors = {} }) {
  const hasErrors = Object.keys(errors).filter(k => errors[k]).length > 0
  const isSynthetic = health?.is_synthetic !== false

  return (
    <div style={{
      height: 'var(--subbar-h)',
      background: 'var(--bg-deep)',
      borderBottom: '1px solid var(--border-subtle)',
      padding: '0 16px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      fontSize: 9.5,
      color: 'var(--text-muted)',
      flexShrink: 0,
      userSelect: 'none',
    }}>
      {/* Left: Scientific advisory */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ color: 'var(--text-dim)' }}>Notice:</span>
        <span style={{ color: 'var(--text-secondary)' }}>
          Model estimates rainfall-conditioned susceptibility. Event timing and individual release not predicted. All actions require human authorisation.
        </span>
      </div>

      {/* Right: Data Quality & API diagnostics */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div>
          Data Quality: <span className="font-mono" style={{ color: isSynthetic ? '#d97706' : 'var(--accent-teal)' }}>
            {isSynthetic ? '0.00 (synthetic calibration)' : '0.80 (IMD observations)'}
          </span>
        </div>

        {hasErrors && (
          <div style={{ color: 'var(--tier-respond)', fontWeight: 600 }}>
            API error: {Object.entries(errors).filter(([,v]) => v).map(([k]) => k).join(', ')}
          </div>
        )}
      </div>
    </div>
  )
}
