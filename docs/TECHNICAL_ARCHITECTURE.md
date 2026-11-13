# Technical Architecture

## Constraints that shaped it
- Windows 11 Home, i7-1185G7 (4C/8T), 15.7 GB RAM, Intel Iris Xe — **no CUDA**. Local diffusion is CPU-only → favor few-step models (SD-Turbo class) at ≤ 512–768 px, and composite real product photos rather than regenerating products.
- No Docker installed → no Redis/Celery. A persistent SQLite-backed job queue with an in-process worker pool is simpler and sufficient for one user.
- Python 3.15 is the system default; ML wheels (onnxruntime, opencv, torch) target ≤ 3.12/3.13 → backend venv uses **Python 3.12**.
- Zero paid APIs. Every hosted provider is opt-in, key-gated, and flagged `free_tier_verified` with a verification date.

## Overview

```
 Browser (Next.js 15 · React 19 · TS · Tailwind v4 · Radix · Konva)
        │  same-origin /api/* (Next rewrites → FastAPI)   ← API keys never reach the browser
        ▼
 FastAPI (Python 3.12) ─────────────────────────────────────────────
   routers/        brands, products, research, listings, images, edits,
                   aplus, editor, inspire, factory, videos, assets,
                   exports, providers, settings, jobs, system
   services/       domain logic (one module per feature)
   ai/             provider registry + adapters + fallback + usage
   imaging/        Pillow/OpenCV ops, rembg, LaMa inpaint, compositing, palette
   video/          FFmpeg command builder (argument lists, never shell strings)
   jobs/           persistent queue, worker pool, retry/backoff, recovery
   storage/        StorageBackend interface → LocalStorage (data/media/…)
   db/             SQLAlchemy 2 models, Alembic migrations, SQLite (WAL)
        │
        ├── SQLite  data/shelfcraft.db
        ├── Files   data/media/{uploads,generated,exports,videos,thumbs}
        └── Local AI: Ollama (http://127.0.0.1:11434), ONNX models in data/models
```

## Key decisions
| Decision | Choice | Why |
|---|---|---|
| Frontend | Next.js (App Router) + TS + Tailwind v4 + Radix/shadcn-style components | Requested; mature; SSR not needed but routing/DX is. |
| Canvas | **Konva** (react-konva) | Declarative React layer model maps cleanly to persisted layer JSON; Transformer handles move/resize/rotate. |
| Backend | FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic | Requested; typed; async-friendly. |
| DB | SQLite (WAL, foreign keys ON) | Single user, zero ops; Postgres-compatible models for later. |
| Jobs | DB table `jobs` + `job_attempts`, `ThreadPoolExecutor` workers (default 2; image jobs limited to 1 on CPU), claim via atomic UPDATE, startup recovery sets stale `running` → `queued` | No Redis/Docker; survives restarts. |
| Text AI | Adapters: Ollama (default, local), Gemini, Groq, OpenRouter (`:free` models only), Mistral, Cloudflare Workers AI | Free-only; registry + fallback chain. |
| Image AI | Local SD-Turbo via diffusers on CPU (optional install), Cloudflare Workers AI image models (if free allocation verified), compositing pipeline that always works | Honest given hardware. |
| Editing AI | rembg (U²-Net, MIT) for background removal; LaMa ONNX (Apache-2.0) for object removal; OpenCV Telea inpaint as labeled non-AI fallback | Runs on CPU. |
| Video | FFmpeg via subprocess arg lists | Reliable, free, already installed. |
| Auth | Single local user; optional access token (`SHELFCRAFT_ACCESS_TOKEN`) required by API when set; server binds 127.0.0.1 | Personal MVP with sensible protection. |

## Provider selection & fallback
1. Requested provider (or user's default) if enabled, free-eligible, circuit closed.
2. Next enabled **free** provider in the user's ordered fallback list.
3. Local provider (Ollama / local image model).
4. Fail with a typed error → UI shows reason + retry; the rest of the app keeps working.

Paid usage is structurally impossible: adapters only accept model IDs from an allow-list marked free (e.g., OpenRouter IDs must end with `:free`), and providers whose `free_tier_verified` is false cannot be enabled for fallback. Retries: max 3, exponential backoff with jitter, honor `Retry-After`; circuit opens after 3 consecutive failures for 5 min. Logs redact keys.

## Data model (summary)
users, user_settings, brands, brand_guidelines, products, product_variants, product_images, product_research, projects, creative_sessions, assets (+tags, folders, favorites), templates, editor_documents, editor_layers (snapshot JSON + normalized layer rows), aplus_documents, provider_configs, generation_requests, jobs, job_attempts, usage_records, export_records, audit_events. Soft delete (`deleted_at`) on user content.

## Security
Keys only in `backend/.env` / DB (never serialized to the client — API returns `has_key: bool`), uploads validated by magic bytes + size limits, UUID filenames, storage paths resolved and checked under the media root (no traversal), ORM-only queries, user HTML sanitized (bleach) where rendered, FFmpeg called with argument lists only, CORS locked to the frontend origin, optional access token.
