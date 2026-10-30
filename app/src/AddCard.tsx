import { useEffect, useState } from "react";
import { CardHit, Zone, api, cardImage } from "./api";

export interface PlayOptions {
  zone: Zone;
  token: boolean;
  tapped: boolean;
}

/** Type-to-play: always one keystroke away, whatever the camera thinks. */
export function AddCard({
  onPlay,
}: {
  onPlay: (card: CardHit, opts: PlayOptions) => void;
}) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<CardHit[]>([]);
  const [hitsFor, setHitsFor] = useState(""); // the query `hits` answer
  const [active, setActive] = useState(0);
  const [zone, setZone] = useState<Zone>("battlefield");
  const [token, setToken] = useState(false);
  const [tapped, setTapped] = useState(false);

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
          setHitsFor(query);
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

  const play = (card: CardHit) => {
    onPlay(card, { zone, token, tapped: tapped && zone === "battlefield" });
    setQuery("");
    setHits([]);
    setToken(false);
  };

  return (
    <section className="panel add-card">
      <div className="panel-head">
        <h4>Play by name</h4>
      </div>
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
            } else if (e.key === "Enter" && hitsFor === query && hits[active]) {
              // Only play what the visible results answer: no stale top hit
              // from a shorter query while the new search is in flight.
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
    </section>
  );
}
