/**
 * Header — LANDSIGHT Top Navigation Bar
 * Shows system name, active district, last pipeline run time, status indicator.
 */
import React from "react"

export default function Header() {
  return (
    <header className="app-header">
      <div className="header-brand">
        <span className="brand-icon">🏔️</span>
        <span className="brand-name">LANDSIGHT</span>
        <span className="brand-tagline">AI-Powered Landslide Connectivity & Response Intelligence</span>
      </div>
      <div className="header-status">
        <span className="status-indicator active"></span>
        <span>System Active</span>
        <span className="district-badge">Kohima District, Nagaland</span>
      </div>
    </header>
  )
}
