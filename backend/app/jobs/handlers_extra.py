"""Job handlers for translate, packaging, ad concepts, playbooks, image→layers, 360° spin, voiceover video, bulk copy."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.ai.base import NoProviderAvailable, TextRequest
from app.db.models import Asset, CreativeSession, FactoryBatch, Notification, Product, Project
from app.db.session import session_scope
from app.jobs.queue import JobContext, PermanentJobError, job_handler
from app.services.assets import create_asset_from_bytes, load_image, register_file_asset


def _note(db: Any, title: str, link: str | None = None, body: str = "", level: str = "success") -> None:
    db.add(Notification(level=level, title=title, body=body[:500], link=link))


def make_listing(db: Any, product_id: str, brand_id: str | None, marketplace: str, options: dict[str, Any],
                 provider: str | None = None) -> Project:
    """Create a listing project and generate its copy synchronously (used by Factory, Playbooks, Labs bulk)."""
    from app.services.copywriting import generate_listing_copy
    from app.services.marketplaces import MARKETPLACES, validate_copy

    p = db.get(Product, product_id)
    if p is None:
        raise PermanentJobError("product not found")
    brand_id = brand_id or p.brand_id
    mk = MARKETPLACES.get(marketplace, MARKETPLACES["amazon"])
    proj = Project(kind="listing", name=f"{p.name} — {mk['label']}"[:200], product_id=p.id, brand_id=brand_id,
                   data={"marketplace": marketplace, "options": options})
    db.add(proj)
    db.flush()
    db.add(CreativeSession(project_id=proj.id, kind="listing", title=proj.name, params={"marketplace": marketplace}))
    db.commit()  # release the write lock before the (slow) LLM call
    copy_, prov, model = generate_listing_copy(db, p.id, brand_id, marketplace, options, provider=provider)
    proj = db.get(Project, proj.id)
    proj.data = {**proj.data, "copy": copy_, "warnings": validate_copy(marketplace, copy_), "provenance": {"provider": prov, "model": model}}
    return proj


@job_handler("listing_translate")
def h_translate(ctx: JobContext) -> dict[str, Any]:
    from app.services.growth import translate_listing

    p = ctx.payload
    try:
        with session_scope() as db:
            out = translate_listing(db, p["project_id"], p["language"], p.get("country", "US"),
                                    translate_images=p.get("translate_images", True), provider=p.get("provider"), progress=ctx.progress)
            _note(db, "Translated listing ready", f"/listings/{out['project_id']}")
            return out
    except (NoProviderAvailable, ValueError) as e:
        raise PermanentJobError(str(e)) from e


@job_handler("packaging_ideas")
def h_packaging(ctx: JobContext) -> dict[str, Any]:
    from app.services.growth import packaging_ideas

    p = ctx.payload
    try:
        with session_scope() as db:
            ideas = packaging_ideas(db, p["product_id"], count=p.get("count", 15), notes=p.get("notes", ""), provider=p.get("provider"))
            product = db.get(Product, p["product_id"])
            proj = Project(kind="packaging", name=f"Packaging ideas — {product.name}"[:200], product_id=product.id,
                           brand_id=product.brand_id, data=ideas)
            db.add(proj)
            db.flush()
            _note(db, "Packaging ideas ready", f"/labs/packaging?project={proj.id}")
            return {"project_id": proj.id, "count": len(ideas["concepts"]), "provider": ideas["provider"]}
    except (NoProviderAvailable, ValueError) as e:
        raise PermanentJobError(str(e)) from e


@job_handler("packaging_render", heavy=True)
def h_packaging_render(ctx: JobContext) -> dict[str, Any]:
    """Render a mock-up image for one packaging concept with the image model (clearly an AI concept render)."""
    from app.ai import fallback_manager as fm
    from app.ai.base import ImageRequest
    from app.imaging import ops

    p = ctx.payload
    with session_scope() as db:
        proj = db.get(Project, p["project_id"])
        if proj is None:
            raise PermanentJobError("packaging project not found")
        c = (proj.data or {}).get("concepts", [])[int(p["index"])]
        product_id = proj.product_id
    prompt = (f"product packaging design mockup, {c.get('structure', 'box')}, {c.get('materials', '')}, colors "
              f"{' '.join(c.get('palette', [])[:3])}, {c.get('big_idea', '')[:120]}, studio shot, plain background")
    try:
        res = fm.generate_image(ImageRequest(prompt=prompt[:600], width=768, height=768), purpose="packaging_render")
    except NoProviderAvailable as e:
        raise PermanentJobError(f"{e}. Enable Local diffusion or Cloudflare in Settings.") from e
    with session_scope() as db:
        a = create_asset_from_bytes(db, ops.to_png(ops.from_bytes(res.image_png).convert("RGB")), ext="png", source="generated",
                                    filename=f"packaging-{c.get('name', 'concept')}.png", title=f"Packaging concept — {c.get('name', '')}",
                                    product_id=product_id, project_id=p["project_id"], provider=res.provider, model=res.model,
                                    is_ai_generated=True, meta={"prompt": prompt, "note": "AI concept render — text and details are illustrative."})
        proj = db.get(Project, p["project_id"])
        renders = dict((proj.data or {}).get("renders") or {})
        renders[str(p["index"])] = a.id
        proj.data = {**proj.data, "renders": renders}
        return {"asset_id": a.id}


@job_handler("ad_concepts")
def h_ad_concepts(ctx: JobContext) -> dict[str, Any]:
    from app.services.growth import ad_concepts

    p = ctx.payload
    try:
        with session_scope() as db:
            out = ad_concepts(db, p["product_id"], count=p.get("count", 6), personas=p.get("personas"), goal=p.get("goal", "conversions"),
                              provider=p.get("provider"))
            proj = db.get(Project, p["project_id"])
            proj.data = {**(proj.data or {}), "concepts": out["concepts"], "personas": out["personas"],
                         "provenance": {"provider": out["provider"], "model": out["model"]}}
            _note(db, "Ad concepts ready", f"/ads/{proj.id}")
            return {"count": len(out["concepts"])}
    except (NoProviderAvailable, ValueError) as e:
        raise PermanentJobError(str(e)) from e


@job_handler("ad_render", heavy=True)
def h_ad_render(ctx: JobContext) -> dict[str, Any]:
    """Render one ad concept as an editable creative in the chosen format."""
    from app.services.creative import generate_creative
    from app.services.growth import AD_FORMATS

    p = ctx.payload
    with session_scope() as db:
        proj = db.get(Project, p["project_id"])
        c = (proj.data or {}).get("concepts", [])[int(p["index"])]
        fmt = AD_FORMATS.get((proj.data or {}).get("format", "sb_image"), AD_FORMATS["sb_image"])
        ctype = "ad_sb" if fmt["w"] / fmt["h"] > 1.5 else "social"
        try:
            out = generate_creative(db, product_id=proj.product_id, brand_id=proj.brand_id, creative_type=ctype, width=fmt["w"], height=fmt["h"],
                                    style=p.get("style", "vibrant"), extra_prompt=c.get("visual", ""), project_id=proj.id,
                                    copy={"headline": c.get("headline"), "subheadline": c.get("subheadline"), "cta": c.get("cta")},
                                    progress=ctx.progress)
        except (NoProviderAvailable, ValueError) as e:
            raise PermanentJobError(str(e)) from e
        renders = dict((proj.data or {}).get("renders") or {})
        renders[str(p["index"])] = {"asset_ids": out["asset_ids"], "document_id": out["document_id"]}
        proj.data = {**proj.data, "renders": renders}
        return out


@job_handler("decompose_image", heavy=True)
def h_decompose(ctx: JobContext) -> dict[str, Any]:
    from app.services.documents import create_document
    from app.services.media_extra import decompose_to_layers

    p = ctx.payload
    with session_scope() as db:
        src = db.get(Asset, p["asset_id"])
        if src is None or src.kind != "image":
            raise PermanentJobError("image not found")
        im = load_image(src)
        title = src.title or src.filename
        product_id = src.product_id
    ctx.progress(0.1, "Reading text (OCR) and finding the subject")
    doc, images, report = decompose_to_layers(im)
    ctx.progress(0.8, "Building editable layers")
    with session_scope() as db:
        ids = {}
        for name, data in images.items():
            a = create_asset_from_bytes(db, data, ext="png", source="edited", filename=f"{title}-{name}.png", title=f"{title} — {name}",
                                        product_id=product_id, provider="shelfcraft", model=f"OCR (RapidOCR) + rembg + {report['background_engine']}",
                                        is_ai_generated=True, meta={"operation": "decompose", "parent_asset_id": p["asset_id"]})
            ids[name] = a.id
        for layer in doc["layers"]:
            if layer["type"] == "image":
                layer["assetId"] = ids.get(layer["assetId"].strip("{}"))
        proj = Project(kind="design", name=f"Layers — {title}"[:200], product_id=product_id, data={})
        db.add(proj)
        db.flush()
        d = create_document(db, name=f"Layers — {title}", doc=doc, project_id=proj.id)
        return {"document_id": d.id, **report}


@job_handler("spin_video", heavy=True)
def h_spin(ctx: JobContext) -> dict[str, Any]:
    from app.services.media_extra import encode_frames, spin_frames
    from app.storage.local import get_storage

    p = ctx.payload
    with session_scope() as db:
        assets = [db.get(Asset, i) for i in p["asset_ids"]]
        if any(a is None or a.kind != "image" for a in assets) or len(assets) < 3:
            raise PermanentJobError("choose at least 3 photos taken from different angles, in order")
        ims = [load_image(a) for a in assets]  # type: ignore[arg-type]
        product_id = assets[0].product_id  # type: ignore[union-attr]
    ctx.progress(0.2, "Normalizing angle photos")
    frames = spin_frames(ims, size=int(p.get("size", 1080)), white=bool(p.get("white_background", True)), tween=int(p.get("tween", 3)))
    key, out = get_storage().new_path("videos", "mp4")
    ctx.progress(0.7, "Encoding MP4")
    dur = encode_frames(frames, out, fps=int(p.get("fps", 24)), loops=int(p.get("loops", 3)))
    with session_scope() as db:
        a = register_file_asset(db, key, kind="video", mime="video/mp4", filename="spin-360.mp4", source="export",
                                title=p.get("title") or "360° spin", product_id=product_id, provider="ffmpeg",
                                model="360° spin from your photos (non-generative)", meta={"operation": "spin", "frames": len(frames)})
        a.duration_s = dur
        _note(db, "360° spin video ready", f"/library?asset={a.id}")
        return {"asset_id": a.id, "duration_s": dur}


@job_handler("voiceover_video", heavy=True)
def h_voiceover(ctx: JobContext) -> dict[str, Any]:
    """AI-written script → offline TTS → slideshow with captions timed to the voice. No avatar."""
    from app.ai import fallback_manager as fm
    from app.services.copywriting import SYSTEM, product_facts
    from app.services.media_extra import concat_wavs, synthesize
    from app.services.video import render_video

    p = ctx.payload
    with session_scope() as db:
        proj = db.get(Project, p["project_id"])
        if proj is None:
            raise PermanentJobError("video project was deleted")
        product = db.get(Product, proj.product_id) if proj.product_id else None
        data = dict(proj.data or {})
        scenes = list(data.get("scenes") or [])
        if not scenes:
            raise PermanentJobError("add scenes first")
        facts = product_facts(product) if product else proj.name
    lines: list[str] = [s for s in (p.get("script") or []) if s.strip()]
    if not lines:
        ctx.progress(0.05, "Writing the voiceover script")
        try:
            res = fm.generate_text(TextRequest(
                prompt=(f"Write a {len(scenes)}-line voiceover for a short, friendly, creator-style product video. One short spoken "
                        f"sentence per line (max 14 words), first line is a hook, last line a soft call to action. Use only these facts:\n"
                        f"{facts}\nReturn JSON {{\"lines\": [\"...\"]}} with exactly {len(scenes)} lines."),
                system=SYSTEM, json_mode=True, temperature=0.7, max_tokens=600), purpose="voiceover_script")
            got = res.json().get("lines") if isinstance(res.json(), dict) else None
            lines = [str(x) for x in got][:len(scenes)] if isinstance(got, list) else []
        except NoProviderAvailable as e:
            raise PermanentJobError(f"{e}. Or type your own script.") from e
    if not lines:
        raise PermanentJobError("no script lines")
    while len(lines) < len(scenes):
        lines.append("")
    with tempfile.TemporaryDirectory(prefix="shelfcraft-vo-") as tmp:
        tmpd = Path(tmp)
        ctx.progress(0.2, "Recording voiceover (offline)")
        spoken = [(i, ln) for i, ln in enumerate(lines) if ln.strip()]
        parts = synthesize([ln for _, ln in spoken], tmpd, voice=p.get("voice", ""), rate=int(p.get("rate", 175)))
        gap = 0.35
        durs = {i: d + gap for (i, _), (_, d) in zip(spoken, parts)}
        for i, sc in enumerate(scenes):
            sc["duration"] = round(max(1.5, durs.get(i, 2.0)), 2)
            sc["text"] = lines[i][:200]
        voice_wav = tmpd / "voice.wav"
        concat_wavs(parts, gap, voice_wav)
        with session_scope() as db:
            ids = {s.get("asset_id") for s in scenes} | ({data["music_asset_id"]} if data.get("music_asset_id") else set())
            assets = {a.id: a for a in db.scalars(select(Asset).where(Asset.id.in_([i for i in ids if i])))}
            for a in assets.values():
                db.expunge(a)
        music = assets.get(data.get("music_asset_id") or "")
        key, total = render_video(scenes, aspect=data.get("aspect", "9:16"), transition="none" if p.get("hard_cuts", True) else data.get("transition", "fade"),
                                  transition_s=0.0, music=music, assets=assets, text_style=data.get("text_style") or {},
                                  progress=ctx.progress, voice_path=voice_wav)
    with session_scope() as db:
        a = register_file_asset(db, key, kind="video", mime="video/mp4", filename=f"{proj.name}-voiceover.mp4", source="export",
                                title=f"{proj.name} (voiceover)", product_id=proj.product_id, project_id=proj.id, provider="ffmpeg",
                                model="slideshow + offline TTS voiceover (no avatar)", is_ai_generated=True,
                                meta={"operation": "voiceover_video", "script": lines})
        a.duration_s = total
        proj = db.get(Project, p["project_id"])
        proj.data = {**proj.data, "scenes": scenes, "last_render_asset_id": a.id, "voiceover_script": lines}
        _note(db, "Voiceover video ready", f"/videos/{proj.id}")
        return {"asset_id": a.id, "duration_s": total, "lines": len(lines)}


@job_handler("playbook_step", heavy=True)
def h_playbook_step(ctx: JobContext) -> dict[str, Any]:
    from app.services.creative import generate_creative

    p = ctx.payload
    step: dict[str, Any] = p["step"]
    with session_scope() as db:
        batch = db.get(FactoryBatch, p["batch_id"])
        cfg = (batch.config if batch else {}) or {}
    kind = step["kind"]
    try:
        with session_scope() as db:
            product = db.get(Product, p["product_id"])
            if product is None:
                raise PermanentJobError("product not found")
            brand_id = cfg.get("brand_id") or product.brand_id
            if kind == "creative":
                return generate_creative(db, product_id=product.id, brand_id=brand_id, creative_type=step["creative_type"],
                                         width=int(step.get("width") or cfg.get("width") or 2000), height=int(step.get("height") or cfg.get("height") or 2000),
                                         style=step.get("style") or cfg.get("style", "minimal"), extra_prompt=step.get("extra_prompt", ""),
                                         progress=ctx.progress)
            if kind == "listing_copy":
                proj = make_listing(db, product.id, brand_id, step.get("marketplace") or cfg.get("marketplace", "amazon"),
                                    {"language": step.get("language", "en"), "country": step.get("country", "US")})
                return {"project_id": proj.id}
            if kind == "research":
                from app.services.copywriting import run_research

                r = run_research(db, product.id)
                return {"research_id": r.id}
            if kind == "packaging":
                from app.services.growth import packaging_ideas

                ideas = packaging_ideas(db, product.id, count=int(step.get("count", 8)))
                proj = Project(kind="packaging", name=f"Packaging ideas — {product.name}"[:200], product_id=product.id, data=ideas)
                db.add(proj)
                db.flush()
                return {"project_id": proj.id}
            if kind == "aplus":
                from app.routers.aplus import _add_module

                proj = Project(kind="aplus", name=f"A+ — {product.name}"[:200], product_id=product.id, brand_id=brand_id,
                               data={"tier": step.get("tier", "premium"), "modules": []})
                db.add(proj)
                db.flush()
                proj.data = {**proj.data, "modules": [_add_module(db, proj, m) for m in step.get("modules") or ["hero_banner", "feature_row", "comparison"]]}
                return {"project_id": proj.id}
            if kind == "video":
                from app.routers.videos import VideoIn, create_video

                v = create_video(VideoIn(name=f"{product.name} video", product_id=product.id, aspect=step.get("aspect", "16:9"),
                                         target_duration=float(step.get("duration", 15))), db)
                db.commit()
                job_type = "voiceover_video" if step.get("voiceover") else "video_render"
        if kind == "video":
            # Render inline (we are already inside a heavy worker slot).
            from app.jobs.handlers import h_video

            sub = JobContext(ctx.job_id, {"project_id": v["id"]})
            return h_voiceover(sub) if job_type == "voiceover_video" else h_video(sub)
        raise PermanentJobError(f"unsupported step {kind}")
    except (NoProviderAvailable, ValueError) as e:
        raise PermanentJobError(str(e)) from e


@job_handler("bulk_listing_copy")
def h_bulk_copy(ctx: JobContext) -> dict[str, Any]:
    p = ctx.payload
    try:
        with session_scope() as db:
            proj = make_listing(db, p["product_id"], p.get("brand_id"), p.get("marketplace", "amazon"),
                                {"language": p.get("language", "en"), "country": p.get("country", "US")}, provider=p.get("provider"))
            return {"project_id": proj.id, "title": (proj.data.get("copy") or {}).get("title")}
    except (NoProviderAvailable, ValueError) as e:
        raise PermanentJobError(str(e)) from e

