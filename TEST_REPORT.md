# Test Report

**Run date:** 2026-11-13 · **Machine:** Windows 11 Home, i7-1185G7, 15.7 GB RAM, no GPU
**Command:** `scripts\test.ps1 -E2E` against the production build started by `scripts\start.ps1 -Prod` → **exit code 0, all suites passed.**

## Summary

| Suite | Tool | Result |
|---|---|---|
| Backend unit/integration | pytest | **58 passed** (39 core + 19 phase-2 growth/API/MCP/team tests) |
| Frontend type-check | `tsc --noEmit` | **0 errors** |
| Frontend lint | ESLint (next core-web-vitals + TS) | **0 errors**, 26 warnings (`react-hooks/set-state-in-effect` intentionally downgraded — see `eslint.config.mjs`; 3 `window.location` navigations; 2 unused stub args in tests) |
| Frontend unit | Vitest | **13 passed** |
| End-to-end | Playwright (installed Chrome) | **15 passed** — 12 desktop (1440×900) + 3 tablet (834×1112) |
| Real-model smoke run | `backend\scripts\e2e_real.py` | **7 / 7 passed** (actual local models, no stubs) |
| Real-model smoke run, phase 2 | `backend\scripts\e2e_real_growth.py` | **4 / 4 passed** |

## Phase 2 (Pixii-parity) additions

