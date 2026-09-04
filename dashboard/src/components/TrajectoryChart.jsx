/**
 * TrajectoryChart — Risk Evolution Time Series (M9)
 * Plots risk score and confidence over pipeline run history.
 * Uses Recharts LineChart.
 * TODO: Add auto-refresh every N minutes, escalation annotations.
 */
import React from "react"
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts"

export default function TrajectoryChart({ data }) {
  return (
    <div className="right-panel-section trajectory-chart">
      <h3>📈 Risk Trajectory (Last 48h)</h3>
      {data.length === 0 ? (
        <p className="placeholder">No trajectory data yet</p>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
            <XAxis dataKey="run_timestamp" tick={{ fontSize: 10 }} />
            <YAxis domain={[0, 1]} tick={{ fontSize: 10 }} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="max_risk_score" stroke="#f87171" name="Max Risk" dot={false} />
            <Line type="monotone" dataKey="mean_confidence" stroke="#60a5fa" name="Avg Confidence" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
