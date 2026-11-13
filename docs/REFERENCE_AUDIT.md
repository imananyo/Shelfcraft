# Reference Audit — Pixii.ai

**Audit date:** 2026-11-13
**Auditor:** Claude Code (Opus 5.5) on behalf of the repository owner
**Authorization:** Repository owner's own Pixii workspace (Free Plan), logged in manually by the owner in an isolated debug-Chrome profile. No credentials, cookies or tokens were requested, read or stored.

## Scope and method

| Target | Method | Notes |
|---|---|---|
| `https://platform.pixii.ai/*` (authenticated) | REA `list_browser_targets` + `inspect_web_page` (passive accessibility/DOM capture), then a custom read-only CDP script (`Page.navigate`, `Runtime.evaluate` for visible text/links/computed styles, `Page.captureScreenshot`, real mouse clicks on *opener* controls only) | Viewport 1440×900. A deny-list prevented clicks on Generate / Scrape / Upgrade / Save / New Project / Start a Run / Invite / payment controls. **No generation was triggered and no credits were spent.** |
| `https://www.pixii.ai/` (public) | Same CDP script, navigation only | Used to record *advertised* capabilities. |

### Tooling limitations (honest record)

- REA `inspect_web_page` succeeded (evidence `ev_ba1e3540…`, target list) and returned the full accessibility tree of `/listing-builder`. DOM/script sections were policy-filtered by REA's default origin scope.
- REA `capture_web_screenshot` timed out (CDP `Page.captureScreenshot` > 20 s) while the window was backgrounded.
- REA `capture_browser_scenario` could not be used: its action/capture schema is not published in the connected server's compact schema or the CLI manifest, and guessed field names were rejected (`capture: Unrecognized key`). REA `search_guidance` returned an output-schema error.
- Workaround: a ~120-line read-only CDP script (kept outside the repo) performed navigation, extraction and screenshots. Screenshots are in `docs/reference/screenshots/` **for internal reference only — they are not shipped in the app or used as assets.**

## Evidence classification

- **Observed** — seen directly in the authenticated UI.
- **Advertised** — stated on the public website, not verified in the app.
- **Inferred** — reasoned from observed behavior / CSS / markup; not confirmed.
- **Not accessible** — gated by plan, or reachable only by creating data / spending credits.

## Observed: application shell

- Left sidebar, **255 px** wide, same background as page (no contrasting rail). Sections:
  - Header: brand avatar + **brand switcher** ("Brand 1", chevron) + **Search** icon button.
  - **Studio**: Create (`/listing-builder`), Scale (`/scale`, ✦ premium marker), Playbooks (`/custom-plans`, ✦), Pixii Labs (`/labs`).
  - **Catalog**: Brand Profile (`/brandProfile`, ✦), Products (`/products`).
  - **Recent Work** (collapsible) with grid-view icon and "View all" → `/sessions`.
  - Footer: user avatar, name, plan label ("Free Plan"), **Upgrade** button.
- Top bar (48 px): sidebar toggle (left), **Upgrade** pill (center, tinted primary), **Invite**, **Get Started** checklist ("0 of 3 steps done").
- Floating chat-widget iframe (third-party support chat).
- Notifications region (`alt+T` toast region — inferred to be a Sonner-style toaster).

## Observed: pages

