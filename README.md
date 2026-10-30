# Calabria: The Gathering

<p align="center"><img src="app/public/logo.png" alt="Calabria: The Gathering" width="600"></p>

Camera-driven Magic: The Gathering dueling platform. Play real, physical cards;
the desktop app watches your playmat over a webcam, recognizes what you played,
and the server arbitrates the duel between remote players.

**Scope for now (tier 0 — "digital playmat"):** online 1v1, casual 60-card.
The server accepts plays as events, tracks zones/turns/life, and lets the
camera pre-fill card identity; strict rule enforcement comes later. The scan
*is* the play declaration — a card enters the game by physically leaving your
hand and appearing on your mat.

## Repository layout

```
server/    Python + FastAPI + OpenCV service: card recognition, rooms, game state
app/       React + Tauri v2 desktop client: webcam capture, confirm UI, live view
flake.nix  devshell (Python/uv, Node/pnpm, Rust, Tauri GTK stack)
docs/      architecture notes and working decisions
```

## Branch workflow

- `main` — stable. Gets merges from `develop` at milestones, tagged `vX.Y.Z`.
- `develop` — integration. Every feature lands here via merge (no-ff).
- `feature/<area>-<slug>` — one concern per branch (e.g. `feature/vision-quads`).

Two rules that ride along with every change:

1. **TDD.** Tests are written (and committed failing) before the code that
   makes them pass for anything under `server/`.
2. **Keep the environment honest.** Adding a dependency means updating
   `server/pyproject.toml` + `server/uv.lock`, the `flake.nix` devshell, and
   `server/Dockerfile` in the same change.

## Quickstart (NixOS / other hosts with Nix)

```sh
nix develop                     # python+uv, node+pnpm, rust, tauri deps

# client: build once, the server serves it at /
cd app && pnpm install && pnpm build && cd ..

# server
cd server
uv sync                         # creates .venv from uv.lock
uv run pytest                   # tests first, see "Branch workflow"
uv run calabria-build-index     # once: card data (see below)
uv run uvicorn calabria.api.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000, create a room, send the link to a friend. For
client work, `pnpm dev` in `app/` hot-reloads on :1420 and proxies to :8000.

## Building the card index

```sh
cd server
uv run calabria-build-index                     # full index (~55k images, ~2-3 min, resumable)
uv run calabria-build-index --limit 2000        # capped run for a quick start
```

Artifacts land in `server/data/` (override with `CALABRIA_DATA_DIR`): the
unique-artwork JSONL snapshot, a sharded card-image cache (~750 MB),
`cards.db` (names/sets), and `card_index.npz` (the retrieval index
`/vision/scan` queries). Re-runs are cheap: one listing request per refresh,
images already cached stay on disk. An index built before v0.2 is ignored
(with a warning) until rebuilt; the old `art_cache/` folder can be deleted.

Measure recognition with `uv run calabria-eval-scan --synthetic 400`, or
better, on photos of your own cards: `--photos DIR` with files named after
the card (`Lightning Bolt.jpg`, `Lightning Bolt 2.jpg`).

## Hosting a game night

One machine runs the server; everyone else just opens a link.

```sh
docker build -t calabria -f server/Dockerfile .
docker run --rm -v calabria-data:/data calabria calabria-build-index --data-dir /data   # once, ~3 min
docker run -d --name calabria -p 8000:8000 -v calabria-data:/data calabria
```

(or run it straight from `server/` as in the quickstart). Rooms are saved
under the data dir, so restarting the server resumes games in progress.

**Friends need HTTPS for the camera.** Browsers only allow webcams on
`https://` pages (or `localhost`). Pick one:

- **Cloudflare quick tunnel** (no account): `cloudflared tunnel --url http://localhost:8000`
  prints a `https://….trycloudflare.com` link to share. On NixOS:
  `nix run nixpkgs#cloudflared -- tunnel --url http://localhost:8000`.
- **Tailscale** (if everyone is on your tailnet, or via Funnel for the
  public): `tailscale serve 8000` / `tailscale funnel 8000`.

Without HTTPS everything except the camera still works: typing card names is
a first-class way to play.

**Playing:** each player keeps their own webcam pointed at their own mat.
Hold a card under the camera and hit Space (or type its name), tap the right
candidate, and it appears on both screens. Use Discord or similar for voice
and face cams; Calabria is the shared board. A plain, mid-tone playmat and
unsleeved or clear-sleeved cards scan best.

## Roadmap

| # | Milestone | Status |
|---|-----------|--------|
| 0 | Repo skeleton, toolchain, Dockerfile, docs | ✅ landed (v0.0.1) |
| 1 | Vision core: quads → warp → dHash index → top-3 candidates | ✅ (superseded by 4.5) |
| 2 | Server: `/vision/scan` + rooms REST + event log | ✅ |
| 2.5 | Scryfall index: bulk snapshot, art cache, name-joined candidates, resumable build | ✅ v0.1.0 |
| 3 | App: camera screen, snap → scan → confirm round trip | ✅ v0.2.0 (web client) |
| 4 | Rooms WS sync, two clients in one room | ✅ v0.2.0 (+ seats, persistence, undo) |
| 4.5 | Recognition v2: mat-difference + edge detection, full-card hashing, eval CLI | ✅ v0.2.0 |
| 5 | Real-photo calibration, auto-tap from card rotation, card-back detection | next |
| 6 | Deck registration (cheat-proof scans), matchmaking, Tier-1 rules | later |

Details and working decisions: [docs/architecture.md](docs/architecture.md).
