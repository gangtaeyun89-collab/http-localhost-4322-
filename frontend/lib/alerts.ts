// Browser-side alert pipeline.
//
// The dashboard polls /api/pairs/quotes every few seconds and watches for
// pairs that cross the entry threshold (|z| >= 2 by default). When a cross
// happens we:
//   * push a record into localStorage so the AlertHistory panel can replay it
//   * fire a desktop notification if the user granted permission
//   * play a short tone via the WebAudio API
//
// A per-pair cooldown stops the same z=2.05 hovering pair from spamming the
// user every poll cycle. Cooldown lives in memory; reloading the page lets
// alerts re-fire, which is the right behaviour for a trading desk that has
// just sat down.

export type AlertSeverity = "warn" | "crit";

export type AlertEvent = {
  id: string; // pair id, e.g. "EQR-MAA"
  base: string;
  quote: string;
  zscore: number;
  signal: "long_spread" | "short_spread";
  severity: AlertSeverity;
  ts: number; // epoch ms
};

const STORAGE_KEY = "statarb.alerts.history.v1";
const STORAGE_LIMIT = 100;
const COOLDOWN_MS = 60_000; // one alert per pair per minute

const cooldown = new Map<string, number>();
let audioCtx: AudioContext | null = null;

export function alertSeverity(absZ: number): AlertSeverity | null {
  if (absZ >= 2.5) return "crit";
  if (absZ >= 2.0) return "warn";
  return null;
}

export function shouldFire(pairId: string, severity: AlertSeverity): boolean {
  // Critical alerts always re-fire on each upgrade from warn -> crit; warn
  // alerts respect the cooldown so a pair hovering at z=2.05 doesn't beep
  // every tick.
  const now = Date.now();
  const last = cooldown.get(pairId) ?? 0;
  if (severity === "crit") {
    if (now - last < 10_000) return false;
    cooldown.set(pairId, now);
    return true;
  }
  if (now - last < COOLDOWN_MS) return false;
  cooldown.set(pairId, now);
  return true;
}

export function resetCooldown(pairId?: string) {
  if (pairId) cooldown.delete(pairId);
  else cooldown.clear();
}

export function pushHistory(evt: AlertEvent) {
  if (typeof window === "undefined") return;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const list: AlertEvent[] = raw ? JSON.parse(raw) : [];
    list.unshift(evt);
    const trimmed = list.slice(0, STORAGE_LIMIT);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
    // Notify same-tab subscribers; the 'storage' event only fires across
    // tabs, not within the writing tab.
    window.dispatchEvent(new CustomEvent("statarb.alerts.update"));
  } catch {
    // localStorage can be unavailable (private browsing, full quota) -- we
    // just skip persistence in that case.
  }
}

export function readHistory(): AlertEvent[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function clearHistory() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
  window.dispatchEvent(new CustomEvent("statarb.alerts.update"));
}

export async function ensureNotificationPermission(): Promise<NotificationPermission> {
  if (typeof Notification === "undefined") return "denied";
  if (Notification.permission === "granted") return "granted";
  if (Notification.permission === "denied") return "denied";
  try {
    return await Notification.requestPermission();
  } catch {
    return "denied";
  }
}

export function notifyBrowser(evt: AlertEvent) {
  if (typeof Notification === "undefined") return;
  if (Notification.permission !== "granted") return;
  const direction =
    evt.signal === "short_spread" ? "SHORT SPREAD" : "LONG SPREAD";
  try {
    new Notification(`${evt.base} / ${evt.quote} · ${direction}`, {
      body: `z-score ${evt.zscore >= 0 ? "+" : ""}${evt.zscore.toFixed(2)}`,
      tag: evt.id, // collapses repeat alerts on the same pair
      silent: false,
    });
  } catch {
    // Some browsers throw on permissionless construction even after grant
    // (e.g. cross-origin iframes). Fall through silently.
  }
}

export function playTone(severity: AlertSeverity) {
  if (typeof window === "undefined") return;
  if (typeof window.AudioContext === "undefined") return;
  try {
    if (!audioCtx) audioCtx = new AudioContext();
    if (audioCtx.state === "suspended") audioCtx.resume();
    const t0 = audioCtx.currentTime;

    // Two-tone beep for crit, single tone for warn -- the audio answers
    // "how urgent?" without you needing to look at the screen.
    const beeps = severity === "crit" ? [880, 1240] : [660];
    beeps.forEach((freq, i) => {
      const start = t0 + i * 0.18;
      const osc = audioCtx!.createOscillator();
      const gain = audioCtx!.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0, start);
      gain.gain.linearRampToValueAtTime(0.18, start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.001, start + 0.14);
      osc.connect(gain);
      gain.connect(audioCtx!.destination);
      osc.start(start);
      osc.stop(start + 0.16);
    });
  } catch {
    // No audio output / blocked autoplay -- silently skip.
  }
}
