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
  unsure: [number, number][]; // centers of the cards we couldn't name
}

export interface Plan {
  play: { card_id: string; name: string; tapped: boolean }[];
  tap: { entry: number; tapped: boolean }[];
  left: CardEntry[]; // your battlefield cards that just left the mat
  arrived: string[]; // names that (re)appeared: their "left" prompts are stale
  unsure: ScannedCard | null; // a new card that needs a human pick
}

const NEAR_PX = 80; // an unsure card this close to one seen before is the same card

const center = (c: ScannedCard): [number, number] => [
  c.quad.reduce((s, p) => s + p[0], 0) / c.quad.length,
  c.quad.reduce((s, p) => s + p[1], 0) / c.quad.length,
];

export function observe(scan: ScannedCard[]): Observation {
  const cards = new Map<string, Seen>();
  const unsure: [number, number][] = [];
  for (const c of scan) {
    if (!c.confident || !c.best?.name) {
      unsure.push(center(c));
      continue;
    }
    const seen = cards.get(c.best.name) ?? { card_id: c.best.card_id, name: c.best.name, total: 0, tapped: 0 };
    seen.total += 1;
    seen.tapped += c.tapped ? 1 : 0;
    cards.set(c.best.name, seen);
  }
  return { cards, total: scan.length, unsure };
}

export function sameObservation(a: Observation, b: Observation): boolean {
  if (a.total !== b.total || a.cards.size !== b.cards.size) return false;
  for (const [name, seen] of a.cards) {
    const other = b.cards.get(name);
    if (!other || other.total !== seen.total || other.tapped !== seen.tapped) return false;
  }
  return true;
}

const none = { total: 0, tapped: 0 };

/** Actions that bring the game in line with a change on the mat. `mine` = your battlefield. */
export function reconcile(prev: Observation | null, next: Observation, mine: CardEntry[], scan: ScannedCard[]): Plan {
  const plan: Plan = { play: [], tap: [], left: [], arrived: [], unsure: null };
  if (!prev) return plan; // first look is the baseline

  const byName = (name: string) => mine.filter((e) => e.name === name);
  let confidentArrivals = 0;

  for (const [name, seen] of next.cards) {
    const before = prev.cards.get(name) ?? none;
    const arrived = seen.total - before.total;
    if (arrived > 0) {
      confidentArrivals += arrived;
      plan.arrived.push(name);
      const plays = Math.min(arrived, seen.total - byName(name).length);
      const arrivedTapped = Math.max(0, seen.tapped - before.tapped); // put down sideways
      for (let i = 0; i < plays; i++) plan.play.push({ card_id: seen.card_id, name, tapped: i < arrivedTapped });
      continue;
    }
    if (arrived < 0) continue;
    const flipped = seen.tapped - before.tapped;
    if (flipped !== 0) {
      const wantTapped = flipped > 0;
      byName(name)
        .filter((e) => e.tapped !== wantTapped)
        .slice(0, Math.abs(flipped))
        .forEach((e) => plan.tap.push({ entry: e.entry_seq, tapped: wantTapped }));
    }
  }

  // Cards that physically left = drop in detected cards + what arrived in
  // their place. A card that merely became unsure (glare, a hand over it)
  // didn't leave, so it can't use up this budget.
  let departures = Math.max(0, prev.total - next.total + confidentArrivals);
  for (const [name, before] of prev.cards) {
    if (departures <= 0) break;
    const now = next.cards.get(name)?.total ?? 0;
    if (now >= before.total) continue;
    const inGame = byName(name);
    const gone = Math.min(before.total - now, inGame.length - now, departures);
    if (gone > 0) {
      plan.left.push(...inGame.slice(-gone)); // most recently played first to go
      departures -= gone;
    }
  }

  if (next.total - prev.total > confidentArrivals) {
    const known = prev.unsure;
    plan.unsure =
      scan.find(
        (c) =>
          !c.confident &&
          c.candidates.length > 0 &&
          known.every(([x, y]) => Math.hypot(center(c)[0] - x, center(c)[1] - y) > NEAR_PX),
      ) ?? null;
  }
  return plan;
}
