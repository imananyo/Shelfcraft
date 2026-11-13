# Free Resources

All entries verified on **2026-11-13** against the linked official pages. Free tiers change —
re-check before relying on any number. Shelfcraft refuses to use a provider whose free tier is not
verified (`free_tier_verified=False` cannot be enabled) and never purchases credits or upgrades plans.

## AI providers

| Provider | What it does in Shelfcraft | Local / hosted | Recurring free access verified? | Current limits (as documented) | Setup | License notes | Privacy |
|---|---|---|---|---|---|---|---|
| **Ollama** + `qwen2.5:3b` (default text), `nomic-embed-text` | Listing copy, research, regeneration | Local (CPU) | ✅ Yes — open source, no account | Hardware-bound: ~5–15 tokens/s on i7-1185G7; research ≈ 2–3 min | `winget install Ollama.Ollama`, `ollama pull qwen2.5:3b` | Ollama: MIT. qwen2.5:3b: Qwen Research License — check before commercial use (llama3.2 or other models can be configured) | Nothing leaves the PC |
| **Local diffusion** (diffusers, `stabilityai/sd-turbo`) | Backgrounds, scenes, img2img fill | Local (CPU) | ✅ Yes — open weights | Measured here: first load ~11 min incl. 2.5 GB download; then **27–36 s per 1024² composite** (512² native) | `scripts\install-local-image-model.ps1` | sd-turbo: Stability AI license — treat as personal/non-commercial until you verify the model card terms | Nothing leaves the PC |
| **rembg** (U²-Net) | Background removal / cut-outs | Local (CPU) | ✅ Yes | ~5–20 s per image on CPU | installed by `setup.ps1` (model auto-downloads ~170 MB) | rembg: MIT; U²-Net: Apache-2.0 | Local |
| **LaMa** (big-lama ONNX, Carve/LaMa-ONNX) | Object removal, extend, text-artifact cleanup | Local (CPU) | ✅ Yes | ~10–40 s per edit (512² inference on a crop) | auto-downloads ~200 MB on first use | Code/weights Apache-2.0; trained on Places — check dataset terms for commercial use | Local |
| **Google Gemini API** (AI Studio key) | Text + vision (Inspire design notes) | Hosted | ✅ Free tier exists ([rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)) | Per-project RPM/RPD/TPM shown in AI Studio; RPD resets midnight Pacific; Google calls the free tier best-effort | Key from AI Studio → Settings | Gemini API terms | **Free tier: Google may use prompts/outputs to improve products.** Image generation (Imagen) needs billing → **not used** |
| **Groq** | Fast text | Hosted | ✅ $0 Free plan ([rate limits](https://console.groq.com/docs/rate-limits)) | Per-model RPM/RPD/TPM in your console (docs pages disagree on exact numbers). Batch API is paid → not used | Key from console.groq.com | Model licenses vary (Llama, gpt-oss…) | Prompts sent to Groq; review its policy |
| **OpenRouter** (`:free` models only) | Text | Hosted | ✅ ([pricing](https://openrouter.ai/pricing)) | 20 req/min, **50 req/day** (1,000/day only after buying credits — Shelfcraft never does). Failed requests count | Key from openrouter.ai | Per-model | Some free endpoints may log/train on prompts |
| **Cloudflare Workers AI** | Text + `flux-1-schnell` images | Hosted | ✅ 10,000 Neurons/day on Workers Free ([pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)) | flux-1-schnell ≈ 4.8 Neurons/512² tile, 9.6/step; some heavy models return 403 on Free | Account ID + API token (stay on **Workers Free** so overage is impossible) | FLUX.1 [schnell]: Apache-2.0 | Prompts sent to Cloudflare |
| **Mistral** | (adapter only) | Hosted | ❌ **Not verified** — [usage-limits docs](https://docs.mistral.ai/admin/billing-usage/usage-limits) say API keys need billing activation | — | Blocked in UI and API | — | Free-tier training policy unclear |
| Cohere / trial-credit services | — | — | ❌ Trial/evaluation only — not integrated | — | — | — | — |

## Added in phase 2

| Component | What it does | Local / hosted | Free? | License | Privacy |
|---|---|---|---|---|---|
| **RapidOCR** (`rapidocr-onnxruntime`, PaddleOCR models in ONNX) | Reads text for *Image → Layers* | Local (CPU) | ✅ | Apache-2.0 | Local |
| **Windows SAPI voices** via `pyttsx3` | Offline voiceover narration | Local | ✅ built into Windows (voices found here: Microsoft David, Zira) | pyttsx3 MPL-2.0; voices per Windows license | Local |
| **MCP Python SDK** (`mcp` 2.x) | MCP server for AI assistants | Local | ✅ | MIT | Local (talks to your Shelfcraft only) |
| **Amazon Selling Partner API** (Catalog Items) | Optional ASIN import of *your* listings | Hosted (Amazon) | ⚠️ **Not verified in this build** — believed to be no-cost for sellers using their own data, but check Amazon's current SP-API developer terms before enabling. Off by default; requires your own developer registration. | Amazon SP-API terms | Sends ASIN + your credentials to Amazon only |

## Non-AI open-source components

| Component | Purpose | License |
|---|---|---|
| FFmpeg 9 (gyan.dev build) | Video composition / encoding | GPL/LGPL build — used as an external program |
| Pillow, OpenCV (headless), NumPy, scikit-learn | Imaging, compositing, palette & layout analysis | HPND / Apache-2.0 / BSD |
| FastAPI, SQLAlchemy, Alembic, Pydantic, httpx | Backend | MIT / BSD |
| Next.js, React, Tailwind CSS, Radix UI, Konva, dnd-kit, TanStack Query, Zustand, lucide | Frontend | MIT / ISC |
| Google Fonts (Geist, Bricolage Grotesque, brand fonts) | UI and editor typography (fetched from fonts.googleapis.com / google/fonts repo) | SIL OFL / Apache-2.0 |
| SQLite | Database | Public domain |

## Hardware notes (this machine)

i7-1185G7 (4C/8T), 15.7 GB RAM, Intel Iris Xe (no CUDA). Larger local image models (SDXL base,
FLUX) are **not** offered: they would take many minutes per image or exceed memory on CPU.
Shelfcraft instead composites your real product photo onto fast SD-Turbo backgrounds, which also
guarantees the product itself is never altered.
