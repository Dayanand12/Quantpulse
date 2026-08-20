// Deep link into Zerodha Kite's own chart view for a symbol. Confirmed
// against a real Kite Web URL (copied from the browser address bar after
// opening a symbol's chart there):
//   https://kite.zerodha.com/markets/ext/chart/web/tvc/NSE/NTPC/2977281
// The trailing number is Kite's own instrument_token — there's no way to
// derive it from the symbol name alone, so callers must resolve it first
// via api.instrumentRefs() (backed by /api/instrument-refs, which reads
// Kite's own instrument dump — see core/domain/models.py::InstrumentRef).
export function zerodhaChartUrl(exchange: string, symbol: string, instrumentToken: number): string {
  return `https://kite.zerodha.com/markets/ext/chart/web/tvc/${exchange}/${encodeURIComponent(symbol)}/${instrumentToken}`
}
