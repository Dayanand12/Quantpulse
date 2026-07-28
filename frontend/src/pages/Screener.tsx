import { useEffect, useMemo, useState } from "react"
import { useLiveStore } from "../store/liveStore"
import { StageBadge } from "../components/StageBadge"
import { fmtNumber, fmtPercent } from "../lib/format"
import type { ScreenerRow } from "../lib/types"

type SortKey = keyof Pick<
  ScreenerRow,
  | "symbol"
  | "ltp"
  | "ema5"
  | "ema9"
  | "vwap"
  | "rsi"
  | "volume_ratio"
  | "atr_pct"
  | "distance_to_or_low"
>

const COLUMNS: Array<{ key: SortKey; label: string }> = [
  { key: "symbol", label: "Symbol" },
  { key: "ltp", label: "LTP" },
  { key: "ema5", label: "EMA 5" },
  { key: "ema9", label: "EMA 9" },
  { key: "vwap", label: "VWAP" },
  { key: "rsi", label: "RSI" },
  { key: "volume_ratio", label: "Volume Ratio" },
  { key: "atr_pct", label: "ATR %" },
  { key: "distance_to_or_low", label: "Dist % to OR Low" },
]

const STAGE_RANK: Record<string, number> = { "Stage 3": 3, "Stage 2": 2, "Stage 1": 1, None: 0 }

export function Screener() {
  const connect = useLiveStore((s) => s.connect)
  const snapshot = useLiveStore((s) => s.snapshot)
  const stageResults = useLiveStore((s) => s.stageResults)

  const [sortKey, setSortKey] = useState<SortKey>("volume_ratio")
  const [sortDesc, setSortDesc] = useState(true)

  useEffect(() => {
    connect()
  }, [connect])

  const rows = useMemo<ScreenerRow[]>(() => {
    const s1 = stageResults.ORB.stage1
    const s2 = stageResults.ORB.stage2
    const s3 = stageResults.ORB.stage3

    return Object.entries(snapshot).map(([symbol, data]) => {
      let stage: ScreenerRow["stage"] = "None"
      if (s3.includes(symbol)) stage = "Stage 3"
      else if (s2.includes(symbol)) stage = "Stage 2"
      else if (s1.includes(symbol)) stage = "Stage 1"

      return {
        symbol,
        stage,
        ltp: data.ltp,
        ema5: data.ema5,
        ema9: data.ema9,
        vwap: data.vwap,
        rsi: data.rsi,
        volume_ratio: data.volume_ratio,
        atr_pct: data.atr_pct,
        orb_low: data.orb_low,
        distance_to_or_low: data.distance_to_or_low,
      }
    })
  }, [snapshot, stageResults])

  const sortedRows = useMemo(() => {
    const copy = [...rows]
    copy.sort((a, b) => {
      const stageDiff = STAGE_RANK[b.stage] - STAGE_RANK[a.stage]
      if (stageDiff !== 0) return stageDiff

      const av = a[sortKey]
      const bv = b[sortKey]
      if (av === null || av === undefined) return 1
      if (bv === null || bv === undefined) return -1

      if (typeof av === "string" || typeof bv === "string") {
        return sortDesc
          ? String(bv).localeCompare(String(av))
          : String(av).localeCompare(String(bv))
      }
      return sortDesc ? bv - av : av - bv
    })
    return copy
  }, [rows, sortKey, sortDesc])

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDesc((d) => !d)
    } else {
      setSortKey(key)
      setSortDesc(true)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Live ORB Screener</h1>

      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
        {sortedRows.length === 0 ? (
          <p className="text-sm text-[var(--ink-muted)]">Waiting for live data…</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="text-[var(--ink-muted)]">
              <tr className="border-b border-[var(--border)]">
                <th className="pb-2 font-normal">Stage</th>
                {COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    onClick={() => toggleSort(col.key)}
                    className="cursor-pointer select-none pb-2 font-normal hover:text-[var(--ink-primary)]"
                  >
                    {col.label}
                    {sortKey === col.key && (sortDesc ? " ↓" : " ↑")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((row) => (
                <tr key={row.symbol} className="border-b border-[var(--border)] last:border-0">
                  <td className="py-2">
                    <StageBadge stage={row.stage} />
                  </td>
                  <td className="py-2 font-medium">{row.symbol}</td>
                  <td className="tabular-nums py-2">{fmtNumber(row.ltp)}</td>
                  <td
                    className="tabular-nums py-2"
                    style={{
                      color:
                        row.ema5 !== null && row.ema9 !== null
                          ? row.ema5 >= row.ema9
                            ? "var(--status-good)"
                            : "var(--status-critical)"
                          : undefined,
                    }}
                  >
                    {fmtNumber(row.ema5)}
                  </td>
                  <td className="tabular-nums py-2">{fmtNumber(row.ema9)}</td>
                  <td className="tabular-nums py-2">{fmtNumber(row.vwap)}</td>
                  <td className="tabular-nums py-2">{fmtNumber(row.rsi)}</td>
                  <td className="tabular-nums py-2">{fmtNumber(row.volume_ratio)}</td>
                  <td className="tabular-nums py-2">{fmtPercent(row.atr_pct)}</td>
                  <td className="tabular-nums py-2">{fmtPercent(row.distance_to_or_low, 3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
