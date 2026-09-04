/**
 * ActionPanel — Current Tier Recommendation (M7)
 * Shows the highest-priority active action recommendation
 * with full rationale and recommended action list.
 * TODO: Implement tier badge, expandable action list, rationale text.
 */
import React from "react"

const TIER_COLORS = { 1: "#4ade80", 2: "#fb923c", 3: "#f87171" }
const TIER_LABELS = { 1: "MONITOR", 2: "ADVISORY", 3: "EMERGENCY" }

export default function ActionPanel({ data }) {
  const top = data[0]
  return (
    <div className="sidebar-panel action-panel">
      <h3>🚨 Active Recommendation</h3>
      {!top ? (
        <p className="placeholder">No recommendations yet</p>
      ) : (
        <div className="action-card" style={{ borderColor: TIER_COLORS[top.action_tier] }}>
          <div className="tier-badge" style={{ background: TIER_COLORS[top.action_tier] }}>
            TIER {top.action_tier} — {TIER_LABELS[top.action_tier]}
          </div>
          <p className="rationale">{top.rationale}</p>
          <ul className="action-list">
            {top.recommended_actions.map((action, i) => (
              <li key={i}>{action}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
