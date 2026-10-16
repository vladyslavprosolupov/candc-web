# Generals Web — local disc edition

Local browser build of the actual **Command & Conquer: Generals Zero Hour**
engine. The engine runs as WebAssembly with WebGL2 graphics, SDL3 input,
OpenAL/Web Audio and FFmpeg. Game data comes from your own local installation.

## Run

```sh
npm start
```

Open **http://localhost:8080** in Chrome and press **Play**. The first launch
imports approximately 2.73 GiB of game files into the browser's OPFS storage
from this local server (approximately 1.85 GiB transferred). Later launches
reuse those files. Keep this origin and port to retain access to saves.
The server listens only on loopback. No Steam account is required.

The primary target is **Zero Hour**. The base Generals archives supply shared
resources; a standalone vanilla Generals runtime has not been built here.
The supplied installation includes Russian localization archives, which are
preserved. The web launcher's language is independent of the game's language.

## Rebuild

The bootstrap needs Git, curl, Python 3 with venv, and the host C/C++ build
utilities (including make). It installs pinned CMake/Ninja and Emscripten
**4.0.10** under ignored `.tools/`, without changing shell startup files.

```sh
npm run bootstrap
npm run build
npm run export
npm run preview
# http://localhost:8095
```

A fresh checkout reconstructs `engine/` from the exact upstream commit and
tracked patch, then verifies its Git tree against `engine-version.json`. Added
patch files enter Git's index so the downloadable source includes them. An
existing engine with different source or developer edits is preserved and the
bootstrap fails; use a separate clean checkout instead of resetting it.

`build-lock.json` pins the SDK installer commit, compiler version, build tools
and Liberation 2.1.5 archive plus individual font hashes. Fonts are downloaded
from the open-source release into `.tools/fonts`, never from an installed game.
The build and export need no `.local/staged` installation or game archives.
FFmpeg and all source dependencies are fetched from pinned revisions/archives;
its build directory uses a project-specific temporary path because FFmpeg's
makefiles cannot handle this workspace's ampersand.

For the complete clean Linux/Cloudflare path, run `npm run build:cloud`. It
bootstraps, installs the locked npm packages, compiles the real engine, runs
tests against the generated bridge and exports `release/`. Normal builds keep
temporary diagnostics OFF. Only the current investigation opts in with
`GX_WEB_DIAGNOSTICS=1 npm run build:cloud`; its separate server gate must also
be explicitly enabled in the deployment settings. `BUILD_JOBS` bounds engine
and FFmpeg compilation (cloud default: 2).

Only when Cloudflare sets `CF_PAGES=1`, the final build step derives the
Functions runtime gate from the verified exported build manifest and writes
that gate into the ephemeral checkout's `wrangler.jsonc`. This runs after source
export, so the downloadable source retains the default-OFF configuration. Local
builds leave the versioned runtime configuration unchanged. The deployed Git
build must verify that Pages consumes this generated runtime setting.

Optional local asset packing is separate from the hosting build:

```sh
python3 -m venv .tools/python
.tools/python/bin/pip install Brotli==1.1.0
npm run assets -- --source '/path/to/Command and Conquer - Generals'
```

`scripts/import-assets.py` validates BIG archive indexes, stages only data,
maps and fonts, and creates the browser package. It does not execute Windows
binaries or modify the original installation. The existing extracted files
are used; the ISO is not needed. Audit results are in `.local/asset-audit.json`.
Asset packs, local caches and build output are excluded from the engine's Git
tracking. **Do not publish `engine/web/dist/assets/`: it contains your game data.**

## Code and provenance

