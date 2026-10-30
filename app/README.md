# Calabria: The Gathering — client

Tauri v2 + React client: webcam capture, scan/confirm flow, live battlefield.

```sh
pnpm install
pnpm tauri dev     # dev shell must be active: nix develop
```

First `tauri dev` run compiles the Rust shell for a few minutes. The camera
permission prompt appears on first capture (macOS/Windows handle this natively;
on Linux, the WebKitGTK dialog is used).

See the repository root README and docs/architecture.md for scope.
