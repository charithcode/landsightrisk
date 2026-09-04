/**
 * RiskMap — Main GIS Map Panel
 * Renders risk choropleth + road vulnerability + confidence overlay
 * using Mapbox GL JS via react-map-gl.
 * TODO: Implement map layers, layer toggle controls, popup on click.
 */
import React from "react"

export default function RiskMap({ riskData, confidenceData, activeLayer, onLayerChange }) {
  return (
    <div className="risk-map-placeholder">
      {/* TODO: Replace with <Map> from react-map-gl */}
      <p>🗺️ Risk Map — Mapbox GL JS (react-map-gl)</p>
      <div className="layer-controls">
        {["risk", "confidence", "roads"].map(layer => (
          <button
            key={layer}
            className={activeLayer === layer ? "active" : ""}
            onClick={() => onLayerChange(layer)}
          >
            {layer.charAt(0).toUpperCase() + layer.slice(1)}
          </button>
        ))}
      </div>
    </div>
  )
}
