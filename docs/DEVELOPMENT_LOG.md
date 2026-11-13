# Development Log

## 2026-11-13

**Environment.** Windows 11 Home, i7-1185G7, 15.7 GB RAM, Iris Xe (no CUDA), Node 26, Python 3.15 (system).
Installed with the owner's approval via winget: Git, FFmpeg 9, Python 3.12, Ollama, VC++ runtime.

**Reference audit.** REA listed and passively inspected the owner's logged-in Pixii tab. REA's
`capture_browser_scenario` schema couldn't be resolved and `capture_web_screenshot` timed out, so
a read-only CDP script handled navigation/screenshots (no generation, no credits). See REFERENCE_AUDIT.md.

**Decisions**
- SQLite + persistent DB job queue instead of Redis/Celery (no Docker; single user; survives restarts).
- Python 3.12 venv (ML wheels unavailable/unstable for 3.15).
- onnxruntime/torch needed the VC++ runtime: fixed system-wide; `setup.ps1` keeps a no-admin DLL fallback.
- Local images: SD-Turbo on CPU (measured 27–36 s/image after load). Larger models rejected as impractical.
- Product integrity: real photo is cut out (rembg) and composited; AI only makes backgrounds. Optional harmonize is opt-in and labeled.
- Text in images is rendered with real fonts as editable layers (never drawn by the image model).
- Mistral blocked: docs say API keys need billing. Gemini image generation blocked (needs billing).
- Frontend renders client-side only (local tool, no SEO) to avoid Suspense hydration mismatches.
- Web + API bind to 127.0.0.1 only (found Next.js exposed on the LAN by default during verification).

**Bugs found & fixed during verification**
- SQLite "database is locked": job progress used a second write connection inside a write transaction → in-memory live progress; commits before slow AI calls (regression test added).
- Heavy-job semaphore missing for inline execution; FFmpeg not found with stale PATH → `find_tool`.
- Alembic `%` interpolation with URL-encoded Windows paths; FK cycle (brands/projects ↔ assets).
- Image prompts > 77 CLIP tokens were silently truncated, dropping "empty surface/no text" → short, priority-ordered prompts.
- Product name in background prompt made SD-Turbo paint extra copies of the product → removed from background prompts.
- Hallucinated watermark text in backgrounds → automatic LaMa cleanup of edge text regions.
- Clipped contact-shadow tile produced a visible rectangle → padded shadow canvas.
- Small model ignored supplied reviews due to unconditional "if no reviews…" instruction → conditional rules.
- Editor: web fonts loaded before stylesheet → wait for CSS then `document.fonts.load`; Space-to-pan used a ref during render; tablet properties panel covered the toolbar; detached anchor export.
- `stop.ps1` left orphaned server processes → port-owner cleanup restricted to Shelfcraft's own command lines.

## 2026-11-13 — Phase 2 (Pixii parity)

**Added:** Create wizard, Scale (translate / apply playbooks), Playbooks + library, Labs (Title & Bullets bulk, Packaging ideas),
Listing grader, Ads studio, Recent work, image → layers, 360° spin from photos, offline voiceover, A+ seamless slices,
Amazon mobile preview, paste/ASIN import, public API `/v1` with keys, MCP server, team mode with roles and `-Lan`.

**Issues found & fixed**
- `rapidocr-onnxruntime` pulled `opencv-python` and the install aborted on a locked `cv2.pyd` → installed with `--no-deps` (OpenCV headless already present and verified).
- `mcp` 2.x renamed `FastMCP` → `MCPServer` (`mcp.server.mcpserver`).
- `start.ps1` exited 1: PowerShell 5.1 reads BOM-less UTF-8 as ANSI, so an em dash became a closing quote → all `.ps1` saved with BOM; `test.ps1` now parses every script and checks the BOM.
- Flaky E2E Ctrl+K test (palette opened before the client-only app mounted) → wait for the sidebar first.
- Docs/UI claimed SP-API is "free for sellers" without verification → reworded to "check Amazon's current developer terms".
