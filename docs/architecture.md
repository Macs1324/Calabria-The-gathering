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
                     3. full-card "small" images from cards.scryfall.io CDN (no rate limit, cached)
                     4. index artifact: card_index.npz + cards.db (CALABRIA_DATA_DIR)
```

## Scryfall usage split (verified against their docs)

- `/vision/scan` never touches api.scryfall.com: candidates and names come
  from the local snapshot. Rules: User-Agent header, honor 429 (30s cooldown),
  cache data >= 24h — satisfied by construction.
- Build-time: `/bulk-data` listing then CDN art crops.
- Runtime remaining: `/cards/named?fuzzy=` as OCR fallback (milestone-6), and
  `/cards/collection` for deck registration.

## Recognition pipeline

1. **Detect**, training-free, two candidate passes merged by overlap:
   *color* (distance from the mat's median Lab color, threshold riding on the
   mat's own noise, so black borders on dark mats separate) and *edges*
   (Canny → close → fill, for illustrated/blotchy mats). Shape checks: area,
   convexity, 63:88-ish aspect. Largest first; anything mostly inside a kept
   quad is dropped (a card's own text box is card-shaped too).
   History: bright-blob Otsu thresholding locked onto the light *text box*
   of black-bordered cards — 0% identification on realistic frames. Fixed
   2026-10-30.
2. **Orient.** Portrait quads are upright or upside down; landscape quads
   are *tapped* (reported as `tapped: true`, groundwork for auto-tap). Both
   candidate warps are hashed; the closer match wins.
3. **Identify** by retrieval against Scryfall's *full-card* images
   ("small", ~10 KB each). Both sides hash the same card-relative region
   (`HASH_REGION`: name bar through art) with a 256-bit dHash, so no
   per-frame-style calibration exists to get wrong (the old `ART_WINDOW`
   inset did not survive borderless/showcase/old frames). Candidates are
   deduped by card name. The `Embedder` seam stays for a learned embedding.
4. **Confirm.** The client shows the top-3 as a one-tap choice with name
   search right below it. Every confirm becomes an event log entry.

**Measuring it:** `uv run calabria-eval-scan --photos DIR` scores real photos
named after the card (`Lightning Bolt.jpg`); `--synthetic N` composites real
card images onto textured mats with glare, perspective, blur, JPEG and 30%
tapped. Synthetic, N=400, 55,603-card index (2026-10-30): detected 95.5%,
name@1 89.0%, name@3 89.5%. Real-photo numbers: not measured yet — that is
the next calibration step.

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
- **Black border on a dark busy mat** can vanish; the edge pass then finds
  the inner frame (~4% inset per side), which matching tolerates. A plain,
  mid-tone mat gives the best results.
- **Overlapping cards** merge into one concave blob and are skipped; scan
  one card at a time (single mode) when playing.
- **Scryfall images are fan-use** (fine for free/hobby; revisit before any monetization).

## Environment rule of thumb

Dependency changes touch three files together: `server/pyproject.toml`
(+ `uv.lock`), `flake.nix`, and `server/Dockerfile`. `uv.lock`, `pnpm-lock.yaml`,
and `Cargo.lock` are committed.
