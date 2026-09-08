import React from 'react'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts'

export default function TrajectoryChart({ data }) {
  const series = data?.chart_series ?? []

  // Build chart data from series
  const chartData = series.map((s, i) => ({
    name:           s.label || `T${i}`,
    alert_cells:    s.n_alert_cells || 0,
    respond_cells:  s.n_respond_cells || 0,
    total_critical: (s.n_alert_cells || 0) + (s.n_respond_cells || 0),
  }))

  const displayData = chartData.length > 0 ? chartData : [
    { name: 'T0', total_critical: 12, alert_cells: 8,  respond_cells: 4 },
    { name: 'T1', total_critical: 18, alert_cells: 12, respond_cells: 6 },
    { name: 'T2 (P)', total_critical: 16, alert_cells: 11, respond_cells: 5 },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flexShrink: 0, borderBottom: '1px solid var(--border-subtle)' }}>
      {/* Header */}
      <div className="panel-hdr">
        <span className="panel-hdr-title">Risk Trajectory</span>
        <span className="font-mono" style={{ fontSize: 9, color: 'var(--text-muted)' }}>
          {chartData.length > 0 ? 'LIVE' : 'BASELINE'}
        </span>
      </div>

      <div style={{ padding: '8px 10px 4px' }}>
        <ResponsiveContainer width="100%" height={95}>
          <AreaChart data={displayData} margin={{ top: 4, right: 4, bottom: 0, left: -26 }}>
            <defs>
              <linearGradient id="alertGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#ea580c" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#ea580c" stopOpacity={0.0} />
              </linearGradient>
              <linearGradient id="respondGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#e11d48" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#e11d48" stopOpacity={0.0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#182232" strokeDasharray="1 3" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 8, fill: '#64748b' }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 8, fill: '#64748b' }} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={{
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-medium)',
                borderRadius: 4,
                fontSize: 10,
                color: 'var(--text-bright)',
                padding: '4px 8px',
              }}
              formatter={(val, name) => [val, name === 'alert_cells' ? 'Alert Cells' : 'Respond Cells']}
            />
            <Area
              type="monotone" dataKey="alert_cells"
              stroke="#ea580c" fill="url(#alertGrad)" strokeWidth={1.5}
            />
            <Area
              type="monotone" dataKey="respond_cells"
              stroke="#e11d48" fill="url(#respondGrad)" strokeWidth={1.5}
            />
          </AreaChart>
        </ResponsiveContainer>

        {/* Quiet disclaimer */}
        <div style={{ fontSize: 8.5, color: 'var(--text-muted)', marginTop: 4, fontStyle: 'italic', paddingBottom: 6 }}>
          T2 reflects persistence baseline; not an event timing prediction.
        </div>
      </div>
    </div>
  )
}
