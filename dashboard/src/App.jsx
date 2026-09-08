/**
 * LANDSIGHT Dashboard — Main Application
 * ========================================
 * Professional Cartographic Operations Center
 * Guwahati–Shillong NH-6 Landslide Connectivity Intelligence
 */

import React, { useState, useEffect, useCallback } from 'react'
import Header from './components/Header'
import StatusBar from './components/StatusBar'
import RiskMap from './components/RiskMap'
import CriticalitySidebar from './components/CriticalitySidebar'
import ActionPanel from './components/ActionPanel'
import TrajectoryChart from './components/TrajectoryChart'
import ReportsPanel from './components/ReportsPanel'
import ScenarioControls from './components/ScenarioControls'
import './index.css'

const API_BASE = 'http://localhost:8000'

export default function App() {
  // ── Core data state ───────────────────────────────────────────
  const [riskData,        setRiskData]        = useState(null)
  const [criticalityData, setCriticalityData] = useState([])
  const [actionData,      setActionData]      = useState([])
  const [trajectoryData,  setTrajectoryData]  = useState(null)
  const [reportsData,     setReportsData]     = useState(null)
  const [healthData,      setHealthData]      = useState(null)
  const [impactData,      setImpactData]      = useState(null)
  const [exposedData,     setExposedData]     = useState(null)

  // ── UI state ──────────────────────────────────────────────────
  const [activeLayer,     setActiveLayer]     = useState('risk')   // 'risk'|'confidence'|'roads'
  const [selectedCell,    setSelectedCell]    = useState(null)
  const [scenarioMode,    setScenarioMode]    = useState('reset')
  const [scenarioLoading, setScenarioLoading] = useState(false)
  const [loading,         setLoading]         = useState(true)
  const [errors,          setErrors]          = useState({})
  const [focusLocation,   setFocusLocation]   = useState(null)

  // ── Fetch helpers ─────────────────────────────────────────────
  const safeFetch = useCallback(async (url, key) => {
    try {
      const res = await fetch(url)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return await res.json()
    } catch (e) {
      setErrors(prev => ({ ...prev, [key]: e.message }))
      return null
    }
  }, [])

  // ── Initial data load ─────────────────────────────────────────
  useEffect(() => {
    const loadAll = async () => {
      setLoading(true)
      const [health, risk, crit, act, traj, rpts, exposed] = await Promise.all([
        safeFetch(`${API_BASE}/health`,                           'health'),
        safeFetch(`${API_BASE}/risk/map?run=latest`,              'risk'),
        safeFetch(`${API_BASE}/criticality?run=latest`,           'criticality'),
        safeFetch(`${API_BASE}/actions?run=latest`,               'actions'),
        safeFetch(`${API_BASE}/trajectory`,                       'trajectory'),
        safeFetch(`${API_BASE}/reports`,                          'reports'),
        safeFetch(`${API_BASE}/connectivity/exposed?run=latest`,  'exposed'),
      ])

      setHealthData(health)
      if (risk)  setRiskData(risk)
      if (crit)  setCriticalityData(crit?.features ?? [])
      if (act)   setActionData(act?.actions ?? [])
      if (traj)  setTrajectoryData(traj)
      if (rpts)    setReportsData(rpts)
      if (exposed) setExposedData(exposed)
      setLoading(false)
    }

    loadAll()
    // Refresh health + reports every 60s
    const timer = setInterval(() => {
      safeFetch(`${API_BASE}/health`, 'health').then(h => h && setHealthData(h))
      safeFetch(`${API_BASE}/reports`, 'reports').then(r => r && setReportsData(r))
    }, 60_000)
    return () => clearInterval(timer)
  }, [safeFetch])

  // ── Scenario handler ──────────────────────────────────────────
  const runScenario = useCallback(async (scenario) => {
    setScenarioMode(scenario)
    if (scenario === 'reset') {
      setImpactData(null)
      return
    }
    setScenarioLoading(true)
    const data = await safeFetch(
      `${API_BASE}/connectivity/impact?scenario=${scenario}&run=latest`,
      'scenario'
    )
    setImpactData(data)
    setScenarioLoading(false)
  }, [safeFetch])

  return (
    <div className="app-container">
      {/* 1. Header with Integrated GIS Location Selector & Live Telemetry */}
      <Header
        health={healthData}
        onLocationSelect={setFocusLocation}
        currentSelected={focusLocation}
      />

      {/* 2. Quiet Scientific Advisory Line */}
      <StatusBar health={healthData} errors={errors} />

      {/* 3. Main Workspace: Dominant Map flanked by Compact Left & Right Panels */}
      <div className="main-layout">
        {/* Left operations panel: Critical Segments + Action Recommendations */}
        <aside className="sidebar">
          <div style={{ flex: 1.1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <CriticalitySidebar
              data={criticalityData}
              impactData={impactData}
            />
          </div>
          <div style={{ flex: 0.9, minHeight: 0, display: 'flex', flexDirection: 'column', borderTop: '1px solid var(--border-subtle)' }}>
            <ActionPanel
              data={actionData}
              loading={loading}
            />
          </div>
        </aside>

        {/* Center: Dominant Map Canvas (~75% Visual Weight) */}
        <main className="map-container">
          <RiskMap
            riskData={riskData}
            reportsData={reportsData}
            impactData={impactData}
            exposedData={exposedData}
            activeLayer={activeLayer}
            onLayerChange={setActiveLayer}
            onCellSelect={setSelectedCell}
            selectedCell={selectedCell}
            focusLocation={focusLocation}
          />
          <ScenarioControls
            onScenario={runScenario}
            currentScenario={scenarioMode}
            loading={scenarioLoading}
          />
        </main>

        {/* Right operations panel: Risk Trajectory + Field Reports */}
        <aside className="right-panel">
          <TrajectoryChart data={trajectoryData} />
          <ReportsPanel
            data={reportsData}
            apiBase={API_BASE}
            onReportSubmit={async () => {
              safeFetch(`${API_BASE}/reports`, 'reports').then(r => r && setReportsData(r))
            }}
          />
        </aside>
      </div>
    </div>
  )
}
