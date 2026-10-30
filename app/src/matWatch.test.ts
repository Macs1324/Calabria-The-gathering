import { describe, expect, it } from "vitest";
import type { CardEntry, ScannedCard } from "./api";
import { observe, reconcile, sameObservation } from "./matWatch";

const scanned = (
  name: string,
  opts: { tapped?: boolean; confident?: boolean; id?: string; at?: [number, number] } = {},
): ScannedCard => {
  const cand = { card_id: opts.id ?? `id-${name}`, name, set_code: "tst", distance: 10 };
  const [x, y] = opts.at ?? [0, 0];
  return {
    quad: [[x, y], [x + 100, y], [x + 100, y + 140], [x, y + 140]],
    tapped: opts.tapped ?? false,
    confident: opts.confident ?? true,
    candidates: [cand],
    best: cand,
  };
};

let seq = 100;
const entry = (name: string, tapped = false): CardEntry => ({
  card_id: `id-${name}`,
  name,
  owner: "me",
  controller: "me",
  entry_seq: seq++,
  tapped,
  counters: {},
  token: false,
});

const step = (prev: ScannedCard[] | null, next: ScannedCard[], mine: CardEntry[]) =>
  reconcile(prev && observe(prev), observe(next), mine, next);

describe("observe", () => {
  it("counts confident cards by name, tapped separately", () => {
    const o = observe([scanned("Forest"), scanned("Forest", { tapped: true }), scanned("Bolt", { confident: false })]);
    expect(o.cards.get("Forest")).toMatchObject({ total: 2, tapped: 1 });
    expect(o.cards.has("Bolt")).toBe(false);
    expect(o.total).toBe(3);
  });

  it("compares observations by content", () => {
    expect(sameObservation(observe([scanned("A")]), observe([scanned("A")]))).toBe(true);
    expect(sameObservation(observe([scanned("A")]), observe([scanned("A", { tapped: true })]))).toBe(false);
  });
});

describe("reconcile", () => {
  it("first observation is only a baseline", () => {
    const plan = step(null, [scanned("Forest")], []);
    expect(plan.play).toEqual([]);
    expect(plan.tap).toEqual([]);
  });

  it("plays a card that appears on the mat", () => {
    const plan = step([], [scanned("Sol Ring")], []);
    expect(plan.play).toEqual([{ card_id: "id-Sol Ring", name: "Sol Ring", tapped: false }]);
  });

  it("does not replay a card already in play (e.g. added by typing)", () => {
    expect(step([], [scanned("Sol Ring")], [entry("Sol Ring")]).play).toEqual([]);
  });

  it("plays only the extra copy", () => {
    const plan = step([scanned("Forest")], [scanned("Forest"), scanned("Forest")], [entry("Forest")]);
    expect(plan.play).toHaveLength(1);
  });

  it("syncs a physical tap to an untapped copy", () => {
    const forest = entry("Forest");
    const plan = step([scanned("Forest")], [scanned("Forest", { tapped: true })], [forest]);
    expect(plan.tap).toEqual([{ entry: forest.entry_seq, tapped: true }]);
  });

  it("syncs a physical untap", () => {
    const forest = entry("Forest", true);
    const plan = step([scanned("Forest", { tapped: true })], [scanned("Forest")], [forest]);
    expect(plan.tap).toEqual([{ entry: forest.entry_seq, tapped: false }]);
  });

  it("leaves digital taps alone when nothing changed physically", () => {
    expect(step([scanned("Forest")], [scanned("Forest")], [entry("Forest", true)]).tap).toEqual([]);
  });

  it("reports cards that left the mat", () => {
    const bolt = entry("Lightning Bolt");
    const plan = step([scanned("Lightning Bolt")], [], [bolt]);
    expect(plan.left.map((e) => e.entry_seq)).toEqual([bolt.entry_seq]);
  });

  it("does not report a departure for a card already moved digitally", () => {
    expect(step([scanned("Lightning Bolt")], [], []).left).toEqual([]);
  });

  it("asks about a new card it cannot identify", () => {
    const unsure = scanned("Mystery", { confident: false });
    const plan = step([scanned("Forest")], [scanned("Forest"), unsure], [entry("Forest")]);
    expect(plan.play).toEqual([]);
    expect(plan.unsure).toBe(unsure);
  });

  it("does not ask when the unidentified card was already there", () => {
    const unsure = scanned("Mystery", { confident: false });
    expect(step([unsure], [unsure], []).unsure).toBeNull();
  });

  // --- review fixes ---------------------------------------------------------

  it("a card that only became unsure has not left the mat", () => {
    const flaky = scanned("Forest", { confident: false });
    expect(step([scanned("Forest")], [flaky], [entry("Forest")]).left).toEqual([]);
  });

  it("a card that arrives tapped is played tapped", () => {
    const plan = step([], [scanned("Forest", { tapped: true })], []);
    expect(plan.play).toEqual([{ card_id: "id-Forest", name: "Forest", tapped: true }]);
  });

  it("asks about the new unsure card, not one that was already there", () => {
    const old = scanned("Old", { confident: false, at: [0, 0] });
    const fresh = scanned("Fresh", { confident: false, at: [600, 300] });
    expect(step([old], [old, fresh], []).unsure).toBe(fresh);
  });

  it("reports names that came back, so stale prompts can go", () => {
    const plan = step([], [scanned("Lightning Bolt")], [entry("Lightning Bolt")]);
    expect(plan.arrived).toEqual(["Lightning Bolt"]);
  });
});