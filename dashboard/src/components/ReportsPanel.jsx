import React, { useState } from 'react'

const DEMO_REPORT = {
  lon: 91.85, lat: 25.88,
  reporter_type: 'trained_volunteer',
  report_type: 'road_blocked',
  description: 'Debris flow across NH-6 corridor near Byrnihat',
  gps_accuracy_m: 15,
  timestamp_utc: new Date().toISOString(),
}

export default function ReportsPanel({ data, apiBase, onReportSubmit }) {
  const [submitting, setSubmitting] = useState(false)
  const [lastResult, setLastResult] = useState(null)

  const reports = data?.features ?? []

  const handleDemoSubmit = async () => {
    setSubmitting(true)
    try {
      const res = await fetch(`${apiBase}/reports`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(DEMO_REPORT),
      })
      const json = await res.json()
      setLastResult(json)
      onReportSubmit?.(json)
    } catch (e) {
      setLastResult({ error: e.message })
    }
    setSubmitting(false)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'hidden' }}>
      {/* Header */}
      <div className="panel-hdr">
        <span className="panel-hdr-title">Field Reports</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="panel-hdr-count">{reports.length}</span>
          <button
            onClick={handleDemoSubmit}
            disabled={submitting}
            style={{
              background: 'var(--bg-active)',
              border: '1px solid var(--border-bright)',
              borderRadius: 3,
              color: 'var(--text-bright)',
              fontSize: 9,
              fontWeight: 600,
              padding: '2px 6px',
              cursor: 'pointer',
              fontFamily: 'var(--font-sans)',
            }}
          >
            {submitting ? 'Sending…' : '+ Test Report'}
          </button>
        </div>
      </div>

      {/* Confirmation feedback */}
      {lastResult && (
        <div style={{
          padding: '4px 10px',
          fontSize: 9,
          background: lastResult.error ? 'rgba(225, 29, 72, 0.08)' : 'rgba(16, 185, 129, 0.08)',
          borderBottom: `1px solid ${lastResult.error ? 'rgba(225, 29, 72, 0.2)' : 'rgba(16, 185, 129, 0.2)'}`,
          color: lastResult.error ? 'var(--tier-respond)' : 'var(--accent-teal)',
          fontFamily: 'var(--font-mono)',
        }}>
          {lastResult.error
            ? `Error: ${lastResult.error}`
            : `✓ Report accepted · Trust ${lastResult.trust?.toFixed(3)}`}
        </div>
      )}

      {/* Reports feed */}
      <div className="ops-list">
        {reports.length === 0 && (
          <div style={{ padding: '24px 12px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 11 }}>
            No active ground observations logged.
          </div>
        )}

        {reports.map((feat, idx) => {
          const p = feat.properties || {}
          const trust = typeof p.trust === 'number' ? p.trust : 0
          const reportType = (p.report_type || 'observation').replace(/_/g, ' ')
          const reporter = (p.reporter_type || 'observer').replace(/_/g, ' ')

          const trustColor = trust >= 0.7 ? '#10b981' : trust >= 0.4 ? '#f59e0b' : '#64748b'

          return (
            <div
              key={idx}
              style={{
                padding: '8px 12px',
                borderBottom: '1px solid var(--border-subtle)',
                position: 'relative',
              }}
            >
              {/* Type and Trust Score */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 2 }}>
                <span style={{
                  fontSize: 10,
                  fontWeight: 600,
                  textTransform: 'capitalize',
                  color: 'var(--text-bright)',
                }}>
                  {reportType}
                </span>

                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span style={{
                    width: 4,
                    height: 4,
                    borderRadius: '50%',
                    background: trustColor,
                    display: 'inline-block',
                  }} />
                  <span className="font-mono" style={{ fontSize: 9.5, color: trustColor, fontWeight: 600 }}>
                    {trust.toFixed(2)}
                  </span>
                </div>
              </div>

              {/* Description */}
              <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginBottom: 3, lineHeight: 1.3 }}>
                {p.description || 'Ground observation report received.'}
              </div>

              {/* Metadata */}
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 8.5, color: 'var(--text-muted)' }}>
                <span style={{ textTransform: 'capitalize' }}>{reporter}</span>
                {p.gps_accuracy_m && <span>±{p.gps_accuracy_m}m accuracy</span>}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