**pytest (`tests/test_growth.py`, 19 tests):** listing grader (good vs bad listing, white-main-image detection, AI
review); translate listing copy and image text; bulk listing copy and the factory `listing_copy` type; packaging ideas;
ad concepts + render; playbook library import/edit/run; apply a design to a different product; image → layers (OCR);
360° spin from angle photos; voiceover video with offline TTS; A+ seamless module exports 3 slices of 1464×600;
paste-import parser; Amazon connector requires setup and never returns secrets; public API keys (no key → 401,
read scope can't write → 403, key not listed back, revoke → 401, `/v1/openapi.json`); MCP server tools registered and
calling `/v1`; team mode (owner setup, invite → accept, viewer can't write, logout, wrong password rejected).

Not unit-tested: the 120 req/min rate limit, the `amazon_mobile` preview, and the `-Lan` refusal in `start.ps1` (code path reviewed: it
reads `/api/auth/status` and keeps the web app on 127.0.0.1 unless team mode is on).

**New E2E journeys:** add a product inline from New listing; listing grader; import a playbook template; create an API
key → call `/v1` → revoke.

**Real-model run (`e2e_real_growth.py`):**

| Step | Engine | Time | Result |
|---|---|---|---|
| Translate listing to German | Ollama `qwen2.5:3b` | 68 s | ✅ "Hearth & Field Sage Stoneware Kaffeetasse 12 oz" |
| Packaging ideas | Ollama `qwen2.5:3b` | 100 s | ✅ 5 concepts |
| Ad concepts (Sponsored Brands image) | Ollama `qwen2.5:3b` | 48 s | ✅ 4 concepts |
| Voiceover video | Ollama script + Windows SAPI voice + FFmpeg | 16 s | ✅ 7 spoken lines, 16.5 s MP4 |

## Backend (pytest, 39 tests)

* **Core API (12):** health & capabilities; brand CRUD + validation; logo & guideline upload (text extraction); product CRUD, images, variants, CSV import (create/update/skip with errors) & export; disguised-file and oversize upload rejection; path-traversal blocking; asset library filters/favorites/folders/ZIP/format conversion with size & KB limits; **provider keys never returned by the API**; unverified provider can't be enabled; paid OpenRouter model rejected; dashboard & search; backup ZIP + backup path traversal; validation error shape.
* **AI fallback (10):** primary used when healthy; rate-limit → fallback + cooldown window respected; bounded retries (exactly 3 attempts) then circuit opens; **unverified/paid provider never called**; strict mode; all-providers-down raises a clear error and logs usage; OpenRouter rejects non-`:free` models before any network call; Gemini blocks image models; every registered provider is free-eligible or blocked; tolerant JSON parsing.
* **Job queue (4):** retry-then-success with attempt log; permanent failure + manual retry + cancel; crash recovery re-queues `running` jobs; idempotency keys.
* **Feature flows (13):** research + listing flow (generate, edit with length warnings, per-field regenerate, restore version, TXT/JSON/CSV export); **listing image set** built from the copy's image strategy; white-background main image uses the real cut-out (pure-white corners verified); composite without image AI is labeled non-AI and saved as an editable document; AI background path is attributed correctly **and doesn't lock the database** (regression test); infographic text layers contain no unresolved placeholders; editor persistence, optimistic version conflict (409), revisions, PNG/JPEG export sizes, JSON export/import, canvas-size validation; A+ create/reorder/add/preview/ZIP (4 JPEGs + manifest, 1464×600); factory preview/cap/back-pressure/run/ZIP; **MP4 export validated with ffprobe**; spot edits labeled AI vs non-AI (enhance, upscale, recolor, OpenCV inpaint, mask-required error, background replace via rembg); Inspire analysis + generation; persistence across engine re-init.

Text LLM calls in pytest use a deterministic fake so tests are fast and offline; background removal (rembg), compositing, rendering and FFmpeg are real.

## Frontend unit (Vitest, 13 tests)

Editor store: undo/redo, merged rapid edits, add/duplicate/delete (locked layers survive), group/ungroup with group selection, align to canvas & selection, z-order, autosave counter. Utilities & API client: byte/time formatting, provider labels, server error surfacing, unreachable-backend message, **no key/authorization headers ever sent**.

## End-to-end (Playwright, 11 tests)

| Test | Desktop | Tablet |
|---|---|---|
| Every main page renders without runtime/console errors (14 routes) | ✅ | ✅ |
| All sidebar links resolve (no dead navigation) | ✅ | ✅ |
| Ctrl+K search palette navigates | ✅ | ✅ |
| Create & edit a brand, persists after reload | ✅ | — |
| Add product with photo, edit, persists after reload | ✅ | — |
| Editor: add text & shape, undo/redo, autosave survives reload, PNG download | ✅ (also 5/5 on a repeat run) | — |
| Asset library: upload, favorite, filter | ✅ | — |
| Settings: unverified provider switch disabled; no key patterns in page HTML | ✅ | — |

## Real-model smoke run (`e2e_real.py`, final run)

| Step | Engine | Time | Result |
|---|---|---|---|
| Listing copy | Ollama `qwen2.5:3b` | 124 s | ✅ title + 5 bullets |
| Product research (with pasted reviews, after prompt fix) | Ollama `qwen2.5:3b` | ~100 s | ✅ sentiment from reviews: positive; themes extracted; assumptions listed |
| White-background main image | rembg U²-Net | 6 s | ✅ 2000×2000 |
| Lifestyle image (AI background + untouched product) | SD-Turbo (CPU) | 30 s | ✅ attributed `local_diffusion / stabilityai/sd-turbo` |
| Feature-callout infographic | template renderer | 3 s | ✅ editable document |
| Object removal | LaMa ONNX | 24 s | ✅ (`ai=True`) |
| Video render | FFmpeg | 15 s | ✅ 6.9 s MP4 |

## Issues found by testing and fixed

See `docs/DEVELOPMENT_LOG.md` (database lock under concurrent writes, CLIP prompt truncation, hallucinated
products/text in backgrounds, font loading, hydration mismatch, LAN exposure of the web server, orphaned
processes on stop, flaky export selection, and more). Every fix was re-verified by the runs above.

## Not covered by automated tests

* Hosted providers (Gemini, Groq, OpenRouter, Cloudflare) against the real services — **no keys configured**; adapters are covered with fakes.
* `generative_fill` (replace object) and `extend` image quality — code paths exist; output quality is model-dependent and was not formally evaluated.
* **Amazon SP-API import** against Amazon's real service — needs your own seller developer credentials; covered only with mocked HTTP.
* The MCP server inside a real MCP client (Claude Desktop / Claude Code) — tool registration and the `/v1` calls it makes are tested; the stdio session with a client was not.
* Team mode across two physical machines on a LAN (tested on one PC with two browser sessions' worth of cookies).
* PostgreSQL; a full clean `setup.ps1` run on a fresh machine; phone-sized layouts; long-duration soak tests.
