import { MouseEvent, useEffect, useState } from "react";
import { CardEntry, GameState, Zone, cardImage } from "./api";
import { RoomActions } from "./useRoom";

const SIDE_ZONES: [Zone, string][] = [
  ["graveyard", "Graveyard"],
  ["exile", "Exile"],
  ["command", "Command"],
];

export type PreviewHandler = (card: CardEntry | null, e?: MouseEvent) => void;

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
  onPreview: PreviewHandler;
  send: RoomActions["send"];
}) {
  const [picked, setOpen] = useState<Zone | null>(null);
  const mine = player === you;
  // A pile that emptied closes itself (its button is disabled at 0)…
  const open =
    picked && state[picked].some((c) => c.owner === player) ? picked : null;
  useEffect(() => {
    if (picked && !open) setOpen(null); // …and stays closed when refilled
  }, [picked, open]);

  const battlefield = state.battlefield.filter((c) => c.controller === player);
  const active = state.turn.player === player;
  const lifeTotal = state.life[player];

  return (
    <section
      className={`board ${mine ? "mine" : "theirs"} ${active ? "active" : ""}`}
    >
      <header className="board-head">
        <span
          className={`avatar ${online ? "on" : ""}`}
          title={online ? "online" : "offline"}
        >
          {player.slice(0, 1).toUpperCase()}
        </span>
        <div className="who">
          <h3>{mine ? `${player} · you` : player}</h3>
          <span className="muted small">
            {active
              ? mine
                ? "your turn"
                : "their turn"
              : online
                ? "online"
                : "offline"}
          </span>
        </div>

        <div className="piles">
          {SIDE_ZONES.map(([zone, label]) => {
            const count = state[zone].filter((c) => c.owner === player).length;
            return (
              <button
                key={zone}
                className={`pile ${open === zone ? "on" : ""}`}
                disabled={count === 0}
                onClick={() => setOpen(open === zone ? null : zone)}
              >
                {label} <b>{count}</b>
              </button>
            );
          })}
        </div>

        <div
          className={`life ${lifeTotal !== undefined && lifeTotal <= 5 ? "low" : ""}`}
        >
          {you && (
            <button
              className="life-btn"
              onClick={(e) =>
                send("life_change", { delta: e.shiftKey ? -5 : -1, player })
              }
              title="−1 (shift-click: −5)"
            >
              −
            </button>
          )}
          <span className="life-total">{lifeTotal ?? "—"}</span>
          {you && (
            <button
              className="life-btn"
              onClick={(e) =>
                send("life_change", { delta: e.shiftKey ? 5 : 1, player })
              }
              title="+1 (shift-click: +5)"
            >
              +
            </button>
          )}
        </div>
      </header>

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
          <p className="empty muted">
            {mine
              ? "Lay a card on your mat, say “play Sol Ring”, or type a name →"
              : "Nothing in play yet"}
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
  onPreview: PreviewHandler;
}) {
  const counters = Object.entries(card.counters);
  return (
    <div
      className={`card ${small ? "small" : ""} ${card.tapped ? "tapped" : ""} ${selected ? "selected" : ""}`}
      onClick={(e) => {
        if (e.detail > 1) return; // second click of a double-click taps, not deselects
        onSelect?.(card.entry_seq);
      }}
      onDoubleClick={onToggleTap}
      onMouseEnter={(e) => onPreview(card, e)}
      onMouseMove={(e) => onPreview(card, e)}
      onMouseLeave={() => onPreview(null)}
    >
      <img
        src={cardImage(card.card_id)}
        alt={card.name ?? ""}
        loading="lazy"
        draggable={false}
      />
      {card.token && <span className="token-tag">token</span>}
      {card.owner !== card.controller && (
        <span className="token-tag stolen">{card.owner}'s</span>
      )}
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
