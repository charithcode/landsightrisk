/**
 * LANDSIGHT Dashboard — Main Application
 * ========================================
 * GIS Decision-Support Dashboard for Landslide Emergency Management
 *
 * Panels:
 *   - RiskMap         : Choropleth of risk scores (M2) + confidence overlay (M3)
 *   - RoadVulnerability : Road network colored by exposure (M4)
 *   - ConnectivityPanel : Isolated village visualization (M5)
 *   - CriticalitySidebar: Ranked corridors list (M6)
 *   - ActionPanel       : Current tier recommendation + rationale (M7)
 *   - TrajectoryChart   : Time-series risk evolution (M9)
 *   - ReportsPanel      : Live field reports feed (M8)
 *   - ScenarioSimulator : Manually trigger failure scenarios
 */

import React, { useState, useEffect } from 'react'
import RiskMap from './components/RiskMap'
import CriticalitySidebar from './components/CriticalitySidebar'
import ActionPanel from './components/ActionPanel'
import TrajectoryChart from './components/TrajectoryChart'
import ReportsPanel from './components/ReportsPanel'
import Header from './components/Header'
import './App.css'

const API_BASE = 'http://localhost:8000'

export default function App() {
  const [riskData, setRiskData] = useState(null)
  const [confidenceData, setConfidenceData] = useState(null)
  const [criticalityData, setCriticalityData] = useState([])
  const [actionData, setActionData] = useState([])
  const [trajectoryData, setTrajectoryData] = useState([])
  const [activeLayer, setActiveLayer] = useState('risk') // 'risk' | 'confidence' | 'roads'
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // TODO: Fetch all data layers from API
    // Promise.all([
    //   fetch(`${API_BASE}/risk-map`).then(r => r.json()),
    //   fetch(`${API_BASE}/confidence-map`).then(r => r.json()),
    //   fetch(`${API_BASE}/criticality`).then(r => r.json()),
    //   fetch(`${API_BASE}/action-recommendations`).then(r => r.json()),
    //   fetch(`${API_BASE}/risk-trajectory`).then(r => r.json()),
    // ]).then(([risk, conf, crit, actions, traj]) => {
    //   setRiskData(risk)
    //   setConfidenceData(conf)
    //   setCriticalityData(crit)
    //   setActionData(actions)
    //   setTrajectoryData(traj)
    //   setLoading(false)
    // })
    setLoading(false)
  }, [])

  return (
    <div className="app-container">
      <Header />
      <div className="main-layout">
        {/* Left sidebar — criticality + actions */}
        <aside className="sidebar">
          <CriticalitySidebar data={criticalityData} />
          <ActionPanel data={actionData} />
        </aside>

        {/* Center — main map */}
        <main className="map-container">
          <RiskMap
            riskData={riskData}
            confidenceData={confidenceData}
            activeLayer={activeLayer}
            onLayerChange={setActiveLayer}
          />
        </main>

        {/* Right panel — trajectory + reports */}
        <aside className="right-panel">
          <TrajectoryChart data={trajectoryData} />
          <ReportsPanel />
        </aside>
      </div>
    </div>
  )
}
