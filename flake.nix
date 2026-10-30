{
  # Calabria — camera-driven MTG dueling platform.
  #
  # This devshell is the source of truth for tool versions. When project
  # dependencies change, keep it and server/Dockerfile up to date together.
  #
  # Usage:   nix develop
  # Non-fish fallback: nix develop -c $SHELL
  description = "Calabria development environment";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { nixpkgs, ... }:
    let
      # NOTE: x86_64-darwin was dropped by nixpkgs 26.11
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (s: f nixpkgs.legacyPackages.${s});
    in
    {
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          name = "calabria-dev";
          packages = [
            # Server (Python, managed with uv)
            pkgs.python312
            pkgs.uv

            # App (Node + Tauri)
            pkgs.nodejs
            pkgs.pnpm
            pkgs.rustc
            pkgs.cargo
            pkgs.clippy
            pkgs.rust-analyzer
            pkgs.cargo-tauri
          ]
          ++ pkgs.lib.optionals pkgs.stdenv.hostPlatform.isLinux [
            # Linux GUI stack Tauri links against (WebKitGTK 4.1 & friends)
            pkgs.pkg-config
            pkgs.glib
            pkgs.gtk3
            pkgs.webkitgtk_4_1
            pkgs.gdk-pixbuf
            pkgs.pango
            pkgs.cairo
            pkgs.librsvg
            pkgs.xdotool # provides libxdo, used by Tauri window interactions
            pkgs.libayatana-appindicator
            pkgs.dbus
            pkgs.libGL
          ];
          env = { }
            // pkgs.lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux {
              PKG_CONFIG_PATH = pkgs.lib.makeSearchPath "lib/pkgconfig" [
                pkgs.glib.dev
                pkgs.gtk3.dev
                pkgs.libsoup_3.dev
                pkgs.webkitgtk_4_1.dev
                pkgs.gdk-pixbuf.dev
                pkgs.pango.dev
                pkgs.cairo.dev
              ];
              # Let manylinux wheels (OpenCV, NumPy) find native runtime libs on NixOS.
              LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
                pkgs.stdenv.cc.cc.lib
                pkgs.libGL
                pkgs.zlib
              ];
            };
        };
      });
    };
}
