import { describe, expect, it } from "vitest";
import { parseCommand } from "./voice";

const ctx = { you: "Max", players: ["Max", "Bea"] };
const p = (text: string) => parseCommand(text, ctx);

describe("parseCommand", () => {
  it("turn flow", () => {
    expect(p("end turn")).toEqual({ kind: "event", type: "turn_end", payload: {} });
    expect(p("Pass the turn")).toEqual({ kind: "event", type: "turn_end", payload: {} });
    expect(p("untap")).toEqual({ kind: "event", type: "untap_all", payload: {} });
    expect(p("go to combat")).toEqual({ kind: "event", type: "phase_set", payload: { phase: "combat" } });
    expect(p("undo")).toEqual({ kind: "undo" });
  });

  it("own life, digits or words", () => {
    expect(p("lose 3")).toEqual({ kind: "event", type: "life_change", payload: { delta: -3, player: "Max" } });
    expect(p("I lose three life")).toEqual({ kind: "event", type: "life_change", payload: { delta: -3, player: "Max" } });
    expect(p("gain 4 life")).toEqual({ kind: "event", type: "life_change", payload: { delta: 4, player: "Max" } });
  });

  it("damage to others", () => {
    const hitBea = { kind: "event", type: "life_change", payload: { delta: -4, player: "Bea" } };
    expect(p("hit Bea for 4")).toEqual(hitBea);
    expect(p("deal four damage to bea")).toEqual(hitBea);
    expect(p("opponent loses 4")).toEqual(hitBea); // the only opponent
    expect(p("bea loses four life")).toEqual(hitBea);
  });

  it("dice", () => {
    expect(p("roll a d20")).toEqual({ kind: "event", type: "dice_roll", payload: { sides: 20 } });
    expect(p("roll d 6")).toEqual({ kind: "event", type: "dice_roll", payload: { sides: 6 } });
    expect(p("flip a coin")).toEqual({ kind: "event", type: "dice_roll", payload: { sides: 2 } });
  });

  it("card and candidate commands", () => {
    expect(p("play lightning bolt")).toEqual({ kind: "play", query: "lightning bolt" });
    expect(p("scan")).toEqual({ kind: "scan" });
    expect(p("second one")).toEqual({ kind: "pick", index: 1 });
    expect(p("number three")).toEqual({ kind: "pick", index: 2 });
  });

  it("ignores table talk", () => {
    expect(p("I think I should pass on that")).toBeNull();
    expect(p("what a great play")).toBeNull();
    expect(p("")).toBeNull();
  });

  it("does not hit an ambiguous opponent", () => {
    expect(parseCommand("opponent loses 2", { you: "Max", players: ["Max", "Bea", "Cy"] })).toBeNull();
  });

  it("targets players whose names have digits or accents", () => {
    const c = { you: "Max", players: ["Max", "José", "Bea2"] };
    expect(parseCommand("hit jose for 3", c)).toEqual({ kind: "event", type: "life_change", payload: { delta: -3, player: "José" } });
    expect(parseCommand("Bea2 loses 1", c)).toEqual({ kind: "event", type: "life_change", payload: { delta: -1, player: "Bea2" } });
  });
});