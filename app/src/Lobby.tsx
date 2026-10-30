import { useState } from "react";
import {
  api,
  isHttpOrigin,
  rememberName,
  rememberedName,
  saveSeat,
  serverBase,
  setServerBase,
} from "./api";

export function Lobby({ onEnter }: { onEnter: (code: string) => void }) {
  const [name, setName] = useState(rememberedName);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const { room_id } = await api.createRoom();
      const seat = await api.join(room_id, name);
      saveSeat(room_id, { name: seat.name, token: seat.token });
      rememberName(seat.name);
      onEnter(room_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="lobby">
      <img className="logo" src="/logo.png" alt="Calabria: The Gathering" />
      <p className="tagline">Paper Magic, over webcams, with friends.</p>

      <section className="panel">
        <label>
          Your name
          <input
            autoFocus
            value={name}
            maxLength={24}
            placeholder="e.g. Max"
            onChange={(e) => setName(e.currentTarget.value)}
          />
        </label>
        <div className="lobby-actions">
          <button
            className="primary"
            disabled={busy || !name.trim()}
            onClick={create}
          >
            Create a room
          </button>
          <form
            className="row"
            onSubmit={(e) => {
              e.preventDefault();
              if (code.trim()) {
                if (name.trim()) rememberName(name.trim());
                onEnter(code.trim());
              }
            }}
          >
            <input
              className="code-input"
              value={code}
              maxLength={4}
              placeholder="CODE"
              onChange={(e) => setCode(e.currentTarget.value.toUpperCase())}
            />
            <button type="submit" disabled={!code.trim()}>
              Join
            </button>
          </form>
        </div>
        {error && <p className="error">{error}</p>}
      </section>

      {!isHttpOrigin() && <ServerSetting />}
    </main>
  );
}

/** Only needed in the desktop shell, which has no server origin of its own. */
function ServerSetting() {
  const [url, setUrl] = useState(serverBase());
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <section className="panel small">
      <label>
        Server URL
        <input value={url} onChange={(e) => setUrl(e.currentTarget.value)} />
      </label>
      <div className="row">
        <button
          onClick={async () => {
            setServerBase(url);
            try {
              await api.health();
              setMsg("Server alive");
            } catch (e) {
              setMsg(
                `Unreachable: ${e instanceof Error ? e.message : String(e)}`,
              );
            }
          }}
        >
          Save &amp; test
        </button>
        {msg && <span className="muted">{msg}</span>}
      </div>
    </section>
  );
}
