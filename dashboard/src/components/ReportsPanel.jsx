/**
 * ReportsPanel — Live Field Reports Feed (M8)
 * Shows incoming citizen / Aapda Mitra reports in real time.
 * Trust score displayed as colored badge.
 * TODO: Poll /report endpoint, render trust badges, filter by location.
 */
import React, { useState } from "react"

export default function ReportsPanel() {
  const [reports, setReports] = useState([])
  const [reportText, setReportText] = useState("")

  const handleSubmit = async (e) => {
    e.preventDefault()
    // TODO: POST to /report API endpoint
    console.log("Submitting report:", reportText)
    setReportText("")
  }

  return (
    <div className="right-panel-section reports-panel">
      <h3>📡 Field Reports (M8)</h3>
      <form onSubmit={handleSubmit} className="report-form">
        <input
          value={reportText}
          onChange={e => setReportText(e.target.value)}
          placeholder="Describe the situation..."
        />
        <button type="submit">Submit</button>
      </form>
      <div className="reports-feed">
        {reports.length === 0 ? (
          <p className="placeholder">No reports yet</p>
        ) : (
          reports.map(r => (
            <div key={r.report_id} className="report-item">
              <span className="trust-badge" style={{ opacity: r.trust_score }}>
                Trust: {(r.trust_score * 100).toFixed(0)}%
              </span>
              <p>{r.description}</p>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
