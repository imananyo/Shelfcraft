# User Flows

## A. Observed Pixii flows (reference, 2026-11-13)

1. **Create → Listings → Marketplace → Product → (Continue → generation, not observed)**
   Card picker → second card picker (marketplace) with breadcrumb → product picker (country, ASIN/URL, add images, or "Add a new product") → Continue.
2. **Create → A+ / Videos** — multi-select format cards with "N selected" counter and sticky Continue.
3. **Create → Amazon Ads** — single-select format cards labeled with exact pixel sizes.
4. **Products → Add product** — dialog: ASIN/URL, or manual stepper starting with Main Image (Cancel / Next).
5. **Brand Profile** — single long form, website "Scrape" auto-fill at top, sections Visual Identity / Brand Details. (Save behavior not observed — likely autosave; *inferred*.)
6. **Scale** — tool cards + run history; gated behind pricing modal on Free plan.
7. **Labs → Title & Bullets** — single/bulk tabs, ASIN input, Generate.

Pattern takeaways: progressive card-based wizards ("What should we work on?" → "Which … ?"), product selection is a shared step, every list page has a purposeful empty state with a single CTA.

## B. Shelfcraft flows (what we build)

### B1. First run
Dashboard shows checklist → **Create brand** (name, colors, fonts, logo, voice) → **Add product** (photos, details) → **Generate first listing**. Each checklist item is computed from DB state.

### B2. Listing builder
1. Choose marketplace (Amazon default; Shopify/Walmart/TikTok Shop enabled via rules config).
2. Choose product (or create inline) and brand (defaults to active brand).
3. Options: country, language, audience override, tone, keywords seed.
4. **Generate copy** → background job → title, bullets, description, keywords, search terms, image strategy. Each field editable, per-field regenerate, char-count vs marketplace limit, copy, save version, export (TXT/JSON/CSV).
5. **Generate image set** → queue 7 slots from the image strategy → each lands as an editable editor document.

### B3. Image generation
Pick product + creative type (white-bg main, hero, lifestyle, feature, detail, comparison, infographic, promo, social) + aspect/size + style + brand → prompt preview (editable) → job → results grid with provider/model attribution → regenerate / download / save to library / open in editor.

### B4. Editor
Open document (from generation, template or blank size preset) → layers panel / canvas / properties panel → edits autosaved (debounced) with version restore → export PNG/JPEG at preset dimensions.

### B5. Spot edit
Select image → paint mask → choose operation (remove object [LaMa], replace background [rembg + generated/solid/uploaded bg], generative fill [if a model is configured], enhance [non-AI, labeled]) → before/after slider → save as new asset or replace layer.

### B6. A+ builder
Choose A+ type (Basic / Premium) → add modules from library → drag to reorder → edit text & images per module (images can open in editor) → preview (desktop/mobile) → export ZIP of module PNGs + JSON copy.

### B7. Reference-guided creative ("Inspire")
Upload reference → analysis (palette, layout grid, text blocks, focal point) → pick product & brand → generate layout as an editable document using the analyzed composition (not copying content) → edit.

### B8. Factory (bulk)
Select products (+variants) → creative types → template → brand → preview job count & estimate → queue (capped) → live progress table → retry failed / cancel pending → download ZIP.

### B9. Video
Choose product → aspect (16:9 / 9:16 / 1:1) + duration → storyboard auto-built from product images (reorderable scenes, per-scene text overlay, duration, transition) → optional music upload → preview (browser) → render MP4 job (FFmpeg) → download / save to library.

### B10. Settings
Providers (enable, key presence, test connection, model, free-tier status, last error, usage) → local models (Ollama status, pull instructions) → defaults → storage path & usage → backup/restore → theme.
