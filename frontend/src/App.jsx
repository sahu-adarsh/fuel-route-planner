import { useState } from 'react'
import RouteForm from './components/RouteForm'
import RouteMap from './components/RouteMap'
import { planRoute, ApiError } from './api'
import './App.css'

function StatTile({ label, value }) {
  return (
    <div className="stat-tile">
      <span className="stat-label">{label}</span>
      <strong className="stat-value">{value}</strong>
    </div>
  )
}

function App() {
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [isLoading, setIsLoading] = useState(false)

  async function handleSubmit(start, end) {
    setIsLoading(true)
    setError(null)
    try {
      const data = await planRoute(start, end)
      setResult(data)
    } catch (err) {
      setResult(null)
      setError(err instanceof ApiError ? err.message : 'Could not reach the server.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="app">
      <header>
        <h1>Fuel Route Planner</h1>
        <p>Plan the cheapest fuel stops between two US locations.</p>
      </header>

      <RouteForm onSubmit={handleSubmit} isLoading={isLoading} />

      {error && <p className="error" role="alert">{error}</p>}

      {result && (
        <>
          <div className="stat-tile-row">
            <StatTile label="Distance" value={`${result.distance_miles} mi`} />
            <StatTile label="Duration" value={`${result.duration_hours} hr`} />
            <StatTile label="Fuel stops" value={result.fuel_stops.length} />
            <StatTile label="Total fuel cost" value={`$${result.total_fuel_cost_usd.toFixed(2)}`} />
          </div>

          <RouteMap geometry={result.route_geometry} fuelStops={result.fuel_stops} />
        </>
      )}
    </div>
  )
}

export default App
