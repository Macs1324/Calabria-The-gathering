import { useEffect, useRef, useState } from "react";
import { CardHit, Zone, api, cardImage } from "./api";
import { Icon } from "./Icon";
import { overlayOpen } from "./Menu";

const ZONES: [Zone, string][] = [
  ["battlefield", "Battlefield"],
  ["graveyard", "Graveyard"],
  ["exile", "Exile"],
  ["command", "Command"],
];

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
  const inputRef = useRef<HTMLInputElement>(null);

  // "/" jumps to the search from anywhere on the table.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (e.key !== "/" || target.closest("input, textarea, select")) return;
      if (overlayOpen()) return;
      e.preventDefault();
      inputRef.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
    <section className="dock-section add-card">
      <h4>Play a card</h4>
      <div className="segmented wide" role="group" aria-label="Play to">
        {ZONES.map(([z, label]) => (
          <button key={z} aria-pressed={zone === z} onClick={() => setZone(z)}>
            {label}
          </button>
        ))}
      </div>
      <div className="row toggles">
        <button
          className="chip"
          aria-pressed={token}
          onClick={() => setToken((t) => !t)}
        >
          {token && <Icon name="check" size={14} />}
          Token
        </button>
        <button
          className="chip"
          aria-pressed={tapped && zone === "battlefield"}
          disabled={zone !== "battlefield"}
          onClick={() => setTapped((t) => !t)}
        >
          {tapped && zone === "battlefield" && <Icon name="check" size={14} />}
          Tapped
        </button>
      </div>
      <div className="search">
        <Icon name="search" size={16} />
        <input
          ref={inputRef}
          value={query}
          aria-label="Card name"
          placeholder="Search by name…"
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
              if (query) setQuery("");
              else e.currentTarget.blur();
            }
          }}
        />
        {!query && <kbd className="search-key">/</kbd>}
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
