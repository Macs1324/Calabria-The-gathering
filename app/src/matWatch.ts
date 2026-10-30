// Hands-free play: turn what the camera sees on your mat into game actions.
//
// Everything is edge-triggered: only a *change* between two stable views of
// the mat causes an action. So a card you moved digitally (typed, undone,
// sent to the graveyard) is never fought over just because it still lies on
// the table, and digital taps survive until the physical card actually moves.
// Only `confident` identifications act on their own; a new card the server is
// unsure about is handed back for a one-tap (or one-word) confirm.

import type { CardEntry, ScannedCard } from "./api";

export interface Seen {
  card_id: string;
  name: string;
  total: number;
  tapped: number;
}

export interface Observation {
  cards: Map<string, Seen>; // confident cards, by name
  total: number; // every detected card, confident or not
}

export interface Plan {
  play: { card_id: string; name: string }[];
  tap: { entry: number; tapped: boolean }[];
  left: CardEntry[]; // your battlefield cards that just left the mat
  unsure: ScannedCard | null; // a new card that needs a human pick
}

export function observe(scan: ScannedCard[]): Observation {
  const cards = new Map<string, Seen>();
  for (const c of scan) {
    if (!c.confident || !c.best?.name) continue;
    const seen = cards.get(c.best.name) ?? {
      card_id: c.best.card_id,
      name: c.best.name,
      total: 0,
      tapped: 0,
    };
    seen.total += 1;
    seen.tapped += c.tapped ? 1 : 0;
    cards.set(c.best.name, seen);
  }
  return { cards, total: scan.length };
}

export function sameObservation(a: Observation, b: Observation): boolean {
  if (a.total !== b.total || a.cards.size !== b.cards.size) return false;
  for (const [name, seen] of a.cards) {
    const other = b.cards.get(name);
    if (!other || other.total !== seen.total || other.tapped !== seen.tapped)
      return false;
  }
  return true;
}

const none = { total: 0, tapped: 0 };

/** Actions that bring the game in line with a change on the mat. `mine` = your battlefield. */
export function reconcile(
  prev: Observation | null,
  next: Observation,
  mine: CardEntry[],
  scan: ScannedCard[],
): Plan {
  const plan: Plan = { play: [], tap: [], left: [], unsure: null };
  if (!prev) return plan; // first look is the baseline

  const byName = (name: string) => mine.filter((e) => e.name === name);
  let confidentArrivals = 0;

  for (const [name, seen] of next.cards) {
    const before = prev.cards.get(name) ?? none;
    const arrived = seen.total - before.total;
    if (arrived > 0) {
      confidentArrivals += arrived;
      const missingInGame = seen.total - byName(name).length;
      for (let i = 0; i < Math.min(arrived, missingInGame); i++)
        plan.play.push({ card_id: seen.card_id, name });
      continue; // a fresh arrival's tap state settles on the next look
    }
    if (arrived < 0) continue;
    const flipped = seen.tapped - before.tapped;
    if (flipped !== 0) {
      const wantTapped = flipped > 0;
      byName(name)
        .filter((e) => e.tapped !== wantTapped)
        .slice(0, Math.abs(flipped))
        .forEach((e) =>
          plan.tap.push({ entry: e.entry_seq, tapped: wantTapped }),
        );
    }
  }

  for (const [name, before] of prev.cards) {
    const now = next.cards.get(name)?.total ?? 0;
    if (now >= before.total) continue;
    const inGame = byName(name);
    const gone = Math.min(before.total - now, inGame.length - now);
    if (gone > 0) plan.left.push(...inGame.slice(-gone)); // most recently played first to go
  }

  if (next.total - prev.total > confidentArrivals) {
    plan.unsure =
      scan.find((c) => !c.confident && c.candidates.length > 0) ?? null;
  }
  return plan;
}
