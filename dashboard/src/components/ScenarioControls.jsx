import React from 'react'

const SCENARIOS = [
  {
    key:   'reset',
    label: 'Baseline',
    desc:  'Restore normal baseline traffic and connectivity conditions',
  },
  {
    key:   'rainfall_replay_june2022',
    label: 'Replay: June 2022',
    desc:  'Extreme monsoon rainfall scenario over NH-6 corridor',
  },
  {
    key:   'nh6_escarpment_block',
    label: 'Simulate: Escarpment Block',
    desc:  'Simulate structural closure of the NH-6 escarpment',
  },
]

export default function ScenarioControls({ onScenario, currentScenario, loading }) {
  const activeKey = currentScenario || 'reset'

  return (
    <div style={{
      position: 'absolute',
      bottom: 12,
      left: '50%',
      transform: 'translateX(-50%)',
      zIndex: 15,
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      background: 'rgba(13, 18, 28, 0.94)',
      border: '1px solid var(--border-medium)',
      borderRadius: 4,
      padding: '3px 8px',
      boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
    }}>
      <span style={{
        fontSize: 8.5,
        fontWeight: 700,
        letterSpacing: '0.08em',
        color: 'var(--text-muted)',
        textTransform: 'uppercase',
        marginRight: 2,
      }}>
        Scenario
      </span>

      {SCENARIOS.map(sc => {
        const isActive = activeKey === sc.key
        return (
          <button
            key={sc.key}
            id={`scenario-btn-${sc.key}`}
            title={sc.desc}
            onClick={() => !loading && onScenario(sc.key)}
            disabled={loading}
            style={{
              fontSize: 10,
              fontWeight: 500,
              padding: '3px 10px',
              borderRadius: 3,
              border: `1px solid ${isActive ? 'var(--border-bright)' : 'transparent'}`,
              background: isActive ? 'var(--bg-active)' : 'transparent',
              color: isActive ? 'var(--text-bright)' : 'var(--text-secondary)',
              cursor: loading ? 'default' : 'pointer',
              transition: 'all 0.15s ease',
              fontFamily: 'var(--font-sans)',
            }}
          >
            {loading && activeKey === sc.key ? 'Processing…' : sc.label}
          </button>
        )
      })}
    </div>
  )
}
