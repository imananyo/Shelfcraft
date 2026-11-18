# Feature Status

Status as of **2026-11-16**. "Verified" means exercised by automated tests and/or a real run with
the actual local models on this machine (see `TEST_REPORT.md`).

Legend: ✅ fully implemented · 🟡 implemented with limitations · 🔑 waiting for optional API configuration · ❌ not implemented

## Modules

| # | Module | Status | Notes |
|---|---|---|---|
| 1 | App shell & dashboard | ✅ | Collapsible sidebar (persisted), brand switcher, Ctrl+K search (products/brands/projects/assets/pages), live job tray, notifications, theme (light/dark/system), profile card. Dashboard: real counts, onboarding checklist computed from data, recent creatives/projects/products, job status, 30-day usage. |
| 2 | Brand workspace | ✅ | Multiple brands, logo upload, guideline docs (PDF/TXT/MD text extracted locally), colors (≤6), heading/body fonts, language, tagline, tone, audience, positioning, values, aesthetic, visual identity, marketing rules. Active brand is injected into every generation prompt and template. Website auto-fill reads public metadata only. |
| 3 | Product workspace | ✅ | CRUD, photos (upload, set main, remove), variants (attributes + color), specs, features/benefits, pricing, SKU/ASIN, categories, tags, search/filter/sort, grid/list, duplicate, CSV import (upsert by SKU, per-row errors) & export. |
| 3b | Import by ASIN / Walmart ID / URL | 🟡 | Listing builder + Products page. Reads the public Amazon/Walmart product page (title, bullets, description, price, brand, specs, up to 8 images, rating and reviews → auto Deep Strategy). One plain request; CAPTCHA/block pages are reported, never bypassed, and the product is still saved with its ID. May conflict with marketplace terms — enabled at the owner's request (2026-11-16). Amazon SP-API used instead when connected. **Blocked? Finish from your browser (2026-11-17):** open the page yourself, then upload the saved page (Ctrl+S) or paste its source (Ctrl+U); the placeholder product is filled in, including photos and reviews (`POST /api/products/import-html`; also a "From your browser" import tab). Verified with a real Walmart page: 10 bullets, 27 specs, 8 photos, 12 reviews → Deep Strategy. |
| 4 | AI product intelligence | ✅ | Personas, positioning, USPs, benefits from features, review sentiment, pain points, objections + answers, competitor gaps, marketing angles, creative strategy, explicit **assumptions** list, record of which inputs were used. Uses the counted review analysis (4b) and category analysis (4c) automatically when present; pasted text still works. Verified with Ollama qwen2.5:3b. |
| 4b | Review analysis (Reviews tab) | ✅ | Reviews stored per product with de-duplication, from saved Amazon/Walmart review pages (any star filter), store pages with schema.org reviews, CSV/TSV exports (Helium 10, Jungle Scout, Seller Central, spreadsheets) and pasted text. Exact stats without AI (stars, verified share, by variant, by month, recurring phrases). AI tags **every** review in batches of 12, groups tags into themes, and **code counts** mentions, share, average rating and picks real quotes; then pain points, objections, requests, listing & image advice. >400 reviews: rating-stratified sample (configurable to 2,000). Feeds listing copy ("voice of the customer"). |
| 4c | Category & competitors (Competitors tab) | ✅ | From pages you save in your own browser: Amazon Best Sellers lists, Amazon/Walmart search results (position, sponsored, badges, "bought in past month"), competitor product pages (bullets, image count, video, A+, Best Sellers Rank, reviews). Exact benchmark (price/rating/review/title-length distributions, shared title keywords and which ones your listing lacks, rich-content share). AI: counted competitor-review complaints across listings, title formula, patterns, weaknesses → opportunities, keywords (restricted to real missing terms). Feeds research and listing copy. Shelfcraft never crawls marketplaces itself. |
| 5 | AI listing builder | ✅ | Amazon / Shopify / Walmart / TikTok Shop; country & language; title, 5 bullets, description, keywords, search terms (byte count), benefits, feature explanations, image strategy, structure, recommendations, assumptions. Per-field regenerate with instructions, manual edit, versions + restore, copy, TXT/CSV/JSON export, length guidance (not compliance claims). |
| 6 | Main image generator | ✅ | White-bg main (rembg cut-out on pure white, ~85% fill), hero, lifestyle, studio, detail, promo, social, ad sizes; size presets; style; brand styling; prompt direction or full prompt; seed; count 1–4; provider choice; history; download; editable layered version of every result; provider/model attribution. |
| 7 | Lifestyle & infographics | ✅ | Real product photo composited (pixels untouched) onto AI backgrounds; optional opt-in "harmonize" pass (labeled as possibly altering details). Infographics (feature callouts, benefits, comparison, dimensions from specs, 3-step how-to) render text with real fonts as editable layers. Hallucinated edge text in AI backgrounds is auto-removed with LaMa. |
| 8 | A+ Content builder | ✅ | Basic / Premium / Premium-mobile; hero, four features, brand story, comparison, lifestyle, detail modules; drag-and-drop order; every module opens in the layered editor; stacked preview; ZIP export (JPEGs + modules.json with text). Dimensions labeled "verify in A+ Content Manager". |
| 9 | Visual editor (Konva) | ✅ | Text/image/rect/ellipse/line layers, move/resize/rotate (snap 45°), multi-select + marquee, duplicate, delete, opacity, fill/stroke/radius, fonts (Google Fonts), size/line-height/letter-spacing/align, layer panel (drag reorder, rename, lock, hide), bring/send, group/ungroup, align (canvas or selection), undo/redo (100 steps), zoom/pan, grid, smart guides, canvas resize + presets, background color/image, inline text editing, templates (add/replace), save as template, autosave (1.5 s) + local crash backup + version conflict handling, revision history + restore, PNG/JPEG at native size, WebP (server), save to library, JSON export/import. |
| 9b | Crop | 🟡 | Crop via left/top/right/bottom sliders in the Properties panel; no on-canvas crop handles. |
| 10 | Spot edit | ✅ / 🟡 | ✅ Remove background (rembg), replace background (color / your image / AI scene), remove object (LaMa, local AI), enhance, upscale 2×, recolor (non-AI, labeled), mask painting, before/after slider, keep & continue. 🟡 **Replace object (generative fill)** is experimental: LaMa clears the area, then SD-Turbo img2img fills it — no true inpainting model runs free on this CPU; quality varies. 🟡 **Extend** uses LaMa; good for plain/repetitive backgrounds only. |
| 11 | Reference-guided creative (Inspire) | ✅ | Palette (k-means), layout/grid, subject placement, whitespace, symmetry, heuristic text-region detection with overlay, optional vision-AI design notes (needs a vision-capable provider, e.g. Gemini), new editable layout with *your* product/brand/copy. Never copies the reference's pixels, text or identity. |
| 12 | Factory (bulk) | ✅ | Multi-product × variants × creative types, brand, template override, style, prompt; preview with count + CPU time estimate + warnings; hard cap 200 jobs/batch and back-pressure; persistent jobs; live progress; retry failed; cancel pending; ZIP download per product folder. One heavy job at a time on CPU. |
| 13 | Product video creator | ✅ | Auto storyboard from product photos & creatives; scene order (drag), duration, text overlay & position, Ken Burns motion; 16:9 / 9:16 / 1:1 / 4:5; transitions (xfade); your own music (trimmed + faded); in-browser preview (approximate); MP4 render (H.264, faststart). Labeled **composed, not AI-generated video**. |
| 13b | Generative video (talking UGC, 360°) | ❌ | No free model that runs usefully on this CPU; not offered rather than faked. |
| 14 | Asset library | ✅ | Uploads, generated, edited, exports, videos, audio, documents; search; type/source/AI filters; tags; folders (drag to file); favorites; preview drawer (image/video/audio); metadata & prompt; provenance chain ("view original"); download; bulk ZIP/move/delete. |
| 15 | Export & download center | ✅ | PNG/JPEG/WebP conversion with size presets and max-KB targeting (reports final dimensions & bytes), MP4, project/document JSON, product CSV, listing TXT/CSV/JSON, ZIPs (assets, A+, factory, project). Implemented inside Library, Editor, Listing, A+, Factory, Video rather than one separate page. |
| 16 | Settings & providers | ✅ | Provider cards (state: available/disabled/not configured/rate-limited/unavailable/blocked), keys (server-side only), models, test connection, last success/error, limits, licenses, privacy; defaults; fallback order; usage table; storage usage; health; backups; display name; access token. |

