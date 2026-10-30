import { useEffect, useRef, useState } from "react";
import { CardHit, ScanCandidate, Zone, api, cardImage } from "./api";
import { Camera } from "./Camera";
import { RoomActions } from "./useRoom";

/**
 * Put a card into play. Typing is the first-class path; the camera scan only
 * pre-fills candidates (top-3 to tap), and "none of these" falls back to search.
 */
export function AddCard({ send }: { send: RoomActions["send"] }) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<CardHit[]>([]);
  const [active, setActive] = useState(0);
  const [zone, setZone] = useState<Zone>("battlefield");
  const [token, setToken] = useState(false);
  const [tapped, setTapped] = useState(false);
  const [camera, setCamera] = useState(false);
  const [scanned, setScanned] = useState<ScanCandidate[] | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!query.trim()) {
      setHits([]);
      return;
    }
    const ctrl = new AbortController();
    const t = window.setTimeout(() => {
      api
        .search(query, ctrl.signal)
        .then((res) => {
          setHits(res.results);
          setActive(0);
        })
        .catch(() => {
          /* aborted or offline: keep the last results */
        });
    }, 120);
    return () => {
      window.clearTimeout(t);
      ctrl.abort();
    };
  }, [query]);

  const play = (card: { card_id: string; name: string | null }) => {
    send("card_play", {
      card_id: card.card_id,
      name: card.name,
      zone,
      token,
      tapped: tapped && zone === "battlefield",
    });
    setQuery("");
    setHits([]);
    setScanned(null);
    setToken(false);
  };

  return (
    <section className="panel add-card">
      <h4>Play a card</h4>
      <div className="row options">
        <select
          value={zone}
          onChange={(e) => setZone(e.currentTarget.value as Zone)}
        >
          <option value="battlefield">to battlefield</option>
          <option value="graveyard">to graveyard</option>
          <option value="exile">to exile</option>
          <option value="command">to command zone</option>
        </select>
        <label className="check">
          <input
            type="checkbox"
            checked={token}
            onChange={(e) => setToken(e.currentTarget.checked)}
          />{" "}
          token
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={tapped}
            disabled={zone !== "battlefield"}
            onChange={(e) => setTapped(e.currentTarget.checked)}
          />{" "}
          tapped
        </label>
      </div>

      <div className="search">
        <input
          ref={inputRef}
          value={query}
          placeholder="Type a card name… (e.g. light bo)"
          onChange={(e) => setQuery(e.currentTarget.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(a + 1, hits.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === "Enter" && hits[active]) {
              play(hits[active]);
            } else if (e.key === "Escape") {
              setQuery("");
            }
          }}
        />
        {hits.length > 0 && (
          <ul className="hits">
            {hits.map((h, i) => (
              <li
                key={h.card_id}
                className={i === active ? "active" : ""}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => {
                  e.preventDefault(); // keep focus in the input
                  play(h);
                }}
              >
                <img
                  src={cardImage(h.card_id, "small")}
                  alt=""
                  loading="lazy"
                />
                <span>{h.name}</span>
                <small>{h.set_code.toUpperCase()}</small>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="row">
        <button
          className={camera ? "on" : ""}
          onClick={() => setCamera((c) => !c)}
        >
          {camera ? "Hide camera" : "📷 Scan with camera"}
        </button>
      </div>

      {camera && <Camera onCandidates={setScanned} />}

      {scanned && (
        <div className="scan-result">
          {scanned.length === 0 ? (
            <p className="muted">
              No card found. Hold it flat and fill more of the frame, or type
              its name.
            </p>
          ) : (
            <>
              <p className="muted">Which one is it?</p>
              <div className="candidates">
                {scanned.map((c) => (
                  <button
                    key={c.card_id}
                    className="candidate"
                    onClick={() => play(c)}
                    title={c.name ?? c.card_id}
                  >
                    <img
                      src={cardImage(c.card_id, "small")}
                      alt={c.name ?? ""}
                    />
                    <span>{c.name ?? c.card_id}</span>
                  </button>
                ))}
              </div>
            </>
          )}
          <button
            className="ghost"
            onClick={() => {
              setScanned(null);
              inputRef.current?.focus();
            }}
          >
            None of these — I'll type it
          </button>
        </div>
      )}
    </section>
  );
}
