# Architecture working notes

Deliberately short. Long-form design belongs in decisions with dates, below;
anything else drifts out of date.

## Shape

```
+-------------------+        +------------------------------+
| app (Tauri)       |  HTTPS | server (FastAPI)             |
|  webcam capture   |  ----> |  /vision/scan  -> candidates |
|  confirm top-3    |        |  rooms + event-sourced state |
|  battlefield view |  <---- |  WS (later): live sync       |
+-------------------+        +------------------------------+
                                      |
                                      v
                              Scryfall bulk data (card metadata + art vectors)
                              prebuilt at build/boot time, cached on disk
```

## Recognition pipeline (milestones 1–2)

1. **Detect** classic OpenCV: Canny → contours → quadrilateral → perspective
   warp to a clean upright crop (63:88). No training needed; upgrade path is a
   YOLO-nano detector on synthetic composites.
2. **Identify** by retrieval: dHash first (fast, close-match), then embedding
   (DINOv2/CLIP over Scryfall `art_crop`, index in RAM ~100MB). A "classifier"
   over >100k classes loses to a nearest-neighbor retrieval; we classify by lookup.
3. **Confirm** the client shows top-3 candidates as a one-tap modal. This
   absorbs reprints, glare, and low-confidence matches into cheap human input,
   and each confirm is logged as an event.

## Game state (tier 0)

Event-sourced: `apply(events) -> state`, rooms are a fold over an event log.
Clients render the log; the log doubles as replay and cheat-forensics. Hand
privacy is natural: hands are held off-camera, so a card exists for the server
only once it is scanned into play.

## Working decisions (2026-10-30)

- **Online 1v1 first.** Each player has their own app + webcam; server arbitrates.
- **Top-3 confirm UI** instead of auto-accept. Model error becomes a tap, not corruption.
- **Tier 0 game logic.** Zones, turn order, life; plays are accepted events.
- **Casual 60-card** format to start (Commander raises state-space cost).
- **Cheat window is accepted** in tier 0 (nothing proves you own six
  Bitterblossoms); deck registration closes it in milestone 6.

## Known risks

- **Sleeves.** Opaque sleeves hide art and name. V0 assumes unsleeved/clear
  play; the confirm UI is the fallback for anything else.
- **Glare and near-identical generic artwork** (basic lands) — acceptable
  failure mode; confirm UI resolves.
- **Scryfall images are fan-use** (fine for free/hobby; revisit before any monetization).

## Environment rule of thumb

Dependency changes touch three files together: `server/pyproject.toml`
(+ `uv.lock`), `flake.nix`, and `server/Dockerfile`. `uv.lock`, `pnpm-lock.yaml`,
and `Cargo.lock` are committed.
