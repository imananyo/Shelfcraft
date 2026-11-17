# Shelfcraft

A local, free-first AI studio for e-commerce sellers: brand profiles, product catalog, product
intelligence, marketplace listing copy, image generation, a layered design editor, spot edits,
A+ content, bulk "factory" runs and product videos — running on your own Windows, macOS or Linux computer with
**zero mandatory API cost**.

> Inspired by the *workflows* of tools like Pixii.ai (see `docs/REFERENCE_AUDIT.md`), with its own
> name, design and implementation. No third-party code, assets or branding are used.

---

## What runs where

| Capability | Default engine (free) | Runs on |
|---|---|---|
| Listing copy, research, translations | **Ollama** `qwen2.5:3b` | your CPU |
| Optional faster/better text | Gemini · Groq · OpenRouter `:free` · Cloudflare (free tiers) | hosted, opt-in |
| Image backgrounds / scenes | **SD-Turbo** via diffusers (CPU) | your CPU (~30 s/image) |
| Optional hosted images | Cloudflare Workers AI `flux-1-schnell` (10k Neurons/day free) | hosted, opt-in |
| Background removal | **rembg** U²-Net | your CPU |
| Object removal / extend | **LaMa** (ONNX) | your CPU |
| Infographic text | Real fonts rendered as editable layers | your CPU |
| Video | **FFmpeg** slideshow composer (not generative video) | your CPU |

Every generated result shows which provider and model produced it. Non-AI operations (filters,
gradients, upscaling) are labeled non-AI. Paid models are rejected before any request is sent.

## Requirements

**Full install guide for Windows, macOS and Linux: [INSTALL.md](INSTALL.md).**

* Windows 10/11, macOS (Intel/Apple Silicon) or Linux; 8 GB RAM minimum (16 GB recommended), ~8 GB free disk (models + data)
* Python 3.12, Node.js 20+, FFmpeg, Ollama — the setup script installs these for you: `scripts\setup.ps1 -InstallPrereqs` (winget, Windows) or `bash scripts/setup.sh --install-prereqs` (Homebrew on macOS; apt/dnf/pacman/zypper on Linux)
* No GPU needed (all local AI runs on CPU)

## Quick start

macOS / Linux:

```bash
bash scripts/setup.sh --install-prereqs --pull-ollama-models
bash scripts/start.sh      # opens http://127.0.0.1:3000
bash scripts/stop.sh
```

Windows:

```powershell
cd <path-to>\shelfcraft

# 1) one-time setup (add -InstallPrereqs to install Python 3.12 / Node / FFmpeg / Ollama via winget)
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -PullOllamaModels

# 2) optional: local image generation (~250 MB wheels + ~2.5 GB model)
powershell -ExecutionPolicy Bypass -File scripts\install-local-image-model.ps1

# 3) start (opens http://localhost:3000)
powershell -ExecutionPolicy Bypass -File scripts\start.ps1          # dev mode
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Prod    # optimized build

# stop
powershell -ExecutionPolicy Bypass -File scripts\stop.ps1
```

Optional local image generation on macOS / Linux: `bash scripts/install-local-image-model.sh`.

Optional demo data (a brand, two products, a design):

```bash
backend/.venv/bin/python backend/scripts/seed_demo.py           # macOS / Linux
backend\.venv\Scripts\python.exe backend\scripts\seed_demo.py   # Windows
```

## Optional hosted providers (free tiers only)

Add keys in **Settings → AI providers** (stored server-side only) or in `backend\.env`
(copy from `backend\.env.example`). Each provider card shows: free-tier verification date and
source, current limits, license notes, privacy notes, last success/error and rate-limit state.

* Free tiers may log or train on prompts — a privacy confirmation is shown before the first hosted provider is enabled.
* Mistral's adapter exists but is **blocked**: its free tier could not be verified (API keys require billing activation per its docs).
* Fallback order is configurable; only enabled, free-eligible providers are tried, then local models.

See `FREE_RESOURCES.md` for limits, licenses and verification dates.

## Project layout

```
backend/   FastAPI · SQLAlchemy · Alembic · SQLite · job queue · AI adapters · imaging · video
  app/ai/          provider registry, adapters, free-only fallback, usage tracking
  app/jobs/        persistent queue (retries, backoff, recovery, cancellation) + handlers
  app/imaging/     rembg, LaMa, compositing, palette/layout analysis, Pillow renderer, fonts
  app/services/    creative pipeline, copywriting, templates, editing, inspire, video, documents
  app/routers/     REST API (all under /api)
  tests/           pytest suite
frontend/  Next.js 16 · React 19 · TypeScript · Tailwind v4 · Radix · Konva
  src/app/         pages (dashboard, brands, products, listings, studio, edit, editor, aplus, …)
  src/components/  shell, editor (canvas/panels), UI kit
  e2e/             Playwright end-to-end tests
scripts/   setup, start, stop, backup, restore, test, install-local-image-model (.ps1 for Windows, .sh for macOS/Linux)
docs/      reference audit, feature matrix, flows, design system, architecture
data/      (created at runtime, git-ignored) database, media, models, logs, backups
```

