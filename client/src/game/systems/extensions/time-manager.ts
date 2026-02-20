/** Time Manager - runs in PlanarAlly client, persists when extension modal is closed */

export interface TimeManagerItem {
    id: string;
    name: string;
    mode: "countdown" | "timer";
    /** For countdown: target in ms. For timer: not used. */
    targetMs: number;
    /** Elapsed ms (for timer) or remaining ms (for countdown when running) */
    valueMs: number;
    running: boolean;
    /** Timestamp when started (Date.now()) */
    startTime?: number;
}

const STORAGE_KEY = "pa-time-manager";
let items: TimeManagerItem[] = [];
let tickInterval: ReturnType<typeof setInterval> | null = null;
function loadState(): void {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (raw) {
            const parsed = JSON.parse(raw) as TimeManagerItem[];
            items = parsed.map((x) => ({
                ...x,
                running: false,
                startTime: undefined,
                valueMs: x.mode === "countdown" ? x.targetMs : x.valueMs ?? 0,
            }));
        }
    } catch {
        items = [];
    }
    if (items.length === 0) {
        items = [{ id: uid(), name: "Timer 1", mode: "timer", targetMs: 60000, valueMs: 0, running: false }];
    }
}

function saveState(): void {
    try {
        const toSave = items.map((x) => ({
            id: x.id,
            name: x.name,
            mode: x.mode,
            targetMs: x.targetMs,
            valueMs: x.mode === "countdown" ? x.targetMs : x.valueMs,
        }));
        localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
    } catch {
        /* ignore */
    }
}

function uid(): string {
    return `tm-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export const COUNTDOWN_COMPLETE_EVENT = "pa-time-manager-countdown-complete";

function dispatchCountdownComplete(name: string): void {
    try {
        window.dispatchEvent(new CustomEvent(COUNTDOWN_COMPLETE_EVENT, { detail: { name } }));
    } catch {
        /* ignore */
    }
}

function playAlert(): void {
    try {
        const ctx = new (window.AudioContext || (window as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
        const playBeep = (freq: number) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.frequency.value = freq;
            osc.type = "sine";
            gain.gain.setValueAtTime(0.3, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);
            osc.start(ctx.currentTime);
            osc.stop(ctx.currentTime + 0.4);
        };
        playBeep(880);
        setTimeout(() => playBeep(1100), 150);
    } catch {
        /* Audio not available */
    }
}

function tick(): void {
    const now = Date.now();
    let changed = false;
    for (const item of items) {
        if (!item.running || item.startTime == null) continue;
        const elapsed = now - item.startTime;
        if (item.mode === "countdown") {
            const remaining = Math.max(0, item.targetMs - elapsed);
            if (remaining !== item.valueMs) {
                item.valueMs = remaining;
                changed = true;
            }
            if (remaining <= 0) {
                item.running = false;
                item.startTime = undefined;
                item.valueMs = 0;
                changed = true;
                playAlert();
                dispatchCountdownComplete(item.name);
                broadcastState();
            }
        } else {
            item.valueMs = elapsed;
            changed = true;
        }
    }
    if (changed) broadcastState();
}

const CHANNEL_NAME = "pa-time-manager";
let bc: BroadcastChannel | null = null;
function getChannel(): BroadcastChannel | null {
    if (typeof BroadcastChannel === "undefined") return null;
    if (!bc) bc = new BroadcastChannel(CHANNEL_NAME);
    return bc;
}
function broadcastState(): void {
    const data = JSON.parse(JSON.stringify(items));
    getChannel()?.postMessage({ type: "state", items: data });
}

function startTick(): void {
    if (tickInterval) return;
    tickInterval = setInterval(tick, 100);
}

function stopTick(): void {
    if (!tickInterval) return;
    clearInterval(tickInterval);
    tickInterval = null;
}

function ensureTick(): void {
    if (items.some((x) => x.running)) startTick();
    else stopTick();
}

export function timeManagerHandleMessage(data: unknown, source: Window | null): boolean {
    const d = data as { type?: string; id?: string; [k: string]: unknown };
    if (d?.type !== "time-manager-get-state" && d?.type?.startsWith("time-manager-") !== true) return false;

    if (d.type === "time-manager-get-state") {
        const data = { type: "time-manager-state", items: JSON.parse(JSON.stringify(items)) };
        if (source) source.postMessage(data, "*");
        broadcastState();
        return true;
    }

    if (d.type === "time-manager-add") {
        const mode = (d.mode as "countdown" | "timer") ?? "timer";
        const name = (d.name as string) ?? `Timer ${items.length + 1}`;
        const targetMs = Math.max(0, Number(d.targetMs) ?? 60000);
        items.push({
            id: uid(),
            name,
            mode,
            targetMs,
            valueMs: mode === "countdown" ? targetMs : 0,
            running: false,
        });
        saveState();
        broadcastState();
        return true;
    }

    if (d.type === "time-manager-remove" && d.id) {
        items = items.filter((x) => x.id !== d.id);
        saveState();
        ensureTick();
        broadcastState();
        return true;
    }

    if (d.type === "time-manager-update" && d.id) {
        const item = items.find((x) => x.id === d.id);
        if (item) {
            if (d.name !== undefined) item.name = String(d.name);
            if (d.mode !== undefined) item.mode = d.mode as "countdown" | "timer";
            if (d.targetMs !== undefined) item.targetMs = Math.max(0, Number(d.targetMs));
            if (!item.running && d.mode === "countdown") item.valueMs = item.targetMs;
            saveState();
            broadcastState();
        }
        return true;
    }

    if (d.type === "time-manager-start" && d.id) {
        const item = items.find((x) => x.id === d.id);
        if (item && !item.running) {
            item.running = true;
            if (item.mode === "countdown") {
                item.startTime = Date.now() - (item.targetMs - item.valueMs);
            } else {
                item.startTime = Date.now() - item.valueMs;
            }
            saveState();
            ensureTick();
            broadcastState();
        }
        return true;
    }

    if (d.type === "time-manager-stop" && d.id) {
        const item = items.find((x) => x.id === d.id);
        if (item && item.running) {
            item.running = false;
            if (item.mode === "timer") {
                item.valueMs = Date.now() - (item.startTime ?? 0);
            }
            item.startTime = undefined;
            saveState();
            ensureTick();
            broadcastState();
        }
        return true;
    }

    if (d.type === "time-manager-reset" && d.id) {
        const item = items.find((x) => x.id === d.id);
        if (item) {
            item.running = false;
            item.startTime = undefined;
            item.valueMs = item.mode === "countdown" ? item.targetMs : 0;
            saveState();
            ensureTick();
            broadcastState();
        }
        return true;
    }

    return false;
}

loadState();
if (items.some((x) => x.running)) startTick();
