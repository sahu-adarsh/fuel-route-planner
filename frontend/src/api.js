const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export class ApiError extends Error {
  constructor(message, code, details) {
    super(message)
    this.code = code
    this.details = details
  }
}

export async function planRoute(start, end) {
  const response = await fetch(`${API_BASE_URL}/api/v1/route/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ start, end }),
  })

  const body = await response.json()

  if (!response.ok) {
    const error = body.error || {}
    throw new ApiError(error.message || 'Something went wrong.', error.code, error.details)
  }

  return body
}
