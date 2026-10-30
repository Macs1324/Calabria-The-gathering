import { useEffect, useMemo, useRef } from "react";
import { GameState, LogEvent } from "./api";
import { seatColor } from "./seats";

/** The game so far, newest at the bottom, a marker at every turn change. */
export function Log({ log, state }: { log: LogEvent[]; state: GameState }) {
  const names = useMemo(() => cardNames(log, state), [log, state]);
  const endRef = useRef<HTMLLIElement>(null);
  useEffect(() => {
    // Block body on purpose: newer browsers return a Promise from
    // scrollIntoView, which React would take for a cleanup function.
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [log.length]);

  let turn = 1;
  return (
    <section className="dock-section log">
      <h4>Activity</h4>
      <ol>
        {log.map((e) => {
          const [who, text] = describe(e, names);
          const item = (
            <li key={e.seq} className={e.type}>
              {who && (
                <b style={{ color: seatColor(state.players, who) }}>{who}</b>
              )}{" "}
              {text}
            </li>
          );
          if (e.type === "game_reset") turn = 1;
          if (e.type !== "turn_end" && e.type !== "game_reset") return item;
          if (e.type === "turn_end") turn += 1;
          return [
            item,
            <li key={`${e.seq}-mark`} className="turn-mark">
              <span>Turn {turn}</span>
            </li>,
          ];
        })}
        <li ref={endRef} className="end" />
      </ol>
    </section>
  );
}

function cardNames(log: LogEvent[], state: GameState): Map<number, string> {
  const names = new Map<number, string>();
  for (const e of log) {
    if (e.type === "card_play")
      names.set(e.seq, String(e.payload.name ?? e.payload.card_id ?? "a card"));
  }
  for (const zone of [
    "battlefield",
    "graveyard",
    "exile",
    "command",
  ] as const) {
    for (const c of state[zone]) names.set(c.entry_seq, c.name ?? c.card_id);
  }
  return names;
}

const plural = (n: number, word: string) =>
  `${n} ${word}${n === 1 ? "" : "s"}`;

/** [who did it, what they did]: the name is drawn in its seat colour. */
function describe(
  e: LogEvent,
  names: Map<number, string>,
): [string | null, string] {
  const p = e.payload;
  const card = names.get(Number(p.entry)) ?? "a card";
  switch (e.type) {
    case "player_join":
      return [e.actor, "sat down"];
    case "player_leave":
      return [e.actor, "left the table"];
    case "card_play": {
      const where = p.zone && p.zone !== "battlefield" ? ` into ${p.zone}` : "";
      return [
        e.actor,
        `played ${p.name ?? p.card_id}${p.token ? " (token)" : ""}${where}${p.tapped ? ", tapped" : ""}`,
      ];
    }
    case "card_tap":
      return [e.actor, `${p.tapped ? "tapped" : "untapped"} ${card}`];
    case "card_move":
      return [e.actor, `moved ${card} to ${p.zone}`];
    case "card_counter": {
      const n = Number(p.delta);
      const counters = plural(Math.abs(n), `${p.kind} counter`);
      return [
        e.actor,
        n >= 0 ? `put ${counters} on ${card}` : `removed ${counters} from ${card}`,
      ];
    }
    case "card_control":
      return [String(p.player), `gained control of ${card}`];
    case "untap_all":
      return [e.actor, "untapped everything"];
    case "life_change": {
      const n = Number(p.delta);
      if (!p.player || p.player === e.actor)
        return [e.actor, `${n < 0 ? "lost" : "gained"} ${Math.abs(n)} life`];
      return [
        e.actor,
        n < 0
          ? `took ${-n} life from ${p.player}`
          : `gave ${p.player} ${n} life`,
      ];
    }
    case "phase_set":
      return [e.actor, `moved to ${p.phase}`];
    case "turn_end":
      return [e.actor, "ended the turn"];
    case "dice_roll":
      return [e.actor, `rolled ${p.result} on a d${p.sides}`];
    case "game_reset":
      return [
        e.actor,
        `started a new game (${p.starting_life ?? 20} life, ${p.first ?? "first seat"} starts)`,
      ];
    default:
      return [e.actor, e.type];
  }
}
