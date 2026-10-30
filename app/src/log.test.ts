import { describe, expect, it } from "vitest";
import { LogEvent } from "./api";
import { turnMarks } from "./Log";

const ev = (seq: number, type: string): LogEvent => ({
  seq,
  type,
  actor: "Max",
  payload: {},
});

describe("turnMarks", () => {
  it("numbers turn changes back from the current turn", () => {
    const log = [ev(1, "card_play"), ev(2, "turn_end"), ev(3, "turn_end")];
    expect([...turnMarks(log, 3)]).toEqual([
      [3, 3],
      [2, 2],
    ]);
  });

  it("stays right when the log is only the tail of a long game", () => {
    // turn 9 now; the window starts mid-game
    const log = [ev(301, "card_tap"), ev(302, "turn_end"), ev(303, "card_play")];
    expect(turnMarks(log, 9).get(302)).toBe(9);
  });

  it("restarts at turn 1 after a reset, unknown before it", () => {
    const log = [ev(1, "turn_end"), ev(2, "game_reset"), ev(3, "turn_end")];
    const marks = turnMarks(log, 2);
    expect(marks.get(3)).toBe(2);
    expect(marks.get(2)).toBe(1);
    expect(marks.get(1)).toBeNull();
  });
});
