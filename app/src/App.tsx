import { useState } from "react";
import "./App.css";

const DEFAULT_SERVER = "http://127.0.0.1:8000";

// Exported for future unit tests (vitest arrives with the camera work).
export async function pingServer(baseUrl: string): Promise<string> {
  const res = await fetch(`${baseUrl}/health`);
  if (!res.ok) return `server answered ${res.status}`;
  const data = (await res.json()) as { status?: string };
  return data.status === "ok" ? "server alive" : `unexpected: ${JSON.stringify(data)}`;
}

export default function App() {
  const [serverUrl, setServerUrl] = useState(DEFAULT_SERVER);
  const [healthMsg, setHealthMsg] = useState<string | null>(null);

  async function ping() {
    setHealthMsg("pinging…");
    try {
      setHealthMsg(await pingServer(serverUrl));
    } catch (e) {
      setHealthMsg(`unreachable: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  return (
    <main className="container">
      <h1>Calabria</h1>
      <p className="subtitle">camera-driven MTG duels</p>

      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          ping();
        }}
      >
        <input
          id="server-url"
          value={serverUrl}
          onChange={(e) => setServerUrl(e.currentTarget.value)}
          placeholder="Server URL"
        />
        <button type="submit">Ping server</button>
      </form>
      {healthMsg && <p>{healthMsg}</p>}
      <p className="placeholder">
        Webcam capture + scan/confirm flow lands in milestone 3 — see
        docs/architecture.md.
      </p>
    </main>
  );
}
