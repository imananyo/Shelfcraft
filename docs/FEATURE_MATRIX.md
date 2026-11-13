# Feature Matrix — Pixii reference vs. Shelfcraft plan

Legend — **Pixii evidence**: O = observed in app, A = advertised on public site, I = inferred, N = not accessible.
**Shelfcraft plan** describes what we build and *how*, given zero paid APIs and this machine (i7-1185G7 CPU, 16 GB RAM, no CUDA GPU).
Actual delivery status lives in `FEATURE_STATUS.md` (updated as we build).

| Area | Pixii capability | Evidence | Shelfcraft implementation plan |
|---|---|---|---|
| Shell | Sidebar w/ brand switcher, search, Studio/Catalog groups, recent work, plan card | O | Same IA pattern with original design: brand switcher, ⌘K search, groups *Create / Library / Catalog / System*, recent work, local profile card (no plans/upsells). |
| Shell | Get Started checklist (0/3) | O | Onboarding checklist driven by real data (brand created, product added, first generation). |
| Dashboard | — (Create page is the home) | O | Real dashboard: recent projects/assets, job status, usage per provider, brand & product counts. |
| Brand profile | URL scrape auto-fill | O (not run) | Best-effort fetch of *public* homepage meta (title, description, theme-color, og:image, CSS colors) → LLM summary. No auth bypass. |
| Brand profile | Logo, font, colors (≤4), language, tagline, tone, audience, values (≤6), aesthetic (≤6), extra details | O | Same fields + guideline document upload (PDF/TXT/MD text extraction), positioning, marketing rules, multiple brands. |
| Products | Catalog with search/filter/sort; add via ASIN/URL or manual (image-first) | O | Full CRUD, images, variants, SKU, price, specs, features/benefits, categories, CSV import/export, URL metadata fetch (public pages only). |
| Listings | Amazon/Shopify/TikTok/Walmart/Amazon Mobile "7 editable visuals"; Main Images | O (selection) / N (output) | Listing builder: text (title, bullets, description, keywords) via LLM + **7-slot image plan** (main, lifestyle, infographic ×N, comparison, detail) generated as editable layered documents. Amazon first; marketplace rules as config. |
| Title & Bullets | ASIN → optimized title (≤75 chars notice), highlights, 5 bullets | O | Included in listing builder with character-limit validation per marketplace (limits documented as "verify on Seller Central"). |
| Deep Strategy | Customer insights & competitor gaps | O (entry) / A | Product Intelligence workspace: personas, pains, objections, USPs, angles from user-provided description/reviews/competitor text. Assumptions labeled. |
| Main/lifestyle/infographic images | Push-button listing images | A | Image generator: local SD-Turbo (CPU) and/or verified-free hosted provider; background removal (rembg/U²-Net) + compositing of the **real product photo** on generated backgrounds so the product is not altered; text rendered as vector layers, not by the model. |
| Editor | Fully editable layers, spot edit, image → layers | A / N | Konva-based editor: layers, text, shapes, images, crop, group, lock, undo/redo, zoom, guides, autosave, PNG/JPEG export. Spot edit: mask + LaMa inpaint (object removal, local ONNX) and generative inpaint where a model is available. |
| A+ Content | Premium/Basic/Premium Mobile; seamless/separate/single modules | O (selection) | A+ builder with module library, drag-and-drop ordering, editable text/images, preview, PNG/ZIP export. Dimension presets marked *verify on Seller Central*. |
| Amazon Ads | Sponsored Brand Image 1200×628; SB Video / SP Video 1920×1080·10 s | O | Ad creative presets in image generator + video creator (slideshow pipeline). |
| Videos | Listing, UGC, 360, Sponsored, Reels | O (selection) / A | FFmpeg slideshow composer: storyboard, scenes, text overlays, transitions, user music, 16:9/9:16/1:1, MP4. **Labeled "composed video", not generative.** Talking UGC / 360 → not implemented (no free local model that runs on this CPU). |
| Scale: Variant / Translate / Different Product | Bulk transforms | O (gated) | Factory: bulk queue over products × creative types × templates; translation via LLM; variant recolor via local image ops. Bounded concurrency, retry, cancel, ZIP. |
| Steal the Look | Inspiration from reference visuals | O (gated) | Reference-guided workflow: palette extraction (k-means), layout/text-hierarchy analysis (OpenCV + optional vision LLM), re-composition with *user's* product & brand. |
| Playbooks | Reusable templates (Main Images, Lifestyle, UGC, Furniture Lifestyle) | O | Templates: saved editor documents + generation presets, importable/duplicable. |
| Packaging ideas | 15 packaging concepts | O (entry) | Stretch: LLM concept list + optional image generation per concept. |
| Recent work / sessions | Searchable session history | O | Creative sessions + asset library with search, tags, folders, favorites. |
| API/MCP | Public API & MCP | A | Out of scope (local REST API exists; documented). |
| Billing / credits | Plans, credits, $749/mo Scale | O | **None.** Usage counters per provider only. |
