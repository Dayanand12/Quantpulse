// Short two-tone chime via the Web Audio API — no audio asset to ship.
// Played when a backtest (single run or a batch panel/Run All) finishes,
// so you can switch to something else while it runs instead of tabbing
// back in repeatedly to check.
let ctx: AudioContext | null = null

function getContext(): AudioContext {
  if (!ctx) ctx = new AudioContext()
  return ctx
}

function beep(context: AudioContext, freq: number, startTime: number, duration: number) {
  const osc = context.createOscillator()
  const gain = context.createGain()
  osc.type = "sine"
  osc.frequency.value = freq
  gain.gain.setValueAtTime(0, startTime)
  gain.gain.linearRampToValueAtTime(0.2, startTime + 0.01)
  gain.gain.exponentialRampToValueAtTime(0.001, startTime + duration)
  osc.connect(gain)
  gain.connect(context.destination)
  osc.start(startTime)
  osc.stop(startTime + duration)
}

export function playBacktestCompleteSound() {
  try {
    const context = getContext()
    if (context.state === "suspended") {
      // Browsers can start an AudioContext suspended until a user gesture
      // unlocks it — resume() is a no-op if it's already running. Clicking
      // "Run"/"Run All" is itself a gesture, so this reliably unlocks it.
      void context.resume()
    }
    const now = context.currentTime
    beep(context, 880, now, 0.12)
    beep(context, 1320, now + 0.13, 0.16)
  } catch {
    // Web Audio unavailable/blocked — never let a notification sound break the run itself
  }
}