## Pixii-parity additions (2026-11-13, phase 2)

| Pixii feature | Status | Shelfcraft implementation |
|---|---|---|
| Studio / Catalog navigation, Create wizard (Listings · Amazon Ads · A+ · Videos · *or* Deep Strategy), Scale, Playbooks, Labs, Recent work | ✅ | Same information architecture, original Shelfcraft design. |
| Listings incl. **Amazon Mobile** | ✅ | `amazon_mobile` marketplace (80-char title guidance, mobile-sized visuals). |
| **Title & Bullets** (single + bulk run) | ✅ | Labs → Title & Bullets; bulk via `/listings/bulk` and Factory "Listing copy" type. |
| **Packaging Idea Generator** (15 concepts) | ✅ | Up to 15 concepts with palette, materials, structure, front-panel copy; optional AI mock-up render per concept. |
| **Deep Strategy** | ✅ | Create → Deep Strategy → Product intelligence (personas, gaps, objections, angles). |
| **Amazon Ads** (Sponsored Brand image/video, Sponsored Products video) + brainstorm/A-B/personas | ✅ | Ads studio: per-persona concepts with hypotheses, render A/B variants as editable creatives; video formats become captioned storyboards. |
| **A+ Seamless / Separate / Single** (Premium, Basic, Premium Mobile) | ✅ | Seamless = one continuous design exported as consecutive slices. |
| **Scale → Variant** | 🟡 | Per-variant runs with a non-AI hue shift. Changing size/flavor visually isn't automated. |
| **Scale → Translate** (1-click new market) | ✅ | New listing in the target language, including text inside images (re-rendered). |
| **Scale → Different Product** | ✅ | Apply finished designs to other products (photos, name, features, benefits swapped; layout kept). |
| **Scale → Steal the Look** | ✅ | Inspire (layout/palette/hierarchy analysis → new original layout). |
| **Playbooks** + template library + import | ✅ | 8 original templates (main image set, lifestyle trio, social/UGC-style kit, furniture lifestyle, full launch kit, multi-marketplace copy, EU expansion copy, A+ & brand story). Editor: playbook defaults (style, marketplace, image size), every step option (copy language/country, video length, A+ modules, packaging count), duplicate steps/playbooks, unsaved-changes guard + Ctrl+S, CPU time estimate, product search/select-all, recent runs with live progress. Steps are validated and cleaned server-side. |
| **Turn any image into editable layers** | ✅ / 🟡 | OCR (RapidOCR) → real text layers, subject cut-out, LaMa-rebuilt background. Fonts are approximated (Inter). |
| **Listing Grader** | ✅ | Transparent rule-based score + optional AI review; works on pasted listings or your own. |
| **Public API** | ✅ | `/v1` with API keys (hashed, scopes, 120 req/min), docs at `/v1/docs`. Local `/api` unchanged. |
| **MCP server** | ✅ | `backend/mcp_server.py` (12 tools) over the public API. |
| **Team / Invite members** | ✅ | Optional team mode: owner, invites (links), admin/editor/viewer roles, sign-in; `start.ps1 -Lan` for network access (only with team mode). |
| **ASIN / Walmart ID / URL import** | ✅ / 🟡 | See row 3b. Walmart verified live; when Amazon serves a CAPTCHA, the import is finished from the page you open in your own browser. |
| **Talking UGC (avatar) video** | 🟡 | **Voiceover video**: AI script + offline Windows voice + captions, no on-screen person (an avatar needs paid/GPU models). |
| **360° rotating video** | 🟡 | **360° spin from your angle photos** (real photos, FFmpeg). Not generated from a single image. |
| Reading reviews / studying the top of the category | ✅ / 🟡 | Reviews tab + Competitors tab (rows 4b, 4c): you save the review, Best Sellers, search and competitor pages in your browser; Shelfcraft analyses all of them. Not fully automatic (no crawling, by design). |
| "Trained on 100K top listings" | ❌ | Proprietary dataset; replaced by benchmarking the actual top listings of *your* category. |
| Plans, credits, billing | ❌ (by design) | Everything is free/local. |
| **Nano Banana / GPT models** (Pixii: "15+ models incl. Nano Banana and GPT") | ✅ opt-in | Paid providers `nano_banana` (Gemini image) and `openai` (GPT text + gpt-image-1, image edits). Locked behind Settings → "Allow paid providers" (off by default), your own key, and explicit selection per generation — never in the automatic free fallback chain. Not live-tested (needs a paid key). |
| **Share link** | ✅ | Share button on listing / A+ / video / project pages → no-login, read-only gallery at `/share/<token>`; revocable. |
| **Export to Figma / Illustrator / Canva** | ✅ | Editor → Export → SVG layers (vector shapes and real text stay editable; images embedded). No PSD. |
| **A+ desktop → mobile** | ✅ | A+ page → "Make mobile version": rebuilds modules at mobile sizes and carries over your edited text, colors and images by layer name. |
| **Keep prompting** | ✅ | Image studio → prompt box under results adds 2 more visuals to the same session. |
| **Session page tools** (Pixii `/campaign`, audited with REA 2026-11-16) | ✅ | Listing → Image set: grid/list layout, Select / Select all, bulk Download ZIP, Remove, Download all, **Add more visuals** (type + prompt, appended to the set); header shortcuts **Add A+ Content** and **Scale** next to Share. |
| **Product catalog bulk actions** | ✅ | Products: select all / per-item checkboxes → Write listings (bulk copy), Open Factory, Delete. |
| **Settings → Notifications** | ✅ | Mute finished-work / partial-result notices (errors always shown); optional Windows desktop pop-ups from the browser. |
| **Resources → Tutorials** | ✅ | Guides page (`/resources`): 10 searchable step-by-step walkthroughs with deep links. Written guides, not videos. |
| **MCP tools** (Pixii lists 18) | ✅ | 22 tools: adds import_product, create_listing_visuals, add_visuals, download_listing_visuals, list_recent_work, rename_recent_work, share_link, create_aplus, convert_a_plus_desktop_to_mobile, get_usage (each backed by a `/v1` endpoint). |
| Billing / plans / credits | ❌ (by design) | Local app; nothing is billed (paid models bill your own provider account). |

