import { useEffect, useMemo, useState } from "react";
import { AddCard } from "./AddCard";
import {
  CardEntry,
  GameState,
  MoveTarget,
  PUBLIC_ZONES,
  Seat,
  Zone,
  cardImage,
} from "./api";
import { Board } from "./Board";
import { Log } from "./Log";
import { RoomActions, useRoom } from "./useRoom";

const PHASES = ["main", "combat", "main 2", "end"];
const DICE = [6, 20];

export function Table({
  code,
  seat,
  onLeave,
  onSeatRejected,
}: {
  code: string;
  seat: Seat | null;
  onLeave: () => void;
  onSeatRejected: () => void;
}) {
  const { view, status, error, clearError, send, undo } = useRoom(
    code,
    seat?.token ?? null,
  );
  const [selected, setSelected] = useState<number | null>(null);
  const [preview, setPreview] = useState<CardEntry | null>(null);
  const [copied, setCopied] = useState(false);

  const you = view?.you ?? null;
  useEffect(() => {
    if (view && seat && view.you === null) onSeatRejected();
  }, [view, seat, onSeatRejected]);

  useEffect(() => {
    if (!error) return;
    const t = window.setTimeout(clearError, 4500);
    return () => window.clearTimeout(t);
  }, [error, clearError]);

  const state = view?.state;
  const selectedCard = useMemo(
    () => (state && selected !== null ? findCard(state, selected) : null),
    [state, selected],
  );
  useEffect(() => {
    if (state && selected !== null && !findCard(state, selected))
      setSelected(null); // it left public view
  }, [state, selected]);

  useShortcuts(you !== null, selectedCard, { send, undo }, () =>
    setSelected(null),
  );

  if (!view || !state) {
    return (
      <main className="lobby">
        <p className="muted">Connecting to room {code}…</p>
      </main>
    );
  }

  const order = you
    ? [...state.players.filter((p) => p !== you), you]
    : state.players;
  const yourTurn = you !== null && state.turn.player === you;

  const invite = async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked: the code is on screen anyway */
    }
  };

  return (
    <div className="table">
      <header className="topbar">
        <img className="sigil" src="/sigil.png" alt="" />
        <button className="room-code" title="Copy invite link" onClick={invite}>
          {copied ? "Link copied!" : code}
        </button>
        <span
          className={`conn ${status}`}
          title={status === "open" ? "Connected" : "Reconnecting…"}
        />
        <div className="turn">
          Turn {state.turn.number} ·{" "}
          <strong>
            {state.turn.player === you
              ? "your turn"
              : `${state.turn.player ?? "—"}'s turn`}
          </strong>
        </div>
        {you && (
          <>
            <div className="phases">
              {PHASES.map((p) => (
                <button
                  key={p}
                  className={state.phase === p ? "on" : ""}
                  onClick={() => send("phase_set", { phase: p })}
                >
                  {p}
                </button>
              ))}
            </div>
            <button
              className={yourTurn ? "primary" : ""}
              onClick={() => send("turn_end")}
              title="Passes the turn and untaps the next player"
            >
              End turn
            </button>
            <button onClick={() => send("untap_all")}>Untap all</button>
            <button onClick={undo} title="Undo your last action (Ctrl+Z)">
              Undo
            </button>
            {DICE.map((sides) => (
              <button key={sides} onClick={() => send("dice_roll", { sides })}>
                d{sides}
              </button>
            ))}
            {state.last_roll && (
              <span className="roll">
                {state.last_roll.player} rolled{" "}
                <strong>{state.last_roll.result}</strong> (d
                {state.last_roll.sides})
              </span>
            )}
          </>
        )}
        <div className="spacer" />
        {you && <NewGame players={state.players} send={send} />}
        <button className="ghost" onClick={onLeave}>
          Leave
        </button>
      </header>

      <main className="play">
        <div className="boards">
          {order.map((player) => (
            <Board
              key={player}
              player={player}
              state={state}
              you={you}
              online={view.online.includes(player)}
              selected={selected}
              onSelect={(seq) => setSelected(seq === selected ? null : seq)}
              onPreview={setPreview}
              send={send}
            />
          ))}
          {state.players.length === 0 && (
            <p className="muted">Nobody seated yet.</p>
          )}
        </div>

        <aside className="sidebar">
          <div className="preview">
            {preview ? (
              <img src={cardImage(preview.card_id)} alt={preview.name ?? ""} />
            ) : (
              <p className="muted">Hover a card to see it up close.</p>
            )}
          </div>
          {you ? (
            <AddCard send={send} />
          ) : (
            <p className="muted panel small">
              Watching. Join from the lobby to play.
            </p>
          )}
          <Log log={view.log} state={state} />
        </aside>
      </main>

      {selectedCard && you && (
        <SelectedBar
          card={selectedCard}
          players={state.players}
          send={send}
          onClose={() => setSelected(null)}
        />
      )}
      {error && (
        <div className="toast" onClick={clearError}>
          {error}
        </div>
      )}
    </div>
  );
}

