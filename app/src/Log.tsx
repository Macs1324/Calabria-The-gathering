import { useEffect, useMemo, useRef } from "react";
import { GameState, LogEvent } from "./api";

/** Human-readable game log, newest at the bottom. */
export function Log({ log, state }: { log: LogEvent[]; state: GameState }) {
  const names = useMemo(() => cardNames(log, state), [log, state]);
  const endRef = useRef<HTMLLIElement>(null);
  useEffect(() => {
    // Block body on purpose: newer browsers return a Promise from
    // scrollIntoView, which React would take for a cleanup function.
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [log.length]);

  return (
    <section className="panel log">
      <h4>Log</h4>
      <ol>
        {log.map((e) => (
          <li key={e.seq} className={e.type}>
            {describe(e, names)}
          </li>
        ))}
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

const signed = (n: number) => (n > 0 ? `+${n}` : `${n}`);

function describe(e: LogEvent, names: Map<number, string>): string {
  const p = e.payload;
  const card = names.get(Number(p.entry)) ?? "a card";
  switch (e.type) {
    case "player_join":
      return `${e.actor} sat down`;
    case "player_leave":
      return `${e.actor} left`;
    case "card_play": {
      const where = p.zone && p.zone !== "battlefield" ? ` into ${p.zone}` : "";
      return `${e.actor} played ${p.name ?? p.card_id}${p.token ? " (token)" : ""}${where}${p.tapped ? ", tapped" : ""}`;
    }
    case "card_tap":
      return `${e.actor} ${p.tapped ? "tapped" : "untapped"} ${card}`;
    case "card_move":
      return `${e.actor} moved ${card} to ${p.zone}`;
    case "card_counter":
      return `${e.actor}: ${signed(Number(p.delta))} ${p.kind} on ${card}`;
    case "card_control":
      return `${p.player} gained control of ${card}`;
    case "untap_all":
      return `${e.actor} untapped everything`;
    case "life_change": {
      const who = p.player && p.player !== e.actor ? `${p.player}'s` : "their";
      return `${e.actor}: ${signed(Number(p.delta))} to ${who} life`;
    }
    case "phase_set":
      return `${e.actor} → ${p.phase}`;
    case "turn_end":
      return `${e.actor} ended the turn`;
    case "dice_roll":
      return `${e.actor} rolled ${p.result} on a d${p.sides}`;
    case "game_reset":
      return `${e.actor} started a new game (${p.starting_life ?? 20} life, ${p.first ?? "first seat"} starts)`;
    default:
      return `${e.actor}: ${e.type}`;
  }
}
