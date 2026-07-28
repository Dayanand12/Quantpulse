import { Suspense, lazy } from "react"
import { BrowserRouter, Route, Routes } from "react-router-dom"
import { Layout } from "./components/Layout"
import { LiveDashboard } from "./pages/LiveDashboard"
import { Positions } from "./pages/Positions"
import { Trades } from "./pages/Trades"
import { Performance } from "./pages/Performance"
import { Screener } from "./pages/Screener"
import { MarketAnalysis } from "./pages/MarketAnalysis"
import { Strategies } from "./pages/Strategies"
import { Settings } from "./pages/Settings"

// CodeMirror pulls in a meaningful bundle (~470kB) that only the Strategy
// Builder page needs — code-split it so every other page's initial load
// stays light.
const StrategyBuilder = lazy(() =>
  import("./pages/StrategyBuilder").then((m) => ({ default: m.StrategyBuilder })),
)

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<LiveDashboard />} />
          <Route path="positions" element={<Positions />} />
          <Route path="trades" element={<Trades />} />
          <Route path="performance" element={<Performance />} />
          <Route path="screener" element={<Screener />} />
          <Route path="market-analysis" element={<MarketAnalysis />} />
          <Route path="strategies" element={<Strategies />} />
          <Route
            path="strategy-builder"
            element={
              <Suspense
                fallback={<p className="text-sm text-[var(--ink-muted)]">Loading…</p>}
              >
                <StrategyBuilder />
              </Suspense>
            }
          />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
