import { useState } from 'react'

function toLocationValue(field) {
  if (field.mode === 'coords') {
    return { lat: Number(field.lat), lng: Number(field.lng) }
  }
  return field.place.trim()
}

function LocationInput({ label, placeholder, value, onChange }) {
  function update(patch) {
    onChange({ ...value, ...patch })
  }

  return (
    <div className="field">
      <div className="field-header">
        <span>{label}</span>
        <div className="mode-toggle" role="tablist" aria-label={`${label} input mode`}>
          <button
            type="button"
            role="tab"
            aria-selected={value.mode === 'place'}
            className={value.mode === 'place' ? 'active' : ''}
            onClick={() => update({ mode: 'place' })}
          >
            Place
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={value.mode === 'coords'}
            className={value.mode === 'coords' ? 'active' : ''}
            onClick={() => update({ mode: 'coords' })}
          >
            Coordinates
          </button>
        </div>
      </div>

      {value.mode === 'place' ? (
        <input
          value={value.place}
          onChange={(event) => update({ place: event.target.value })}
          placeholder={placeholder}
          required
        />
      ) : (
        <div className="coord-inputs">
          <input
            type="number"
            inputMode="decimal"
            step="any"
            min={-90}
            max={90}
            value={value.lat}
            onChange={(event) => update({ lat: event.target.value })}
            placeholder="Latitude"
            aria-label={`${label} latitude`}
            required
          />
          <input
            type="number"
            inputMode="decimal"
            step="any"
            min={-180}
            max={180}
            value={value.lng}
            onChange={(event) => update({ lng: event.target.value })}
            placeholder="Longitude"
            aria-label={`${label} longitude`}
            required
          />
        </div>
      )}
    </div>
  )
}

export default function RouteForm({ onSubmit, isLoading }) {
  const [start, setStart] = useState({ mode: 'place', place: 'Chicago, IL', lat: '', lng: '' })
  const [end, setEnd] = useState({ mode: 'place', place: 'Dallas, TX', lat: '', lng: '' })

  function handleSubmit(event) {
    event.preventDefault()
    onSubmit(toLocationValue(start), toLocationValue(end))
  }

  return (
    <form className="route-form" onSubmit={handleSubmit}>
      <LocationInput label="Start" placeholder="Chicago, IL" value={start} onChange={setStart} />
      <LocationInput label="End" placeholder="Dallas, TX" value={end} onChange={setEnd} />
      <button type="submit" disabled={isLoading}>
        {isLoading ? 'Planning…' : 'Plan route'}
      </button>
    </form>
  )
}
