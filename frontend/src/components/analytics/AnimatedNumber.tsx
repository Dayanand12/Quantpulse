import { useEffect, useRef, useState } from "react"

interface AnimatedNumberProps {
  value: number
  format?: (n: number) => string
  durationMs?: number
}

// Eases the displayed value from its previous number to the new one on
// every change, instead of snapping — used by SummaryCard and any table
// cell that wants the same "value ticks up/down" feel.
export function AnimatedNumber({
  value,
  format = (n) => n.toLocaleString("en-IN"),
  durationMs = 500,
}: AnimatedNumberProps) {
  const [display, setDisplay] = useState(value)
  const fromRef = useRef(value)
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    const from = fromRef.current
    const to = value
    if (from === to) return

    const start = performance.now()

    function tick(now: number) {
      const elapsed = now - start
      const t = Math.min(1, elapsed / durationMs)
      const eased = 1 - Math.pow(1 - t, 3) // ease-out cubic
      setDisplay(from + (to - from) * eased)

      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick)
      } else {
        fromRef.current = to
      }
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
  }, [value, durationMs])

  return <span className="tabular-nums">{format(display)}</span>
}