- `engine/`: [Lolendor/Generals-WebAssembly](https://github.com/Lolendor/Generals-WebAssembly),
  pinned to `2f564cd6095485e1303335e516b9449fd8c041f3` before local changes.
  It forks [the requested Apple port](https://github.com/ammaarreshi/Generals-Mac-iOS-iPad),
  based on GeneralsX and EA's released source.
- [GTA Vice City WASM](https://github.com/joncodeofficial/gta-vice-city-wasm) was
  examined as a reference for local browser asset storage. No GTA code or data
  is required or bundled.
- `scripts/`: local asset import, build and HTTP server integration.
- `tests/`: archive validation and HTTP isolation/range regression tests.

The wrapper and `engine/` are independent Git repositories. `engine-version.json`
records the upstream revision, preserved pre-existing baseline and current local
engine commit. The tracked `patches/generals-local.patch` reconstructs the current
engine source from the pinned upstream revision; local engine commits need not
exist on the upstream remote. Exported source includes both working source and
this provenance manifest.

Engine licensing is GPL v3 with the additional terms in `engine/LICENSE.md`.
Game assets remain separately owned. Fonts are Liberation 2.1.5. This is an
independent modified program, not an EA product or an EA-endorsed release.

## Validation

```sh
npm test
# GPU integration fixture (requires the configured Emscripten build):
npm run test:renderer:build
# With npm start running, open http://localhost:8080/render-test/
```

The input-freeze investigation adds actual-SDL concurrency tests and actual
WebGL ownership/cache fixtures. See
`engine/docs/WORKDIR/reports/2026-10-16_BROWSER_INPUT_INVESTIGATION.md` for
reproduction commands, evidence and limits, and `hosting/README.md` for explicit
temporary diagnostics opt-in, disable and removal. Normal builds and exports
keep diagnostic probes/collection disabled.

Historical validation of the earlier build follows; current validation is
recorded in the investigation report and hosting guide.

These tests check invalid/truncated BIG archives, WebAssembly MIME types,
COOP/COEP isolation, full and partial responses, HEAD and invalid ranges.
Verified in Chrome on 2026-10-08 with the supplied files: compilation from
source, first import into OPFS, subsequent launch using cached assets, main
menu, Alpine Assault skirmish against AI, unit selection, moving a dozer to
construct a power plant, completed construction, radar upgrade and minimap.
The game displayed 29–30 FPS at the default 30 FPS cap during this short test.
Screenshot: `.local/skirmish-proof.jpg`.

As of 2026-10-15 the launcher defaults to a 120 render FPS ceiling. The existing
WebMain/FramePacer path preserves the original game-speed rate independently;
the launcher does not inject the engine's `-fps` game-speed argument. Chrome
showed 112–118 FPS in a short USA campaign test, with 17 seconds of mission time
over 17 seconds of wall time. Actual FPS depends on display refresh and workload.
The legacy `gx-fps=30` default upgrades to 120; legacy 60/90 preferences remain.
The render-only `gx-render-fps` preference supports 30/60/90/120.

The local renderer patch fixes an upside-down frame in upstream: clip-space
Y, face winding, texture-target orientation and viewport/scissor coordinates
are now consistent. The browser now owns fullscreen: native SDL fullscreen
switching no longer changes the backbuffer to the monitor size and adds a frame.
The Direct3D device initializes automatic depth testing on creation and reset.
Previously ZENABLE was zero, so the skybox could paint over the USA intro scene.
The GPU fixture exercises actual D3D8/WebGL drawing and reads back pixels; it
regressed before the fix and now checks visibility, draw order and reset defaults.
All seven GPU checks pass. The first USA mission cinematic was checked visually:
terrain, motorcycles and the rocket site now remain visible in front of the sky.

Save/load was verified after a full page reload (buildings, radar and funds
restored). USA campaign intro video, first mission controls and saving/loading
were tested. A real 8-file save/settings export was restored on a different
origin, and the campaign loaded with the moved tank in its saved position.
The public release imported 282 local data files (2.73 GiB) and launched the
stripped WASM engine. A fresh visit under a subdirectory on a plain static HTTP
server successfully obtained isolation through the service worker.
The complete 282-file tar.gz was imported on a fresh origin, survived reload and
started the engine to its main menu. The TAR parser tests cover fragmented streams,
CRC corruption, truncation, unsafe paths, links and unexpected entries.
Campaign completion, multiplayer, other browsers and long sessions remain unverified.

## Host it for friends

```sh
npm run pack:archive # prepare the separate R2 download
npm run export
npm run preview
# http://localhost:8095
```

Publish only `release/` on Cloudflare Pages, GitHub Pages or your HTTPS server.
It is a static, asset-free release (~92 MiB including downloadable sources;
engine ~8.8 MiB). Each visitor downloads the tar.gz from R2, selects it in the launcher and
imports it into browser storage once. The extracted-folder option is also available. Settings includes save export/restore for migration.
The fullscreen control is at the top right; Alt+Enter (Option+Enter on macOS) also toggles it.
During fullscreen play, Pointer Lock confines the mouse and displays the original
SDL game cursor at the same coordinates used for hit testing. Click the game to
(re)capture the mouse; that activation click is consumed. Esc releases the mouse
(and Chrome may also exit fullscreen). The edge-scroll zone remains 3 pixels.
The launcher uses the normal system cursor.
Unsupported or denied fullscreen requests display an error on the page.
Use a regular browser tab: embedded previews can restrict fullscreen.

See [hosting/README.md](hosting/README.md) for complete deployment instructions,
local import vs hosted pack behavior, storage requirements and save migration.
The package is `.local/downloads/generals-zero-hour-v1.tar.gz` (2.11 GB).
Set its download link in `engine/web/shell/launcher-config.json` before export.
The bucket is `candc-web`; it is separate from the asset-free Pages release.

## Current launcher

The Russian, single-screen launcher is hosted at https://generals.prosolupov.com/
behind Cloudflare Access. Download the archive, select it once, then play.
The Pages project and all deployment hostnames have the same email allow policy.
R2 remains public by the owner’s earlier instruction.

Save export/restore is at `/saves.html` on each origin; the minimal launcher has
no settings/language buttons. Browser data does not move automatically to a new
domain. See `hosting/README.md` for deployment and migration details.
