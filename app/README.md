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

Shortcuts on the table: click a card to select it, then `T` tap, `G`/`E`/`C`
graveyard/exile/command, `H`/`L` hand/library, `B` battlefield, `Esc`
deselect; double-click taps; `Ctrl+Z` undoes your last action; `Space` scans
when the camera is open.