## Infrastructure

| Item | Status | Notes |
|---|---|---|
| Free-only provider layer | ✅ | Registry, adapters (Ollama, Gemini, Groq, OpenRouter `:free`, Cloudflare, local diffusion, Mistral-blocked), fallback chain, timeouts, bounded retries with backoff, Retry-After/429 handling, circuit breaker, usage & request logs without secrets. |
| Hosted providers live-tested | 🔑 | Adapters are implemented and unit-tested with fakes, but **no hosted key was configured**, so Gemini/Groq/OpenRouter/Cloudflare were not exercised against the real services. Add a key and use "Test connection". |
| Background jobs | ✅ | SQLite-backed persistent queue (no Redis/Celery needed), worker pool, heavy-job semaphore, idempotency keys, retries, cancellation, crash recovery on restart. |
| Database & migrations | ✅ | SQLite (WAL, FKs on) via SQLAlchemy 2 + Alembic. Soft delete on user content. |
| PostgreSQL | 🟡 | Models are portable and `SHELFCRAFT_DATABASE_URL` is supported, but PostgreSQL was **not tested**; API backups are SQLite-only. |
| Embeddings / vector search | ❌ | Not needed at this data size; `nomic-embed-text` is pulled and an `embed()` adapter exists, but no FAISS/Chroma retrieval feature is built. |
| Docker Compose | ❌ | Docker isn't installed on this machine and isn't required; native Windows scripts are provided instead. |
| Auth / multi-user | 🟡 | Single local user; optional access token; services bind to 127.0.0.1 only. Not multi-tenant (SaaS-ready structure, not SaaS-ready auth). |
| Phone layout | 🟡 | Desktop and tablet reviewed; phone works but is not a design target (editor is impractical on phones). |
| Packaging-idea generator, Amazon Ads brainstorming, 1-click "Translate" tool | ✅ | Built in phase 2 (see the Pixii-parity table above: Packaging Idea Generator, Amazon Ads studio, Scale → Translate). |

