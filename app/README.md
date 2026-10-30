# Calabria: The Gathering — client

React client: lobby, live table, card search, webcam scan + confirm. Built
once and served by the server at `/`, so players just open the server URL in
a browser — nothing to install.

```sh
pnpm install
pnpm build          # -> dist/, picked up by the server (CALABRIA_WEB_DIR, default ../app/dist)
pnpm dev            # hot reload on :1420, proxying API + WebSocket calls to a local server on :8000
```

The camera only works on `https://` pages or `localhost` (browser rule) —
see the root README's Hosting section.

The Tauri shell (`pnpm tauri dev`) still builds and asks for a server URL on
the lobby screen, but the browser is the supported way to play: WebKitGTK
(Tauri's Linux webview) is unreliable with webcams.

**Hands-free play.** Turn on the mat camera once (it's remembered):
cards you lay on your mat are played, physically tapping/untapping them
syncs, and a card that leaves the mat asks "Graveyard / Exile / Hand?". Only
cards the server isn't sure about ask you to pick one of three. Every
automatic action shows a toast with Undo. The 🎙 Voice toggle (Chrome, Edge,
Safari) adds commands like "end turn", "untap", "hit Bea for 4", "lose 2",
"play Lightning Bolt", "one/two/three", "roll a d20" — the ? next to it lists
them. Only whole short phrases count, so table talk doesn't fire anything.

Tests: `pnpm test` (vitest: mat-watch decisions, voice grammar).

Shortcuts on the table: click a card to select it, then `T` tap, `G`/`E`/`C`
graveyard/exile/command, `H`/`L` hand/library, `B` battlefield, `Esc`
deselect; double-click taps; `Ctrl+Z` undoes your last action; `Space` scans
when the camera is open.
