// Base URL the backend API/WebSocket are reached at.
//
// Empty by default — every fetch/WebSocket call stays same-origin
// relative, exactly as before this existed (works via Vite's dev proxy
// in development, or a reverse proxy / single process serving frontend +
// backend from one origin in production — no env var needed for either).
//
// Set VITE_API_BASE_URL at build time (e.g. "https://api.example.com")
// only if frontend and backend are deployed to two different origins —
// the one knob that needs turning for that deployment shape, instead of
// requiring a reverse proxy just to keep same-origin-relative paths working.
export const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? ""

export function wsBase(): string {
  if (!API_BASE) {
    const proto = window.location.protocol === "https:" ? "wss" : "ws"
    return `${proto}://${window.location.host}`
  }
  return API_BASE.replace(/^http/, "ws")
}