## Acceptance criteria (from the brief)

| # | Criterion | Result |
|---|---|---|
| 1 | Frontend starts | ✅ dev and production (`scripts\start.ps1 -Prod`) |
| 2 | Backend starts | ✅ |
| 3 | Migrations work | ✅ Alembic upgrade on every start |
| 4 | Dashboard loads real data | ✅ |
| 5 | Brand create/edit | ✅ (E2E) |
| 6 | Product create/edit | ✅ (E2E) |
| 7 | Product image upload | ✅ (E2E + API tests) |
| 8 | Listing generation with a real provider | ✅ Ollama qwen2.5:3b (real run) |
| 9 | Image generation via free provider / local model | ✅ local SD-Turbo (real run, ~30 s) |
| 10 | Local image editing | ✅ rembg, LaMa, OpenCV (real run + tests) |
| 11 | Editor real layer manipulation | ✅ (unit + E2E) |
| 12 | Projects persist after restart | ✅ (test + manual restart) |
| 13 | Asset downloads | ✅ |
| 14 | A+ create & export | ✅ |
| 15 | Bulk jobs queue & monitor | ✅ |
| 16 | Video exports valid file | ✅ MP4 verified with ffprobe |
| 17 | Provider failures don't crash | ✅ (fallback tests; app works with all AI off) |
| 18 | Paid APIs can't be called by fallback | ✅ (tests: unverified provider never called, paid model IDs rejected pre-network) |
| 19 | Keys not exposed to frontend | ✅ (API + E2E checks) |
| 20 | Main journeys pass automated tests | ✅ see TEST_REPORT.md |
| 21 | No dead navigation buttons | ✅ (E2E crawls every sidebar link) |
| 22 | No important page is a static placeholder | ✅ |
| 23 | UI reviewed at desktop & tablet | ✅ (screenshots + tablet E2E; editor tablet layout fixed) |
| 24 | Setup works on this Windows machine | ✅ start/stop scripts verified; `setup.ps1` steps were executed individually during the build (a full clean re-run on a fresh machine was not performed) |