| Route | Title | What is there |
|---|---|---|
| `/listing-builder` (**Create**) | "What should we work on?" | 5 option cards in a 2-col grid: **Listings** (Amazon, Shopify, TikTok Shop, Walmart), **Amazon Ads** (Product, Brand, Display), **A+ Content** (Premium Desktop & Mobile, Basic), **Videos** (UGC, 360, Sponsored, Reels, Listing); divider "or"; **Deep Strategy** (Customer insights and competitor gaps). Bottom upsell card "Unlock the power". |
| Create → Listings | "Which listing should we work on?" | Amazon / Shopify / TikTok Shop / Walmart (each "7 editable visuals"), Amazon Mobile ("7 mobile optimized visuals"), Main Images ("7 main images"). Breadcrumb "Listings / Amazon". |
| Create → Listings → Amazon (also Main Images, Deep Strategy) | "Which product to generate for?" | Marketplace country selector (🇺🇸 US), input "Amazon ASIN, Walmart ID or product URL", **Add images (Recommended)**, **Continue**; "or" **Add a new product** ("Not listed on Amazon? Add its photo and details."). |
| Create → Amazon Ads | "Which format should we work on?" | Sponsored Brand Image (1200×628), Sponsored Brand Video (1920×1080, 10 s), Sponsored Products Video (1920×1080, 10 s). |
| Create → A+ Content | "Which A+ content should we work on?" | Groups **Premium**, **Basic**, **Premium Mobile**; each with Seamless Modules (one continuous image), Separate Modules (6 standalone), Single Module. Multi-select with "N selected" counter + Continue. |
| Create → Videos | "Which format should we work on?" | Amazon: Listing Video 16:9·10 s, Talking UGC 9:16·10 s, 360 Rotating 16:9·10 s, Sponsored Products 16:9·10 s. Instagram: Talking UGC 9:16, Reels Ad 9:16·10 s. Selectable cards, counter, Continue. |
| `/scale` | "Tools" | Cards: **Variant** (swap color, size, or flavor), **Translate** (adapt listing for a new market), **Different Product** (apply one…), **Steal the Look** (take inspiration from visuals you love). "My Runs (0)" empty state, "Start a Run" split button. Clicking any tool on Free plan opens a **pricing modal** (Growth / Scale / Enterprise; "Start Scale at $749/mo"; 20 brands · 10 members · 17,600 credits). |
| `/custom-plans` (**Playbooks**) | — | Empty state "No Playbooks Yet"; buttons Playbook Templates, New Playbook. Templates dialog lists: Amazon Main Images, Lifestyle, UGC, Furniture Lifestyle (each "Import"). |
| `/labs` | "Pixii Labs" | Cards: **Title & Bullets**, **Packaging Idea Generator** (15 packaging concepts), **Projects** (Create a design from scratch). |
| `/labs/title-bullets` | "Title & Bullets" | Tabs Single ASIN / Bulk run; country flag; input "Amazon ASIN, Walmart ID or product URL"; Generate. Notice: "Title must be 75 characters max". "How Pixii does it": optimized for Alexa/ChatGPT/mobile; analyzes customers, reviews, uniqueness; generates title, highlights, bullets. |
| `/labs/packaging` | "Which product should we work on?" | Same product-picker pattern as listings + "Generate packaging ideas". |
| `/projects` | — | Empty state "No projects yet" + New Project. |
| `/brandProfile` | "Brand Profile" | Website URL + **Scrape** ("auto-fill your profile"); info callout "State of the art AI models can not do 100% brand accuracy"; **Visual Identity**: logo upload tile, Primary Font (searchable combobox), Brand Colors (max 4, swatch tiles); **Brand Details**: Language select, Tagline, Tone of Voice, Target Audience (textarea), Brand Values (chips, max 6, Enter to add), Brand Aesthetic (chips, max 6), Extra Details (textarea). |
| `/products` | "Product Catalog" | Count ("0 products"), search, filter, sort, **Add product** split button, empty state + "Create a listing". Add Product dialog: country + ASIN/URL input, or **Add Product Details manually** → step form starting with **Main Image**, Cancel / Next. |
| `/sessions` | "Recent works" | Search sessions input; empty state "Generate your first listing visuals and they will show up here." |

## Advertised (public site, not verified in app)

- "Paste an ASIN… reads your reviews, sizes up your comparables, studies the top 5% of your category, then designs the listing" (main image, lifestyle images, infographics; A+ modules; listing videos).
- "Every design is fully editable. Break any image into layers… or fix one detail with a **spot edit**." "Turn an image into editable layers, like in Canva."
- On-brand fonts, colors, voice. Variants, 1-click translations, scale to 1,000 products.
- Amazon, Shopify, Walmart, TikTok Shop; "compliant with each platform's rules".
- Amazon Ads: brainstorm/A-B test, personas. Videos: UGC-style, benefit-led explainers, listing videos.
- "Trained on 100K top listings". API and MCP server. Listing Grader (separate site).
- Marketing claims (+30% revenue, 100× cheaper) — **not verifiable; not reproduced as claims in our app.**

## Not accessible during audit

- The **editor** (layers, spot edit) — only reachable after generating or creating a project (would create data / spend credits).
- Generation results, loading/progress states, error states for generation.
- All Scale tools (plan-gated), A+ generation (plan-gated per upsell copy), Playbook editing.
- Responsive/tablet behavior was not exercised (desktop 1440×900 only).
- Dark mode: CSS defines a `.dark` token set (**inferred** support); no toggle observed.

## Inferred technical stack (from computed CSS only)

- Design tokens named exactly like **shadcn/ui** (`--background`, `--card`, `--sidebar-*`, `--chart-1..5`), values in **oklch** → Tailwind CSS v4 + shadcn/ui (inferred).
- Fonts: **Switzer** (body) and **Cabinet Grotesk** (headings), both from Fontshare (inferred from family names).
- Primary: `oklch(62% .166 38.2)` (warm orange); AI gradient orange → magenta; neutral cool grays (hue 240); `--radius: .75rem`; inputs radius 16 px, 36 px tall.

No source code, private API, asset, logo or image from Pixii is used in Shelfcraft.
