import { useState } from "react";
import { CardEntry, GameState, Zone, cardImage } from "./api";
import { RoomActions } from "./useRoom";

const SIDE_ZONES: [Zone, string][] = [
  ["graveyard", "Graveyard"],
  ["exile", "Exile"],
  ["command", "Command"],
];
const LIFE_STEPS = [-5, -1, 1, 5];

/** One player's side of the table: life, battlefield, and public piles. */
export function Board({
  player,
  state,
  you,
  online,
  selected,
  onSelect,
  onPreview,
  send,
}: {
  player: string;
  state: GameState;
  you: string | null;
  online: boolean;
  selected: number | null;
  onSelect: (seq: number) => void;
  onPreview: (card: CardEntry | null) => void;
  send: RoomActions["send"];
}) {
  const [open, setOpen] = useState<Zone | null>(null);
  const mine = player === you;
  const battlefield = state.battlefield.filter((c) => c.controller === player);
  const active = state.turn.player === player;

  return (
    <section
      className={`board ${mine ? "mine" : ""} ${active ? "active" : ""}`}
    >
      <div className="board-head">
        <span
          className={`dot ${online ? "on" : ""}`}
          title={online ? "online" : "offline"}
        />
        <h3>{mine ? `${player} (you)` : player}</h3>
        {active && <span className="badge">{mine ? "your turn" : "their turn"}</span>}
        <div className="life">
          {you &&
            LIFE_STEPS.slice(0, 2).map((d) => (
              <button
                key={d}
                onClick={() => send("life_change", { delta: d, player })}
              >
                {d}
              </button>
            ))}
          <span className="life-total">{state.life[player] ?? "—"}</span>
          {you &&
            LIFE_STEPS.slice(2).map((d) => (
              <button
                key={d}
                onClick={() => send("life_change", { delta: d, player })}
              >
                +{d}
              </button>
            ))}
        </div>
        <div className="piles">
          {SIDE_ZONES.map(([zone, label]) => {
            const count = state[zone].filter((c) => c.owner === player).length;
            return (
              <button
                key={zone}
                className={open === zone ? "on" : ""}
                disabled={count === 0}
                onClick={() => setOpen(open === zone ? null : zone)}
              >
                {label} {count}
              </button>
            );
          })}
        </div>
      </div>

      {open && (
        <div className="pile-open">
          {state[open]
            .filter((c) => c.owner === player)
            .map((c) => (
              <CardTile
                key={c.entry_seq}
                card={c}
                small
                selected={selected === c.entry_seq}
                onSelect={you ? onSelect : undefined}
                onPreview={onPreview}
              />
            ))}
        </div>
      )}

      <div className="battlefield">
        {battlefield.length === 0 && (
          <p className="muted empty">
            {mine
              ? "Play a card from the panel on the right →"
              : "Empty battlefield"}
          </p>
        )}
        {battlefield.map((c) => (
          <CardTile
            key={c.entry_seq}
            card={c}
            selected={selected === c.entry_seq}
            onSelect={you ? onSelect : undefined}
            onToggleTap={
              you
                ? () =>
                    send("card_tap", { entry: c.entry_seq, tapped: !c.tapped })
                : undefined
            }
            onPreview={onPreview}
          />
        ))}
      </div>
    </section>
  );
}

function CardTile({
  card,
  small,
  selected,
  onSelect,
  onToggleTap,
  onPreview,
}: {
  card: CardEntry;
  small?: boolean;
  selected: boolean;
  onSelect?: (seq: number) => void;
  onToggleTap?: () => void;
  onPreview: (card: CardEntry | null) => void;
}) {
  const counters = Object.entries(card.counters);
  return (
    <div
      className={`card ${small ? "small" : ""} ${card.tapped ? "tapped" : ""} ${selected ? "selected" : ""}`}
      title={`${card.name ?? card.card_id}${card.owner !== card.controller ? ` (owned by ${card.owner})` : ""}`}
      onClick={() => onSelect?.(card.entry_seq)}
      onDoubleClick={onToggleTap}
      onMouseEnter={() => onPreview(card)}
    >
      <img
        src={cardImage(card.card_id)}
        alt={card.name ?? ""}
        loading="lazy"
        draggable={false}
      />
      {card.token && <span className="token-tag">token</span>}
      {counters.length > 0 && (
        <div className="counters">
          {counters.map(([kind, n]) => (
            <span key={kind}>
              {n}× {kind}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
