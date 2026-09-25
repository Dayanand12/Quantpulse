import { Suspense, lazy } from "react"
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { Layout } from "./components/Layout"
import { LiveDashboard } from "./pages/LiveDashboard"
import { Positions } from "./pages/Positions"
import { Trades } from "./pages/Trades"
import { Performance } from "./pages/Performance"
import { Screener } from "./pages/Screener"
import { MarketAnalysis } from "./pages/MarketAnalysis"
import { Strategies } from "./pages/Strategies"
import { DeployedStrategies } from "./pages/DeployedStrategies"
import { AvailableStrategies } from "./pages/AvailableStrategies"
import { Backtest } from "./pages/Backtest"
import { BacktestRun } from "./pages/BacktestRun"
import { OptionsBacktest } from "./pages/OptionsBacktest"
import { OptionsBacktestRun } from "./pages/OptionsBacktestRun"
import { Analysis } from "./pages/Analysis"
import { OptionsAnalysis } from "./pages/OptionsAnalysis"
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
          <Route path="strategies" element={<Strategies />}>
            <Route index element={<Navigate to="deployed" replace />} />
            <Route path="deployed" element={<DeployedStrategies />} />
            <Route path="available" element={<AvailableStrategies />} />
          </Route>
          <Route path="backtest" element={<Backtest />}>
            <Route index element={<Navigate to="run" replace />} />
            <Route path="run" element={<BacktestRun />} />
            <Route path="analysis" element={<Analysis />} />
          </Route>
          <Route path="options-backtest" element={<OptionsBacktest />}>
            <Route index element={<Navigate to="run" replace />} />
            <Route path="run" element={<OptionsBacktestRun />} />
            <Route path="analysis" element={<OptionsAnalysis />} />
          </Route>
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
