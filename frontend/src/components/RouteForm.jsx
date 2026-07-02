import { useState } from 'react'

export default function RouteForm({ onSubmit, isLoading }) {
  const [start, setStart] = useState('Chicago, IL')
  const [end, setEnd] = useState('Dallas, TX')

  function handleSubmit(event) {
    event.preventDefault()
    onSubmit(start, end)
  }

  return (
    <form className="route-form" onSubmit={handleSubmit}>
      <label className="field">
        <span>Start</span>
        <input
          value={start}
          onChange={(event) => setStart(event.target.value)}
          placeholder="Chicago, IL"
          required
        />
      </label>
      <label className="field">
        <span>End</span>
        <input
          value={end}
          onChange={(event) => setEnd(event.target.value)}
          placeholder="Dallas, TX"
          required
        />
      </label>
      <button type="submit" disabled={isLoading}>
        {isLoading ? 'Planning…' : 'Plan route'}
      </button>
    </form>
  )
}
