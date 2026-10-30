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
  LogEvent,
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
import { Icon, IconName } from "./Icon";
import { Dialog, Menu } from "./Menu";
import { seatColor } from "./seats";
import { Plan } from "./matWatch";
import { Command } from "./voice";
import { VoiceControl } from "./VoiceControl";
import { RoomActions, useRoom } from "./useRoom";

const PHASES: [string, string][] = [
  ["main", "Main"],
  ["combat", "Combat"],
  ["main 2", "Main 2"],
  ["end", "End"],
];
const CAMERA_KEY = "calabria.cameraOn";
const FEED_MS = 6000;

interface FeedItem {
  id: number;
  icon?: IconName;
  text: string;
  // The event this item stands for. Undo only shows while that event is
  // still the room's latest and yours: server undo pops exactly one event.
  expect?: { type: string; name?: string | null };
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
  const [newGame, setNewGame] = useState(false);
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
  // Departure prompts only for cards still on your battlefield; forget the
  // rest, so a card that comes back later doesn't revive an old prompt.
  const leftNow = useMemo(
    () => left.filter((c) => mine.some((m) => m.entry_seq === c.entry_seq)),
    [left, mine],
  );
  useEffect(() => {
    if (leftNow.length !== left.length) setLeft(leftNow);
  }, [left, leftNow]);

  useEffect(() => {
    if (zoom && state && !findCard(state, zoom.card.entry_seq)) setZoom(null); // hovered card moved away
  }, [zoom, state]);

  // --- activity feed (every automatic action can be undone from here) ------
  const feedId = useRef(0);
  const notify = useCallback(
    (text: string, icon?: IconName, expect?: FeedItem["expect"]) => {
      const id = ++feedId.current;
      setFeed((f) => [...f.slice(-4), { id, icon, text, expect }]);
      window.setTimeout(
        () => setFeed((f) => f.filter((i) => i.id !== id)),
        FEED_MS,
      );
    },
    [],
  );

  const playCard = useCallback(
    (
      card: { card_id: string; name: string | null },
      via: IconName | null,
      opts?: PlayOptions,
    ) => {
      send("card_play", {
        card_id: card.card_id,
        name: card.name,
        zone: opts?.zone ?? "battlefield",
        token: opts?.token ?? false,
        tapped: opts?.tapped ?? false,
      });
      if (via)
        notify(`Played ${card.name ?? "a card"}`, via, {
          type: "card_play",
          name: card.name,
        });
    },
    [send, notify],
  );

  const onPlan = useCallback(
    (plan: Plan) => {
      plan.play.forEach((c) => playCard(c, "camera", { zone: "battlefield", token: false, tapped: c.tapped }));
      for (const t of plan.tap) {
        send("card_tap", t);
        const name = mine.find((m) => m.entry_seq === t.entry)?.name ?? "a card";
        notify(`${t.tapped ? "Tapped" : "Untapped"} ${name}`, "camera", {
          type: "card_tap",
        });
      }
      if (plan.arrived.length) setLeft((prev) => prev.filter((c) => !plan.arrived.includes(c.name ?? ""))); // back on the mat
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
      playCard(c, "camera");
      setCandidates(null);
    },
    [playCard],
  );

