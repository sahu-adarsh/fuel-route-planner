import { useMemo } from 'react'
import { MapContainer, TileLayer, Polyline, Marker, Popup } from 'react-leaflet'
import L from 'leaflet'

// Vite doesn't resolve Leaflet's default marker image paths on its own.
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: new URL('leaflet/dist/images/marker-icon-2x.png', import.meta.url).href,
  iconUrl: new URL('leaflet/dist/images/marker-icon.png', import.meta.url).href,
  shadowUrl: new URL('leaflet/dist/images/marker-shadow.png', import.meta.url).href,
})

export default function RouteMap({ geometry, fuelStops }) {
  const positions = useMemo(
    () => geometry.coordinates.map(([lng, lat]) => [lat, lng]),
    [geometry],
  )
  const bounds = useMemo(() => L.latLngBounds(positions), [positions])

  return (
    <MapContainer bounds={bounds} className="route-map" scrollWheelZoom>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Polyline positions={positions} pathOptions={{ color: '#2a78d6', weight: 4 }} />
      {fuelStops.map((stop, index) => (
        <Marker key={`${stop.name}-${stop.cumulative_distance_miles}-${index}`} position={[stop.lat, stop.lng]}>
          <Popup>
            <strong>{stop.name}</strong>
            <br />
            {stop.city}, {stop.state}
            <br />
            ${stop.price_per_gallon.toFixed(2)}/gal &mdash; {stop.gallons_purchased.toFixed(1)} gal
            <br />
            mile {stop.cumulative_distance_miles}
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  )
}
