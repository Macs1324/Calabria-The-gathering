// Server API: REST helpers, shared types, and per-room seat storage.
//
// Served by the FastAPI server (or Vite's dev proxy) the client talks to its
// own origin. Inside the Tauri shell there is no HTTP origin, so it falls back
// to a saved server URL, then to a local server.

export const PUBLIC_ZONES = [
  "battlefield",
  "graveyard",
  "exile",
  "command",
] as const;
export type Zone = (typeof PUBLIC_ZONES)[number];
export type MoveTarget = Zone | "hand" | "library";

export interface CardEntry {
  card_id: string;
  name: string | null;
  owner: string;
  controller: string;
  entry_seq: number;
  tapped: boolean;
  counters: Record<string, number>;
  token: boolean;
}

export interface GameState {
  players: string[];
  battlefield: CardEntry[];
  graveyard: CardEntry[];
  exile: CardEntry[];
  command: CardEntry[];
  life: Record<string, number>;
  turn: { number: number; player: string | null };
  phase: string;
  last_roll: { player: string; sides: number; result: number } | null;
}

export interface LogEvent {
  seq: number;
  type: string;
  actor: string;
  payload: Record<string, unknown>;
}

export interface View {
  kind: "view";
  room_id: string;
  state: GameState;
  log: LogEvent[];
  online: string[];
  you: string | null;
}

export interface CardHit {
  card_id: string;
  name: string;
  set_code: string;
}

export interface ScanCandidate {
  card_id: string;
  name: string | null;
  set_code: string | null;
  distance: number;
}

export interface ScannedCard {
  quad: [number, number][];
  tapped: boolean;
  candidates: ScanCandidate[];
  best: ScanCandidate | null;
  confident: boolean; // safe to act on without asking (hands-free mode)
}

export interface Seat {
  name: string;
  token: string;
}

const SERVER_KEY = "calabria.server";
const NAME_KEY = "calabria.name";
const seatKey = (room: string) => `calabria.seat.${room.toUpperCase()}`;

// Storage can be unavailable (private windows, blocked site data): never let
// that break the app, it only costs the remembered seat.
export function storageGet(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function storageSet(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* best effort */
  }
}

export function serverBase(): string {
  const saved = storageGet(SERVER_KEY);
  if (saved) return saved.replace(/\/+$/, "");
  return location.protocol.startsWith("http") ? "" : "http://127.0.0.1:8000";
}

export function setServerBase(url: string | null): void {
  storageSet(SERVER_KEY, url && url.trim() ? url.trim() : null);
}

export const isHttpOrigin = () => location.protocol.startsWith("http");

export function wsUrl(path: string): string {
  const base = serverBase() || location.origin;
  return base.replace(/^http/, "ws") + path;
}

export function cardImage(
  cardId: string,
  version: "small" | "normal" = "normal",
): string {
  return `${serverBase()}/cards/${encodeURIComponent(cardId)}/image?version=${version}`;
}

export const rememberedName = () => storageGet(NAME_KEY) ?? "";
export const rememberName = (name: string) => storageSet(NAME_KEY, name);

export function loadSeat(room: string): Seat | null {
  const raw = storageGet(seatKey(room));
  if (!raw) return null;
  try {
    const seat = JSON.parse(raw) as Seat;
    return seat.name && seat.token ? seat : null;
  } catch {
    return null;
  }
}

export const saveSeat = (room: string, seat: Seat) =>
  storageSet(seatKey(room), JSON.stringify(seat));
export const forgetSeat = (room: string) => storageSet(seatKey(room), null);

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(serverBase() + path, init);
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = ((await res.json()) as { detail?: unknown }).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(
      typeof detail === "string" ? detail : JSON.stringify(detail),
      res.status,
    );
  }
  return (await res.json()) as T;
}

const postJson = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<{ status: string }>("/health"),
  createRoom: () => request<{ room_id: string }>("/rooms", { method: "POST" }),
  roomState: (room: string) =>
    request<GameState>(`/rooms/${encodeURIComponent(room)}`),
  join: (room: string, name: string, token?: string) =>
    request<{ room_id: string; name: string; token: string }>(
      `/rooms/${encodeURIComponent(room)}/join`,
      postJson({ name, token: token ?? null }),
    ),
  search: (q: string, signal?: AbortSignal) =>
    request<{ results: CardHit[] }>(
      `/cards/search?q=${encodeURIComponent(q)}&limit=8`,
      { signal },
    ),
  scan: (imageBase64: string, mode: "single" | "all" = "single") =>
    request<{ cards: ScannedCard[] }>(
      "/vision/scan",
      postJson({ image: imageBase64, mode }),
    ),
};