  const onCommand = useCallback(
    (cmd: Command, heard: string) => {
      switch (cmd.kind) {
        case "event":
          send(cmd.type, cmd.payload);
          notify(`“${heard.trim()}”`, "mic", { type: cmd.type });
          return;
        case "undo":
          undo();
          notify("Undone", "mic");
          return;
        case "scan":
          if (scanRef.current) scanRef.current();
          else notify("Turn the camera on to scan", "mic");
          return;
        case "pick":
          if (candidates?.[cmd.index]) pick(candidates[cmd.index]);
          return;
        case "play":
          api
            .search(cmd.query)
            .then(({ results }) =>
              results[0]
                ? playCard(results[0], "mic")
                : notify(`No card called “${cmd.query}”`, "mic"),
            )
            .catch(() => notify("Search failed", "mic"));
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
        <div className="bar-left">
          <img className="sigil" src="/sigil.png" alt="" />
          <button
            className="room-code"
            data-tip={copied ? undefined : "Copy invite link"}
            onClick={invite}
          >
            <span
              className={`conn ${status}`}
              title={status === "open" ? "Connected" : "Reconnecting…"}
            />
            <span>{copied ? "Copied" : code}</span>
            <Icon name={copied ? "check" : "link"} size={14} />
          </button>
        </div>

        <div className="bar-center">
          <div className={`turn-pill ${yourTurn ? "yours" : ""}`}>
            <span className="turn-no">Turn {state.turn.number}</span>
            <span
              className="turn-who"
              style={
                yourTurn
                  ? undefined
                  : { color: seatColor(state.players, state.turn.player) }
              }
            >
              {yourTurn ? "Your turn" : `${state.turn.player ?? "—"}'s turn`}
            </span>
          </div>
          <nav className="phases" aria-label="Phase">
            {PHASES.map(([p, label]) => (
              <button
                key={p}
                aria-pressed={state.phase === p}
                disabled={!you}
                onClick={() => send("phase_set", { phase: p })}
              >
                {label}
              </button>
            ))}
          </nav>
          {state.last_roll && (
            <span className="roll" title={`Last roll: d${state.last_roll.sides}`}>
              <Icon name="dice" size={15} />
              <span
                style={{ color: seatColor(state.players, state.last_roll.player) }}
              >
                {state.last_roll.player}
              </span>
              <strong>{state.last_roll.result}</strong>
              <span className="muted">d{state.last_roll.sides}</span>
            </span>
          )}
        </div>

        <div className="bar-right">
          {you && (
            <>
              <VoiceControl
                ctx={{ you, players: state.players }}
                onCommand={onCommand}
              />
              <span className="bar-sep" />
              <button
                className="icon-btn"
                aria-label="Undo"
                data-tip="Undo · Ctrl+Z"
                onClick={undo}
              >
                <Icon name="undo" />
              </button>
              <button
                className="icon-btn"
                aria-label="Untap all"
                data-tip="Untap all"
                onClick={() => send("untap_all")}
              >
                <Icon name="untap" />
              </button>
            </>
          )}
          <Menu
            label="More"
            items={[
              ...(you
                ? [
                    {
                      label: "Roll a d20",
                      icon: "dice" as const,
                      onSelect: () => send("dice_roll", { sides: 20 }),
                    },
                    {
                      label: "Roll a d6",
                      icon: "dice" as const,
                      onSelect: () => send("dice_roll", { sides: 6 }),
                    },
                    {
                      label: "New game…",
                      icon: "shuffle" as const,
                      onSelect: () => setNewGame(true),
                    },
                  ]
                : []),
              { label: "Leave table", icon: "leave", onSelect: onLeave },
            ]}
          />
          {you && (
            <button
              className="end-turn primary"
              onClick={() => send("turn_end")}
              title="Pass the turn (or say “end turn”)"
            >
              End turn <Icon name="arrowRight" size={16} />
            </button>
          )}
        </div>
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
                <section className="dock-section">
                  <div className="cam-frame off">
                    <Icon name="camera" size={26} />
                    <strong>Play hands-free</strong>
                    <p>
                      Point your webcam at your mat. Cards you lay down, tap
                      and take away are tracked for you.
                    </p>
                    <button onClick={() => setCamera(true)}>
                      Turn on mat camera
                    </button>
                  </div>
                </section>
              )}
              <AddCard onPlay={(card, opts) => playCard(card, null, opts)} />
            </>
          ) : (
            <section className="dock-section">
              <p className="muted small">
                You're watching. Join from the lobby to take a seat.
              </p>
            </section>
          )}
          <Log log={view.log} state={state} />
        </aside>
      </main>

      {feed.length > 0 && (
        <div className="feed">
          {feed.map((item, i) => (
            <div key={item.id} className="feed-item">
              {item.icon && <Icon name={item.icon} size={15} />}
              <span>{item.text}</span>
              {i === feed.length - 1 && canUndo(item, view.log, you) && (
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

      {newGame && you && (
        <NewGame
          players={state.players}
          send={send}
          onClose={() => setNewGame(false)}
        />
      )}
      {zoom && <Zoom {...zoom} />}
      {error && (
        <div className="toast" onClick={clearError}>
          {error}
        </div>
      )}
    </div>
  );
}

/** Undo pops the room's latest event, so offer it only while that event is this item's. */
function canUndo(item: FeedItem, log: LogEvent[], you: string | null): boolean {
  const last = log[log.length - 1];
  if (!item.expect || !last || last.actor !== you || last.type !== item.expect.type) return false;
  return item.expect.name === undefined || last.payload.name === item.expect.name;
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

const ZONE_LABEL: Record<Zone, string> = {
  battlefield: "On the battlefield",
  graveyard: "In the graveyard",
  exile: "In exile",
  command: "In the command zone",
};

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
  const kinds = [
    ...COUNTERS,
    ...Object.keys(card.counters).filter((k) => !COUNTERS.includes(k)),
  ];
  const others = players.filter((p) => p !== card.controller);
  return (
    <div className="selected-bar">
      <img
        className="sel-thumb"
        src={cardImage(card.card_id, "small")}
        alt=""
      />
      <div className="sel-body">
        <div className="sel-title">
          <strong>{card.name ?? card.card_id}</strong>
          <span className="muted small">{ZONE_LABEL[card.zone]}</span>
          <button
            className="icon-btn sel-close"
            aria-label="Deselect"
            data-tip="Deselect · Esc"
            onClick={onClose}
          >
            <Icon name="x" size={16} />
          </button>
        </div>
        <div className="sel-row">
          {card.zone === "battlefield" && (
            <button
              onClick={() => send("card_tap", { entry, tapped: !card.tapped })}
            >
              <Icon name={card.tapped ? "untap" : "tap"} size={15} />
              {card.tapped ? "Untap" : "Tap"} <kbd>T</kbd>
            </button>
          )}
          <span className="group">
            <span className="group-label">Move to</span>
            {MOVES.filter(([zone]) => zone !== card.zone).map(
              ([zone, label, key]) => (
                <button
                  key={zone}
                  className="chip"
                  onClick={() => send("card_move", { entry, zone })}
                >
                  {label} <kbd>{key}</kbd>
                </button>
              ),
            )}
          </span>
        </div>
        <div className="sel-row">
          <span className="group">
            <span className="group-label">Counters</span>
            {kinds.map((kind) => (
              <span key={kind} className="counter-ctl">
                <button
                  aria-label={`Remove ${kind}`}
                  disabled={!card.counters[kind]}
                  onClick={() =>
                    send("card_counter", { entry, kind, delta: -1 })
                  }
                >
                  <Icon name="minus" size={13} />
                </button>
                <span>
                  {kind} <b>{card.counters[kind] ?? 0}</b>
                </span>
                <button
                  aria-label={`Add ${kind}`}
                  onClick={() => send("card_counter", { entry, kind, delta: 1 })}
                >
                  <Icon name="plus" size={13} />
                </button>
              </span>
            ))}
            <form
              className="counter-new"
              onSubmit={(e) => {
                e.preventDefault();
                if (!custom.trim()) return;
                send("card_counter", { entry, kind: custom.trim(), delta: 1 });
                setCustom("");
              }}
            >
              <input
                placeholder="New counter…"
                aria-label="New counter kind"
                value={custom}
                onChange={(e) => setCustom(e.currentTarget.value)}
              />
            </form>
          </span>
          {card.zone === "battlefield" && others.length > 0 && (
            <span className="group">
              <span className="group-label">Give to</span>
              {others.map((p) => (
                <button
                  key={p}
                  className="chip"
                  onClick={() => send("card_control", { entry, player: p })}
                >
                  {p}
                </button>
              ))}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function NewGame({
  players,
  send,
  onClose,
}: {
  players: string[];
  send: RoomActions["send"];
  onClose: () => void;
}) {
  const [life, setLife] = useState(20);
  const [first, setFirst] = useState(players[0] ?? "");
  return (
    <Dialog title="New game" onClose={onClose}>
      <p className="muted">
        Clears every battlefield and pile, and resets life totals.
      </p>
      <div className="field">
        <span>Starting life</span>
        <div className="segmented">
          {[20, 30, 40].map((n) => (
            <button key={n} aria-pressed={life === n} onClick={() => setLife(n)}>
              {n}
            </button>
          ))}
        </div>
      </div>
      <div className="field">
        <span>Who starts</span>
        <div className="segmented">
          {players.map((p) => (
            <button key={p} aria-pressed={first === p} onClick={() => setFirst(p)}>
              {p}
            </button>
          ))}
        </div>
      </div>
      <div className="dialog-actions">
        <button className="ghost" onClick={onClose}>
          Cancel
        </button>
        <button
          className="danger"
          onClick={() => {
            send("game_reset", { starting_life: life, first: first || players[0] });
            onClose();
          }}
        >
          Wipe the table &amp; start
        </button>
      </div>
    </Dialog>
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
