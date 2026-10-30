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

# server
cd server
uv sync                         # creates .venv from uv.lock
uv run pytest                   # ~threads tests first, see docs
uv run uvicorn calabria.api.main:app --reload

# app (first tauri build takes a while: compiles the Rust shell)
cd app
pnpm install
pnpm tauri dev
```

## Building the card index

```sh
cd server
uv run calabria-build-index                     # full index (~55k crops, resumable)
uv run calabria-build-index --limit 2000        # capped run for a quick start
```

Artifacts land in `server/data/` (override with `CALABRIA_DATA_DIR`): the
unique-artwork JSONL snapshot, a sharded art cache, `cards.db` (names/sets),
and `card_index.npz` (the retrieval index `/vision/scan` queries). Re-runs
are cheap: one listing request per refresh, art crops already cached stay on
disk.

## Server container

```sh
docker build -t calabria-server -f server/Dockerfile .
docker run -p 8000:8000 calabria-server
```

## Roadmap

| # | Milestone | Status |
|---|-----------|--------|
| 0 | Repo skeleton, toolchain, Dockerfile, docs | ✅ landed (v0.0.1) |
| 1 | Vision core: quads → warp → dHash index → top-3 candidates | ✅ (dHash stand-in; embedding swap next) |
| 2 | Server: `/vision/scan` + rooms REST + event log | ✅ |
| 2.5 | Scryfall index: bulk snapshot, art cache, name-joined candidates, resumable build | ✅ this branch |
| 3 | App: camera screen, snap → scan → confirm round trip | in progress (shell scaffolded) |
| 4 | Rooms WS sync, two clients in one room | later |
| 5 | Auto-tap from card rotation, card-back detection | later |
| 6 | Deck registration (cheat-proof scans), matchmaking, Tier-1 rules | later |

Details and working decisions: [docs/architecture.md](docs/architecture.md).
