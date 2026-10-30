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
                     card data (built offline by scripts/cli: calabria-build-index)
                     1. Scryfall /bulk-data listing (1 API call per refresh)
                     2. unique_artwork.tar.gz JSONL snapshot (~39 MB, one row per distinct art)
                     3. art crops from cards.scryfall.io CDN (no rate limit, cached on disk)
                     4. index artifact: card_index.npz + cards.db (CALABRIA_DATA_DIR)
```

## Scryfall usage split (verified against their docs)

- `/vision/scan` never touches api.scryfall.com: candidates and names come
  from the local snapshot. Rules: User-Agent header, honor 429 (30s cooldown),
  cache data >= 24h — satisfied by construction.
- Build-time: `/bulk-data` listing then CDN art crops.
- Runtime remaining: `/cards/named?fuzzy=` as OCR fallback (milestone-6), and
  `/cards/collection` for deck registration.

## Recognition pipeline (milestones 1–2)

1. **Detect** classic OpenCV: Otsu threshold (bright card blobs on dark mats)
   → quadrilateral contours → perspective warp to a clean upright 63:88 crop.
   Edge detectors (Canny) were tried and are corner-brittle on solid fills.
   A physical card's white frame is what carries detection — bare art on a
   mat does not separate. Upgrade path for noisy frames: YOLO-nano on
   synthetic composites.
2. **Hash only the art window** (`ART_WINDOW` inset ≈ 68% of card side) so a
   webcam view of a full physical card aligns with Scryfall `art_crop`
   index entries. Fractions are an approximation of modern frames —
   calibrate with real photographs (TODO in milestone 3).
3. **Identify** by retrieval. dHash matrix is the current stand-in
   (in-RAM, `card_index.npz`), with an `Embedder` seam for the swap to
   DINOv2/CLIP embeddings + FAISS. QA on real art with webcam-like
   perturbations: rank-1 ≈ 67%, top-3 ≈ 78% (dHash stage) — the top-3 + tap
   confirm UI lives specifically to absorb that.
4. **Confirm** the client shows top-3 candidate cards as a one-tap modal.
   Every confirm becomes an event log entry.

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