## Public API, MCP server and teams

* **Public API:** Settings → *API & MCP* → **Create key**. Then call `http://127.0.0.1:8000/v1/...` (or `http://127.0.0.1:3000/v1/...`)
  with `Authorization: Bearer sk_shelf_…`. Interactive docs: **http://127.0.0.1:8000/v1/docs**. The app's own `/api` is unchanged.
* **MCP server** (Claude Desktop, Claude Code, other MCP clients): `backend\mcp_server.py` — Settings → *API & MCP* shows a ready-to-paste config.
  Example for Claude Code:
  ```powershell
  claude mcp add shelfcraft -e SHELFCRAFT_API_KEY=sk_shelf_... -- <shelfcraft>/backend/.venv/bin/python <shelfcraft>/backend/mcp_server.py   # Windows: <shelfcraft>\backend\.venv\Scripts\python.exe
  ```
* **Team members:** Settings → *Team* → enable team mode (creates the owner login), invite teammates (share the link), assign
  admin / editor / viewer. To let them reach your PC on the same network: `scripts\start.ps1 -Prod -Lan` on Windows or `bash scripts/start.sh --prod --lan` on macOS/Linux (refused unless team mode is on).
* **Amazon import:** Settings → *Integrations* → Amazon Selling Partner API with your own seller credentials. Or paste any listing text in *Add product*.

## Backups

* **In the app:** Settings → Storage & data → *Create backup now* (ZIP of database + media).
* **Command line:** `scripts\backup.ps1 [-Destination D:\Backups]` — works while the app is running (SQLite online backup).
* **Command line (macOS / Linux):** use the in-app backup above.
* **Restore:** stop the app, then `scripts\restore.ps1 -Backup <zip>` (Windows) or `bash scripts/restore.sh <zip>` (macOS / Linux). Your current data is moved to
  `data\pre-restore-<timestamp>` first, so a wrong restore is reversible.

## Security notes

* API binds to `127.0.0.1` only; the browser talks to the Next.js origin, which proxies `/api`.
* Provider keys never reach the browser (the API returns only `has_key`).
* Uploads are type-checked by content (magic bytes), size-limited (25 MB default), stored under random names; storage paths are confined to the media root.
* Optional access token: set `SHELFCRAFT_ACCESS_TOKEN` in `backend\.env`, then enter it in Settings → Preferences.
* FFmpeg is invoked with argument lists only (no shell). Website auto-fill refuses private/loopback addresses and sites that prohibit automated access.

## Tests

```powershell
powershell -ExecutionPolicy Bypass -File scripts\test.ps1        # pytest + tsc + eslint + vitest
powershell -ExecutionPolicy Bypass -File scripts\test.ps1 -E2E   # + Playwright (app must be running)
backend\.venv\Scripts\python.exe backend\scripts\e2e_real.py     # real-model smoke run (slow, CPU)
```

macOS / Linux:

```bash
(cd backend && .venv/bin/python -m pytest -q tests)
(cd frontend && npx tsc --noEmit && npm run lint && npm test)
```

Results: `TEST_REPORT.md`. Status of every feature: `FEATURE_STATUS.md`.

## Troubleshooting

macOS / Linux troubleshooting (Python/Node versions, espeak-ng, fonts, build tools) is in [INSTALL.md](INSTALL.md#troubleshooting).

| Symptom | Fix |
|---|---|
| "No text AI is reachable" | Start Ollama (Start menu on Windows, `ollama serve` on macOS/Linux) and `ollama pull qwen2.5:3b`, or add a free key in Settings |
| Image jobs use a plain gradient | Install/enable Local diffusion (script above) or Cloudflare in Settings |
| `onnxruntime` / `torch` DLL load failed | Install the VC++ runtime (`winget install Microsoft.VCRedist.2015+.x64`) or re-run `setup.ps1` (applies a no-admin fallback) |
| Video export unavailable | Install FFmpeg (`winget install Gyan.FFmpeg` · `brew install ffmpeg` · `sudo apt install ffmpeg`) and restart |
| Port already in use | `scripts\stop.ps1` / `bash scripts/stop.sh`, or start with `-ApiPort`/`-WebPort` (`--api-port`/`--web-port`) |
| Logs | `data\logs\backend.log`, `data\logs\web.log` |
