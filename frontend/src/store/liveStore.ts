import { create } from "zustand"
import type {
  BrokerStatus,
  LivePayload,
  MarketTicker,
  PositionView,
  Snapshot,
  StageResults,
} from "../lib/types"

interface LiveState {
  connected: boolean
  snapshot: Snapshot
  stageResults: StageResults
  brokerStatus: BrokerStatus
  positions: PositionView[]
  marketTicker: MarketTicker
  connect: () => void
}

const emptyStageResults: StageResults = {
  ORB: { stage1: [], stage2: [], stage3: [] },
}

const emptyBrokerStatus: BrokerStatus = {
  available_capital: 0,
  open_positions: {},
  total_trades: 0,
  trade_log: [],
}

let socket: WebSocket | null = null

export const useLiveStore = create<LiveState>((set) => ({
  connected: false,
  snapshot: {},
  stageResults: emptyStageResults,
  brokerStatus: emptyBrokerStatus,
  positions: [],
  marketTicker: {},

  connect: () => {
    if (socket) return

    const open = () => {
      const proto = window.location.protocol === "https:" ? "wss" : "ws"
      const ws = new WebSocket(`${proto}://${window.location.host}/ws/live`)
      socket = ws

      ws.onopen = () => set({ connected: true })

      ws.onclose = () => {
        set({ connected: false })
        socket = null
        setTimeout(open, 2000)
      }

      ws.onerror = () => ws.close()

      ws.onmessage = (event) => {
        const payload = JSON.parse(event.data) as LivePayload
        set({
          snapshot: payload.snapshot,
          stageResults: payload.stage_results,
          brokerStatus: payload.broker_status,
          positions: payload.positions,
          marketTicker: payload.market_ticker,
        })
      }
    }

    open()
  },
}))
