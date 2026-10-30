import {
  MouseEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { AddCard, PlayOptions } from "./AddCard";
import {
  CardEntry,
  GameState,
  MoveTarget,
  PUBLIC_ZONES,
  ScanCandidate,
  Seat,
  Zone,
  api,
  cardImage,
  storageGet,
  storageSet,
} from "./api";
import { Board } from "./Board";
import { ConfirmTray } from "./ConfirmTray";
import { Log } from "./Log";
import { MatCamera } from "./MatCamera";
import { Plan } from "./matWatch";
import { Command } from "./voice";
import { VoiceControl } from "./VoiceControl";
import { RoomActions, useRoom } from "./useRoom";

const PHASES = ["main", "combat", "main 2", "end"];
const CAMERA_KEY = "calabria.cameraOn";
const FEED_MS = 6000;

interface FeedItem {
  id: number;
  text: string;
  undoable: boolean;
}

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
  const [zoom, setZoom] = useState<{
    card: CardEntry;
    x: number;
    y: number;
  } | null>(null);
  const [copied, setCopied] = useState(false);
  const [camera, setCamera] = useState(() => storageGet(CAMERA_KEY) === "on");
  const [candidates, setCandidates] = useState<ScanCandidate[] | null>(null);
  const [left, setLeft] = useState<CardEntry[]>([]);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const scanRef = useRef<(() => void) | null>(null);

  const you = view?.you ?? null;
  const state = view?.state;

  useEffect(() => {
    if (view && seat && view.you === null) onSeatRejected();
  }, [view, seat, onSeatRejected]);

  useEffect(() => {
    if (!error) return;
    const t = window.setTimeout(clearError, 4500);
    return () => window.clearTimeout(t);
  }, [error, clearError]);

  useEffect(() => storageSet(CAMERA_KEY, camera ? "on" : "off"), [camera]);

  const selectedCard = useMemo(
    () => (state && selected !== null ? findCard(state, selected) : null),
    [state, selected],
  );
  useEffect(() => {
    if (state && selected !== null && !findCard(state, selected))
      setSelected(null); // it left public view
  }, [state, selected]);

  const mine = useMemo(
    () =>
      state && you ? state.battlefield.filter((c) => c.controller === you) : [],
    [state, you],
  );
  // Departure prompts only for cards still on your battlefield.
  const leftNow = useMemo(
    () => left.filter((c) => mine.some((m) => m.entry_seq === c.entry_seq)),
    [left, mine],
  );

  // --- activity feed (every automatic action can be undone from here) ------
  const feedId = useRef(0);
  const notify = useCallback((text: string, undoable = true) => {
    const id = ++feedId.current;
    setFeed((f) => [...f.slice(-4), { id, text, undoable }]);
    window.setTimeout(
      () => setFeed((f) => f.filter((i) => i.id !== id)),
      FEED_MS,
    );
  }, []);

  const playCard = useCallback(
    (
      card: { card_id: string; name: string | null },
      via: string,
      opts?: PlayOptions,
    ) => {
      send("card_play", {
        card_id: card.card_id,
        name: card.name,
        zone: opts?.zone ?? "battlefield",
        token: opts?.token ?? false,
        tapped: opts?.tapped ?? false,
      });
      if (via) notify(`${via} Played ${card.name ?? "a card"}`);
    },
    [send, notify],
  );

  const onPlan = useCallback(
    (plan: Plan) => {
      plan.play.forEach((c) => playCard(c, "📷"));
      for (const t of plan.tap) {
        send("card_tap", t);
        const name =
          mine.find((m) => m.entry_seq === t.entry)?.name ?? "a card";
        notify(`📷 ${t.tapped ? "Tapped" : "Untapped"} ${name}`);
      }
      if (plan.left.length) {
        setLeft((prev) => [
          ...prev,
          ...plan.left.filter(
            (c) => !prev.some((p) => p.entry_seq === c.entry_seq),
          ),
        ]);
      }
      if (plan.unsure) setCandidates(plan.unsure.candidates);
    },
    [playCard, send, notify, mine],
  );

  const pick = useCallback(
    (c: ScanCandidate) => {
      playCard(c, "📷");
      setCandidates(null);
    },
    [playCard],
  );

  const onCommand = useCallback(
    (cmd: Command, heard: string) => {
      switch (cmd.kind) {
        case "event":
          send(cmd.type, cmd.payload);
          notify(`🎙 “${heard.trim()}”`);
          return;
        case "undo":
          undo();
          notify("🎙 Undone", false);
          return;
        case "scan":
          if (scanRef.current) scanRef.current();
          else notify("🎙 Turn the camera on to scan", false);
          return;
        case "pick":
          if (candidates?.[cmd.index]) pick(candidates[cmd.index]);
          return;
        case "play":
          api
            .search(cmd.query)
            .then(({ results }) =>
              results[0]
                ? playCard(results[0], "🎙")
                : notify(`🎙 No card called “${cmd.query}”`, false),
            )
            .catch(() => notify("🎙 Search failed", false));
      }
    },
    [send, undo, notify, candidates, pick, playCard],
  );

  useShortcuts(you !== null, selectedCard, { send, undo }, () =>
    setSelected(null),
  );

  const onPreview = useCallback((card: CardEntry | null, e?: MouseEvent) => {
    setZoom(card && e ? { card, x: e.clientX, y: e.clientY } : null);
  }, []);

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
          {copied ? "Link copied" : code}
        </button>
        <span
          className={`conn ${status}`}
          title={status === "open" ? "Connected" : "Reconnecting…"}
        />

        <div className={`turn-pill ${yourTurn ? "yours" : ""}`}>
          <span className="turn-no">T{state.turn.number}</span>
          <span>
            {yourTurn ? "Your turn" : `${state.turn.player ?? "—"}'s turn`}
          </span>
        </div>
        {you && (
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
        )}
        {state.last_roll && (
          <span className="roll">
            🎲 {state.last_roll.player}:{" "}
            <strong>{state.last_roll.result}</strong>
            <span className="muted"> /d{state.last_roll.sides}</span>
          </span>
        )}

        <div className="spacer" />

        {you && (
          <>
            <VoiceControl
              ctx={{ you, players: state.players }}
              onCommand={onCommand}
            />
            <div className="tool-group">
              <button
                onClick={undo}
                title="Undo your last action (Ctrl+Z, or say “undo”)"
              >
                ↶ Undo
              </button>
              <button
                onClick={() => send("untap_all")}
                title="Untap your permanents"
              >
                ⟳ Untap
              </button>
              <button
                onClick={() => send("dice_roll", { sides: 20 })}
                title="Roll a d20"
              >
                d20
              </button>
              <button
                onClick={() => send("dice_roll", { sides: 6 })}
                title="Roll a d6"
              >
                d6
              </button>
            </div>
            <NewGame players={state.players} send={send} />
          </>
        )}
        <button className="ghost" onClick={onLeave}>
          Leave
        </button>
        {you && (
          <button
            className="end-turn primary"
            onClick={() => send("turn_end")}
            title="Pass the turn (or say “end turn”)"
          >
            End turn ➜
          </button>
        )}
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
              onPreview={onPreview}
              send={send}
            />
          ))}
          {state.players.length === 0 && (
            <p className="muted">Nobody seated yet.</p>
          )}
        </div>

        <aside className="sidebar">
          {you ? (
            <>
              {camera ? (
                <MatCamera
                  mine={mine}
                  onPlan={onPlan}
                  onCandidates={setCandidates}
                  scanRef={scanRef}
                  onClose={() => setCamera(false)}
                />
              ) : (
                <section className="panel go-hands-free">
                  <h4>Play hands-free</h4>
                  <p className="muted small">
                    Point your webcam at your mat: cards you lay down, tap and
                    take away are tracked for you.
                  </p>
                  <button className="primary" onClick={() => setCamera(true)}>
                    📷 Turn on mat camera
                  </button>
                </section>
              )}
              <AddCard onPlay={(card, opts) => playCard(card, "", opts)} />
            </>
          ) : (
            <p className="muted panel small">
              Watching. Join from the lobby to play.
            </p>
          )}
          <Log log={view.log} state={state} />
        </aside>
      </main>

      {feed.length > 0 && (
        <div className="feed">
          {feed.map((item, i) => (
            <div key={item.id} className="feed-item">
              <span>{item.text}</span>
              {item.undoable && i === feed.length - 1 && (
                <button
                  className="ghost"
                  onClick={() => {
                    undo();
                    setFeed((f) => f.filter((x) => x.id !== item.id));
                  }}
                >
                  Undo
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="bottom-dock">
        {you && (
          <ConfirmTray
            candidates={candidates}
            left={leftNow}
            onPick={pick}
            onDismissCandidates={() => setCandidates(null)}
            onMove={(card, zone) => {
              send("card_move", { entry: card.entry_seq, zone });
              setLeft((l) => l.filter((c) => c.entry_seq !== card.entry_seq));
            }}
            onKeep={(card) =>
              setLeft((l) => l.filter((c) => c.entry_seq !== card.entry_seq))
            }
          />
        )}
        {selectedCard && you && (
          <SelectedBar
            card={selectedCard}
            players={state.players}
            send={send}
            onClose={() => setSelected(null)}
          />
        )}
      </div>

      {zoom && <Zoom {...zoom} />}
      {error && (
        <div className="toast" onClick={clearError}>
          {error}
        </div>
      )}
    </div>
  );
}

/** Big card image next to the pointer, on the side with more room. */
function Zoom({ card, x, y }: { card: CardEntry; x: number; y: number }) {
  const W = 280;
  const H = W * (88 / 63);
  const left = x > window.innerWidth / 2 ? x - W - 24 : x + 24;
  const top = Math.min(Math.max(12, y - H / 2), window.innerHeight - H - 12);
  return (
    <img
      className="zoom"
      src={cardImage(card.card_id)}
      alt={card.name ?? ""}
      style={{ left, top, width: W }}
    />
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
  if (!open)
    return (
      <button className="ghost" onClick={() => setOpen(true)}>
        New game…
      </button>
    );
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
