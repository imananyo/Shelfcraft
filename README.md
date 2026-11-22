# Shelfcraft

A local, free-first AI studio for e-commerce sellers: brand profiles, product catalog, product
intelligence, customer-review analysis, competitor / category benchmarks, marketplace listing copy, image generation, a layered design editor, spot edits,
A+ content, bulk "factory" runs and product videos — running on your own Windows, macOS or Linux computer with
**zero mandatory API cost**.

> Inspired by the *workflows* of tools like Pixii.ai (see `docs/REFERENCE_AUDIT.md`), with its own
> name, design and implementation. No third-party code, assets or branding are used.

---

## What runs where

| Capability | Default engine (free) | Runs on |
|---|---|---|
| Listing copy, research, translations | **Ollama** `qwen2.5:3b` | your CPU |
| Creative brief + image-set plan | same text engine (one small call per image) | your CPU (~2–4 min per set) |
| Review analysis, category analysis | same text engine (local or free hosted) | your CPU / hosted |
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

### Running from VS Code

Open the folder (`code .`), then **Ctrl+Shift+P → Tasks: Run Task**:

* **Shelfcraft: Run app (backend + frontend)** — both servers in VS Code terminals; the backend auto-reloads on code changes.
* **Shelfcraft: Backend** / **Shelfcraft: Frontend** / **Shelfcraft: Start Ollama** / **Shelfcraft: Backend tests**.

Or by hand in two terminals (stop `scripts\start.ps1` first so the ports are free):

```powershell
cd backend;  .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app
cd frontend; npm run dev -- -H 127.0.0.1 -p 3000
```

Always type the full `powershell -ExecutionPolicy Bypass -File scripts\start.ps1` — starting the line with `ExecutionPolicy`
runs PowerShell's own `Get-ExecutionPolicy` and fails with *ParameterBindingException*.

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
* **Models are picked automatically.** Leave *Text model* empty (or `auto`) and Gemini, Groq and OpenRouter use the best
  model your key can use right now (OpenRouter: `:free` models only). Free tiers retire models often — e.g. Nov 2026:
  `gemini-2.5-flash`, Groq `llama-3.3-70b-versatile`, OpenRouter `llama-3.3-70b-instruct:free`.
  * A retired / "no longer free" model is skipped from then on, a saved setting naming it is reset to automatic, and the
    stale error is cleared.
  * An overloaded model (HTTP 503) falls through to the next-best one — at most 3 attempts per request, to protect daily free quotas.
  * Paid providers (OpenAI, NanoBanana) never switch models on their own and need a model chosen explicitly.
  * **Test connection** in Settings also clears old errors and shows the model now in use.
* HTTP 429 means the provider's own free-tier limit is used up; Shelfcraft pauses that provider and uses the next one.

See `FREE_RESOURCES.md` for limits, licenses and verification dates.

## Customer reviews and competitors

Open a product → **Reviews** and **Competitors** tabs. Everything is collected from pages *you* open in your own
browser — Shelfcraft never solves CAPTCHAs, rotates proxies or works around bot detection.

* **Import from your browser:** when a marketplace answers an import with a CAPTCHA or sign-in page, open the listing
  in your normal browser, save the page (Ctrl/⌘+S) or copy its source, and upload/paste it in *Add product → From your
  browser* (or the banner on the product). Amazon and Walmart product pages are recognised automatically (ASIN / item id
  must match the product).
* **Reviews tab:** upload saved review pages (Amazon star-filter links and Walmart review links are provided, up to 40
  files at a time), CSV exports or pasted text. Duplicates are skipped. Shows a rating histogram, frequent phrases and a
  filterable review list. **Analyze** tags every review (batches of 12), merges the tags into themes and counts them,
  then writes praise / complaints / feature requests with real quotes. Above 400 reviews a rating-stratified sample is
  used. Expect ~12 min for ~40 reviews on a CPU.
* **Competitors tab:** upload saved Amazon Best Sellers or search-result pages, Walmart search pages or competitor
  product pages. Shows exact benchmarks (price, rating and review quantiles, monthly sales, title length, image count,
  video / A+ share, sponsored share, badges, BSR) and keywords competitors use that your listing is missing — competitor
  brand and product-line names are excluded. **Analyze category** adds an AI summary of what top listings do and what
  their buyers complain about. Untick a row to leave it out.
* Listing copy and product research automatically use the latest review and category analyses when you don't paste any.

## Listing image sets: analyse → plan → render

