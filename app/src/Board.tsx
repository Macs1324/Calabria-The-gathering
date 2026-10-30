import { CSSProperties, MouseEvent, useEffect, useState } from "react";
import { CardEntry, GameState, Zone, cardImage } from "./api";
import { Icon } from "./Icon";
import { seatColor } from "./seats";
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
  const seat = { "--seat": seatColor(state.players, player) } as CSSProperties;

  return (
    <section
      className={`board ${mine ? "mine" : "theirs"} ${active ? "active" : ""}`}
      style={seat}
    >
      <header className="board-head">
        <span className="avatar">
          {player.slice(0, 1).toUpperCase()}
          <span
            className={`presence ${online ? "on" : ""}`}
            title={online ? "online" : "offline"}
          />
        </span>
        <div className="who">
          <h3>
            {player}
            {mine && <span className="you-tag">you</span>}
          </h3>
          <span className="status">
            {active
              ? mine
                ? "Your turn"
                : "Taking their turn"
              : online
                ? "Online"
                : "Offline"}
          </span>
        </div>

        <div className="piles">
          {SIDE_ZONES.map(([zone, label]) => {
            const cards = state[zone].filter((c) => c.owner === player);
            const top = cards[cards.length - 1];
            return (
              <button
                key={zone}
                className={`pile ${open === zone ? "on" : ""}`}
                disabled={cards.length === 0}
                aria-label={`${label}: ${cards.length}`}
                onClick={() => setOpen(open === zone ? null : zone)}
              >
                <span className="pile-face">
                  {top && (
                    <img src={cardImage(top.card_id, "small")} alt="" />
                  )}
                  {cards.length > 0 && <b>{cards.length}</b>}
                </span>
                <span className="pile-label">{label}</span>
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
              aria-label={`${player} loses 1 life`}
              onClick={(e) =>
                send("life_change", { delta: e.shiftKey ? -5 : -1, player })
              }
              title="−1 (shift-click: −5)"
            >
              <Icon name="minus" size={16} />
            </button>
          )}
          <span className="life-total">{lifeTotal ?? "—"}</span>
          {you && (
            <button
              className="life-btn"
              aria-label={`${player} gains 1 life`}
              onClick={(e) =>
                send("life_change", { delta: e.shiftKey ? 5 : 1, player })
              }
              title="+1 (shift-click: +5)"
            >
              <Icon name="plus" size={16} />
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
        {battlefield.length === 0 &&
          (mine ? (
            <div className="empty">
              <span className="ghost-card" />
              <p>
                Lay a card on your mat, say <q>play Sol Ring</q>, or search for
                it on the right.
              </p>
            </div>
          ) : (
            <p className="empty muted">No permanents</p>
          ))}
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
              {kind} <b>×{n}</b>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
