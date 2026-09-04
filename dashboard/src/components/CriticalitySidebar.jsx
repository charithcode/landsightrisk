/**
 * CriticalitySidebar — Ranked Corridors Panel (M6)
 * Shows sorted list of villages/corridors by criticality score.
 * Color-coded by action tier (red/orange/yellow).
 * TODO: Implement ranked list with scroll, click-to-focus-on-map.
 */
import React from "react"

export default function CriticalitySidebar({ data }) {
  return (
    <div className="sidebar-panel criticality-panel">
      <h3>⚠️ Priority Corridors</h3>
      {data.length === 0 ? (
        <p className="placeholder">No data loaded</p>
      ) : (
        data.slice(0, 10).map((item, i) => (
          <div key={item.village_id} className={`corridor-item tier-${item.action_tier}`}>
            <span className="rank">#{i + 1}</span>
            <span className="village-name">{item.village_id}</span>
            <span className="score">{(item.criticality_score * 100).toFixed(0)}</span>
          </div>
        ))
      )}
    </div>
  )
}