Open a listing → **Image set**. The set is built in three stages (the same overall pattern as hosted tools like Pixii):

1. **Creative brief** (listing → *Strategy & keywords*): product facts + Deep Strategy (including its image ideas) +
   counted review themes + category benchmark + a short AI pass for the hook, concept and customer needs
   (feature → benefit → emotional payoff → problem solved). It is saved with the product and reused until one of those
   sources changes — then it is marked *Out of date* and rebuilt on the next plan.
2. **Image plan** — **Plan images** writes one plan per slot (main, lifestyle, feature callouts, benefit, comparison,
   dimensions, detail): purpose, scene, headline, callouts, person in scene, and the strategy point it proves.
   Shelfcraft assigns each image a *different* point (hook, pain point, USP, review, spec), plans the main and dimensions
   images without AI, enforces the brand's headline/callout limits, drops callouts not found in the facts and flags
   banned words. Edit anything, then **Save plan**.
3. **Render** — every image is its own job with its own progress and **Retry / Re-render**. Your product photo is never
   redrawn: it is cut out and composited onto an AI background; text is rendered with real fonts as editable layers.

**Brand rules** (brand page → *Brand rules for images & claims* → **Draft with AI**, review, **Save**): claims you can
make, claims that need care, banned words, photo look, layout notes, allowed/banned props, backgrounds, what stays fixed
vs. varies, main-image rules and limits. They are used by the image planner and by every copy prompt. The AI draft only
fills the form; nothing is saved until you save the brand.

## Listing grader

**Grader → From an Amazon URL**: paste any Amazon product link (any domain, share links like `amzn.in/d/…`) or an ASIN
and press **Import & grade**. The public page is read once: title, bullets, description, brand, price/rating, every
listing photo (saved to the library tagged *grader* so the image checks use the real images) and whether it has A+
content. No product is created. Search terms aren't public, so that section is shown as *Not scored* and the score is
calculated from the other sections (same for the description when A+ replaces it). If Amazon shows a robot check, upload
the page saved from your browser or paste its source. **Edit fields** moves everything to *Paste a listing*.

## Project layout

```
backend/   FastAPI · SQLAlchemy · Alembic · SQLite · job queue · AI adapters · imaging · video
  app/ai/          provider registry, adapters, free-only fallback, usage tracking
  app/jobs/        persistent queue (retries, backoff, recovery, cancellation) + handlers
  app/imaging/     rembg, LaMa, compositing, palette/layout analysis, Pillow renderer, fonts
  app/services/    creative pipeline, image_plan (brief + per-slot plan), brand_rules, copywriting, grader,
                   marketplace_scrape, templates, editing, inspire, video, documents
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
  **Known issue:** under Windows PowerShell 5.1 this script currently fails (it prints a Python *SyntaxError* and an
  empty "Backup written:") because PowerShell strips the quotes of the inline Python code. Use the in-app backup until it is fixed.
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
powershell -ExecutionPolicy Bypass -File scripts\test.ps1 -E2E   # + Playwright, against the isolated test instance (start it with scripts\test-instance.ps1)
backend\.venv\Scripts\python.exe backend\scripts\e2e_real.py     # real-model smoke run (slow, CPU)
```

macOS / Linux:

```bash
(cd backend && .venv/bin/python -m pytest -q tests)
(cd frontend && npx tsc --noEmit && npm run lint && npm test)
```

Playwright refuses to run against your real workspace on port 3000 (it would create "E2E Brand …" test data there);
it defaults to the isolated test instance on port 3100. Set `BASE=...` to target another instance, and
`ALLOW_REAL_WORKSPACE=1` only if you really mean port 3000.

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
| Provider card shows "HTTP 404 … model does not exist / no longer available" | Clear *Text model* (automatic) and press **Test connection**; newer versions reset it on their own |
| Provider card shows "HTTP 429" | That provider's free daily/minute limit is used up — wait, or enable another free provider |
| Import says CAPTCHA / "robot check" | Use **From your browser**: save the page in your own browser and upload it |
| Import says "couldn't reach the page (ConnectError)" | Usually a flaky IPv6 route; imports now retry once over IPv4 automatically. Check your connection and import again |
| "DLL load failed … An Application Control policy has blocked this file" | Windows Smart App Control blocked a compiled package. *Steal the look* no longer needs scikit-learn (its palette uses OpenCV); for other packages, allow the file or turn off Smart App Control |
| Logs | `data\logs\backend.log`, `data\logs\web.log` |
