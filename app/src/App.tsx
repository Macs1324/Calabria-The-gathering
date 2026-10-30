import { useCallback, useEffect, useState } from "react";
import "./App.css";
import {
  ApiError,
  Seat,
  api,
  forgetSeat,
  loadSeat,
  rememberName,
  rememberedName,
  saveSeat,
} from "./api";
import { Lobby } from "./Lobby";
import { Table } from "./Table";

// Rooms live in the hash (#/K7QX) so the server's API paths never clash with
// client routes, and an invite is just the page URL.
function useHashRoom(): [string | null, (code: string | null) => void] {
  const read = () => {
    const code = location.hash.replace(/^#\/?/, "").trim().toUpperCase();
    return code || null;
  };
  const [room, setRoom] = useState(read);
  useEffect(() => {
    const onHash = () => setRoom(read());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const go = useCallback((code: string | null) => {
    location.hash = code ? `/${code.toUpperCase()}` : "";
  }, []);
  return [room, go];
}

export default function App() {
  const [room, go] = useHashRoom();
  return room ? (
    <RoomGate key={room} code={room} onLeave={() => go(null)} />
  ) : (
    <Lobby onEnter={go} />
  );
}

type Gate =
  | { step: "checking" }
  | { step: "missing" }
  | { step: "join"; error?: string }
  | { step: "seated"; seat: Seat | null };

/** Make sure the room exists and we have a seat (or chose to watch). */
function RoomGate({ code, onLeave }: { code: string; onLeave: () => void }) {
  const [gate, setGate] = useState<Gate>({ step: "checking" });
  const [name, setName] = useState(rememberedName);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    api
      .roomState(code)
      .then(() => {
        if (!live) return;
        const seat = loadSeat(code);
        setGate(seat ? { step: "seated", seat } : { step: "join" });
      })
      .catch((e) => {
        if (!live) return;
        setGate(
          e instanceof ApiError && e.status === 404
            ? { step: "missing" }
            : { step: "join", error: String(e.message ?? e) },
        );
      });
    return () => {
      live = false;
    };
  }, [code]);

  const join = async () => {
    setBusy(true);
    try {
      const res = await api.join(code, name);
      const seat = { name: res.name, token: res.token };
      saveSeat(code, seat);
      rememberName(res.name);
      setGate({ step: "seated", seat });
    } catch (e) {
      setGate({
        step: "join",
        error: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setBusy(false);
    }
  };

  if (gate.step === "seated") {
    return (
      <Table
        code={code}
        seat={gate.seat}
        onLeave={onLeave}
        onSeatRejected={() => {
          forgetSeat(code);
          setGate({
            step: "join",
            error: "Your seat in this room was not recognised — join again.",
          });
        }}
      />
    );
  }

  return (
    <main className="lobby">
      <img className="logo" src="/logo.png" alt="Calabria: The Gathering" />
      <section className="panel">
        {gate.step === "checking" && (
          <p className="muted">Looking for room {code}…</p>
        )}
        {gate.step === "missing" && (
          <>
            <h2>No room called {code}</h2>
            <p className="muted">Check the code, or create a new room.</p>
            <button onClick={onLeave}>Back to the lobby</button>
          </>
        )}
        {gate.step === "join" && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              join();
            }}
          >
            <h2>
              Join room <span className="code">{code}</span>
            </h2>
            <label>
              Your name
              <input
                autoFocus
                value={name}
                maxLength={24}
                onChange={(e) => setName(e.currentTarget.value)}
              />
            </label>
            {gate.error && <p className="error">{gate.error}</p>}
            <div className="gate-actions">
              <button
                className="primary"
                type="submit"
                disabled={busy || !name.trim()}
              >
                Take a seat
              </button>
              <button
                type="button"
                onClick={() => setGate({ step: "seated", seat: null })}
              >
                Just watch
              </button>
              <button type="button" className="ghost" onClick={onLeave}>
                Back
              </button>
            </div>
          </form>
        )}
      </section>
    </main>
  );
}