export function findCard(
  state: GameState,
  seq: number,
): (CardEntry & { zone: Zone }) | null {
  for (const zone of PUBLIC_ZONES) {
    const card = state[zone].find((c) => c.entry_seq === seq);
    if (card) return { ...card, zone };
  }
  return null;
}

const MOVES: [MoveTarget, string, string][] = [
  ["battlefield", "Battlefield", "B"],
  ["graveyard", "Graveyard", "G"],
  ["exile", "Exile", "E"],
  ["command", "Command", "C"],
  ["hand", "Hand", "H"],
  ["library", "Library", "L"],
];
const COUNTERS = ["+1/+1", "-1/-1", "loyalty"];

function SelectedBar({
  card,
  players,
  send,
  onClose,
}: {
  card: CardEntry & { zone: Zone };
  players: string[];
  send: RoomActions["send"];
  onClose: () => void;
}) {
  const [custom, setCustom] = useState("");
  const entry = card.entry_seq;
  return (
    <div className="selected-bar">
      <strong className="selected-name">{card.name ?? card.card_id}</strong>
      {card.zone === "battlefield" && (
        <button
          onClick={() => send("card_tap", { entry, tapped: !card.tapped })}
        >
          {card.tapped ? "Untap" : "Tap"} <kbd>T</kbd>
        </button>
      )}
      <span className="group">
        {MOVES.filter(([zone]) => zone !== card.zone).map(
          ([zone, label, key]) => (
            <button
              key={zone}
              onClick={() => send("card_move", { entry, zone })}
            >
              → {label} <kbd>{key}</kbd>
            </button>
          ),
        )}
      </span>
      <span className="group">
        {COUNTERS.map((kind) => (
          <span key={kind} className="counter-ctl">
            <button
              onClick={() => send("card_counter", { entry, kind, delta: -1 })}
            >
              −
            </button>
            <span>{kind}</span>
            <button
              onClick={() => send("card_counter", { entry, kind, delta: 1 })}
            >
              +
            </button>
          </span>
        ))}
        <form
          className="counter-ctl"
          onSubmit={(e) => {
            e.preventDefault();
            if (custom.trim())
              send("card_counter", { entry, kind: custom.trim(), delta: 1 });
          }}
        >
          <input
            placeholder="other counter"
            value={custom}
            onChange={(e) => setCustom(e.currentTarget.value)}
          />
          <button type="submit">+</button>
        </form>
      </span>
      {card.zone === "battlefield" && (
        <span className="group">
          {players
            .filter((p) => p !== card.controller)
            .map((p) => (
              <button
                key={p}
                onClick={() => send("card_control", { entry, player: p })}
              >
                Give to {p}
              </button>
            ))}
        </span>
      )}
      <button className="ghost" onClick={onClose} title="Esc">
        ✕
      </button>
    </div>
  );
}

function NewGame({
  players,
  send,
}: {
  players: string[];
  send: RoomActions["send"];
}) {
  const [open, setOpen] = useState(false);
  const [life, setLife] = useState(20);
  const [first, setFirst] = useState(players[0] ?? "");
  if (!open) return <button onClick={() => setOpen(true)}>New game…</button>;
  return (
    <span className="new-game">
      <select
        value={life}
        onChange={(e) => setLife(Number(e.currentTarget.value))}
      >
        <option value={20}>20 life</option>
        <option value={30}>30 life</option>
        <option value={40}>40 life</option>
      </select>
      <select value={first} onChange={(e) => setFirst(e.currentTarget.value)}>
        {players.map((p) => (
          <option key={p} value={p}>
            {p} starts
          </option>
        ))}
      </select>
      <button
        className="danger"
        onClick={() => {
          send("game_reset", {
            starting_life: life,
            first: first || players[0],
          });
          setOpen(false);
        }}
      >
        Wipe board &amp; start
      </button>
      <button className="ghost" onClick={() => setOpen(false)}>
        Cancel
      </button>
    </span>
  );
}

function useShortcuts(
  seated: boolean,
  card: (CardEntry & { zone: Zone }) | null,
  { send, undo }: RoomActions,
  deselect: () => void,
) {
  useEffect(() => {
    if (!seated) return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.closest("input, textarea, select")) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        undo();
        return;
      }
      if (e.key === "Escape") return deselect();
      if (!card || e.ctrlKey || e.metaKey || e.altKey) return;
      const key = e.key.toUpperCase();
      if (key === "T" && card.zone === "battlefield")
        send("card_tap", { entry: card.entry_seq, tapped: !card.tapped });
      const move = MOVES.find(([zone, , k]) => k === key && zone !== card.zone);
      if (move) send("card_move", { entry: card.entry_seq, zone: move[0] });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [seated, card, send, undo, deselect]);
}
