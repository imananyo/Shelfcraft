"""Job handlers. Each runs in a worker thread with its own DB session and reports progress."""
from __future__ import annotations

import threading
from typing import Any

from sqlalchemy import select

from app.ai.base import NoProviderAvailable
from app.db.models import Asset, CreativeSession, EditorDocument, FactoryBatch, Notification, Project
from app.db.session import session_scope
from app.imaging import ops
from app.imaging.render import render_png
from app.jobs.queue import JobContext, PermanentJobError, job_handler
from app.services.assets import create_asset_from_bytes, load_image, register_file_asset


def _notify(db: Any, title: str, body: str = "", link: str | None = None, level: str = "success") -> None:
    """In-app notification, honouring Settings → Notifications (errors are always shown)."""
    from app.db.models import UserSettings

    s = db.query(UserSettings).first()
    prefs = ((s.generation_defaults or {}).get("notify") if s else None) or {}
    if level == "success" and prefs.get("success") is False:
        return
    if level == "warning" and prefs.get("warning") is False:
        return
    db.add(Notification(level=level, title=title, body=body[:500], link=link))


@job_handler("product_research")
def h_research(ctx: JobContext) -> dict[str, Any]:
    from app.services.copywriting import run_research

    p = ctx.payload
    ctx.progress(0.1, "Analyzing product")
    try:
        with session_scope() as db:
            r = run_research(db, p["product_id"], reviews=p.get("reviews", ""), competitors=p.get("competitors", ""),
                             notes=p.get("notes", ""), provider=p.get("provider"))
            _notify(db, "Product research ready", link=f"/products/{p['product_id']}?tab=intelligence")
            return {"research_id": r.id, "provider": r.provider, "model": r.model}
    except NoProviderAvailable as e:
        raise PermanentJobError(str(e)) from e
    except ValueError as e:
        raise PermanentJobError(str(e)) from e


@job_handler("review_analysis")
def h_review_analysis(ctx: JobContext) -> dict[str, Any]:
    from app.services.review_analysis import analyze_product_reviews

    p = ctx.payload
    ctx.progress(0.02, "Loading reviews")
    try:
        rid = analyze_product_reviews(p["product_id"], provider=p.get("provider"), max_reviews=int(p.get("max_reviews") or 400),
                                      progress=ctx.progress)
    except ValueError as e:
        raise PermanentJobError(str(e)) from e
    with session_scope() as db:
        _notify(db, "Review analysis ready", link=f"/products/{p['product_id']}?tab=reviews")
    return {"research_id": rid}


@job_handler("category_analysis")
def h_category_analysis(ctx: JobContext) -> dict[str, Any]:
    from app.services.category_analysis import analyze_category

    p = ctx.payload
    ctx.progress(0.02, "Loading top listings")
    try:
        rid = analyze_category(p["product_id"], provider=p.get("provider"), max_reviews=int(p.get("max_reviews") or 0),
                               progress=ctx.progress)
    except ValueError as e:
        raise PermanentJobError(str(e)) from e
    with session_scope() as db:
        _notify(db, "Category analysis ready", link=f"/products/{p['product_id']}?tab=competitors")
    return {"research_id": rid}


@job_handler("listing_copy")
def h_listing_copy(ctx: JobContext) -> dict[str, Any]:
    from app.services.copywriting import generate_listing_copy
    from app.services.marketplaces import validate_copy

    p = ctx.payload
    ctx.progress(0.1, "Writing listing copy")
    try:
        with session_scope() as db:
            proj = db.get(Project, p["project_id"])
            if proj is None:
                raise PermanentJobError("listing project was deleted")
            data = dict(proj.data or {})
            current = data.get("copy") or {}
            new, provider, model = generate_listing_copy(
                db, proj.product_id, proj.brand_id, data.get("marketplace", "amazon"), data.get("options", {}),
                field=p.get("field"), current=current, provider=p.get("provider"))
            merged = {**current, **new} if p.get("field") else new
            versions = list(data.get("versions") or [])
            if current:
                versions.append({"copy": current, "provenance": data.get("provenance")})
            data.update({"copy": merged, "versions": versions[-20:], "warnings":
                         validate_copy(data.get("marketplace", "amazon"), merged),
                         "provenance": {"provider": provider, "model": model, "field": p.get("field")}})
            proj.data = data
            _notify(db, f"Listing copy ready — {proj.name}", link=f"/listings/{proj.id}")
            return {"project_id": proj.id, "provider": provider, "model": model}
    except NoProviderAvailable as e:
        raise PermanentJobError(str(e)) from e
    except ValueError as e:
        raise PermanentJobError(str(e)) from e


@job_handler("image_generate", heavy=True)
def h_image_generate(ctx: JobContext) -> dict[str, Any]:
    from app.services.creative import generate_creative

    p = ctx.payload
    try:
        with session_scope() as db:
            out = generate_creative(
                db, product_id=p.get("product_id"), brand_id=p.get("brand_id"), creative_type=p["creative_type"],
                width=int(p.get("width", 1024)), height=int(p.get("height", 1024)), style=p.get("style", "minimal"),
                prompt_override=p.get("prompt"), extra_prompt=p.get("extra_prompt", ""), provider=p.get("provider"),
                seed=p.get("seed"), harmonize=bool(p.get("harmonize")), copy=p.get("copy"),
                project_id=p.get("project_id"), template_id=p.get("template_id"), progress=ctx.progress)
            if p.get("session_id"):
                s = db.get(CreativeSession, p["session_id"])
                if s:
                    s.params = {**(s.params or {}), "asset_ids": (s.params or {}).get("asset_ids", []) + out["asset_ids"]}
            return out
    except NoProviderAvailable as e:
        raise PermanentJobError(f"{e}. Enable a free image provider or install the local model in Settings.") from e
    except ValueError as e:
        raise PermanentJobError(str(e)) from e


@job_handler("brand_rules_draft")
def h_brand_rules_draft(ctx: JobContext) -> dict[str, Any]:
    """AI draft of a brand's claim & visual rules. Returned, not saved: the user reviews and saves it."""
    from app.services.brand_rules import draft_rules

    p = ctx.payload
    ctx.progress(0.1, "Drafting brand rules")
    try:
        with session_scope() as db:
            rules, provider, model = draft_rules(db, p["brand_id"], provider=p.get("provider"))
            return {"brand_id": p["brand_id"], "rules": rules, "provider": provider, "model": model}
    except (NoProviderAvailable, ValueError) as e:
        raise PermanentJobError(str(e)) from e


@job_handler("listing_image_plan")
def h_listing_image_plan(ctx: JobContext) -> dict[str, Any]:
    """Build (or rebuild) the creative brief and the per-slot image plan, without rendering."""
    from app.services.image_plan import build_plan

    p = ctx.payload
    try:
        with session_scope() as db:
            plan = build_plan(db, p["project_id"], provider=p.get("provider"), rebuild_brief=bool(p.get("rebuild_brief")),
                              slots=p.get("slots"), progress=ctx.progress)
            return {"project_id": p["project_id"], "slots": len(plan["slots"]), "brief_id": plan["brief_id"]}
    except (NoProviderAvailable, ValueError) as e:
        raise PermanentJobError(str(e)) from e


# Slot jobs of one listing can finish close together; serialise their read-modify-write of project.data.
_PROJECT_DATA_LOCK = threading.Lock()


def _slot_order(data: dict[str, Any]) -> list[str]:
    return [s["slot"] for s in (data.get("image_plan") or {}).get("slots") or []]


def _set_slot_state(project_id: str, slot: str, state: dict[str, Any], result: dict[str, Any] | None = None) -> bool:
    """Record a slot's status (and its new images). Returns True when no slot of the set is still pending."""
    with _PROJECT_DATA_LOCK, session_scope() as db:
        proj = db.get(Project, project_id)
        if proj is None:
            return False
        data = dict(proj.data or {})
        status = {**(data.get("image_status") or {}), slot: state}
        data["image_status"] = status
        if result is not None:
            order = _slot_order(data)
            images = [i for i in (data.get("images") or []) if i.get("slot") != slot] + [{"slot": slot, **result}]
            rank = {s: n for n, s in enumerate(order)}
            images.sort(key=lambda i: rank.get(i.get("slot"), len(rank)))  # plan order; "extra" visuals stay last
            data["images"] = images
            first = images[0].get("asset_ids") if images else None
            if first:
                proj.thumbnail_asset_id = first[0]
        data["image_errors"] = [f"{s}: {st.get('error')}" for s, st in status.items() if st.get("status") == "failed"]
        proj.data = data
        pending = [s for s, st in status.items() if st.get("status") in ("queued", "running")]
        if not pending and state.get("status") in ("done", "failed"):
            done = sum(1 for st in status.values() if st.get("status") == "done")
            failed = len(data["image_errors"])
            _notify(db, f"Listing images ready — {proj.name}", f"{done} created, {failed} failed",
                    link=f"/listings/{proj.id}?tab=images", level="success" if not failed else "warning")
        return not pending


@job_handler("listing_images")
def h_listing_images(ctx: JobContext) -> dict[str, Any]:
    """Image set: make sure a brief + plan exist, then queue one render job per slot (each retryable on its own)."""
    from app.jobs.queue import enqueue
    from app.services.image_plan import build_plan
    from app.services.marketplaces import MARKETPLACES

    p = ctx.payload
    with session_scope() as db:
        proj = db.get(Project, p["project_id"])
        if proj is None:
            raise PermanentJobError("listing project was deleted")
        planned = set(_slot_order(proj.data or {}))
        want = p.get("slots") or []
        default_order = MARKETPLACES.get((proj.data or {}).get("marketplace", "amazon"), MARKETPLACES["amazon"])["image_slots"]
    if p.get("replan") or not planned or not set(want) <= planned:
        # Always plan the whole set (so images don't repeat each other's angle), plus any extra slot asked for.
        order = list(default_order) + [s for s in want if s not in default_order]
        try:
            with session_scope() as db:
                build_plan(db, p["project_id"], provider=p.get("provider"), slots=order,
                           progress=lambda f, m: ctx.progress(f * 0.9, m))
        except (NoProviderAvailable, ValueError) as e:
            raise PermanentJobError(str(e)) from e
    ctx.progress(0.95, "Queueing one job per image")
    jobs: dict[str, str] = {}
    with _PROJECT_DATA_LOCK, session_scope() as db:
        proj = db.get(Project, p["project_id"])
        if proj is None:
            raise PermanentJobError("listing project was deleted")
        data = dict(proj.data or {})
        slots = [s for s in _slot_order(data) if not want or s in want]
        status = dict(data.get("image_status") or {})
        for slot in slots:
            j = enqueue(db, "listing_image_slot", {"project_id": proj.id, "slot": slot, "style": p.get("style", "minimal"),
                                                   "provider": p.get("provider")}, project_id=proj.id)
            jobs[slot] = j.id
            status[slot] = {"status": "queued", "job_id": j.id}
        data["image_status"] = status
        data["image_errors"] = [f"{s}: {st.get('error')}" for s, st in status.items() if st.get("status") == "failed"]
        proj.data = data
    return {"slot_jobs": jobs, "slots": list(jobs)}


@job_handler("listing_image_slot", heavy=True)
def h_listing_image_slot(ctx: JobContext) -> dict[str, Any]:
    """Render one planned image of a listing's set."""
    from app.services.creative import SLOT_TO_TYPE, generate_creative
    from app.services.image_plan import fallback_slot
    from app.services.marketplaces import MARKETPLACES

    p = ctx.payload
    slot = p["slot"]
    with session_scope() as db:
        proj = db.get(Project, p["project_id"])
        if proj is None:
            raise PermanentJobError("listing project was deleted")
        data = proj.data or {}
        mk = MARKETPLACES.get(data.get("marketplace", "amazon"), MARKETPLACES["amazon"])
        copy_ = data.get("copy") or {}
        plan = next((s for s in (data.get("image_plan") or {}).get("slots") or [] if s.get("slot") == slot), None)
        product_id, brand_id = proj.product_id, proj.brand_id
    s = plan or fallback_slot(slot, {}, copy_)
    _set_slot_state(p["project_id"], slot, {"status": "running", "job_id": ctx.job_id})
    copy_slot = {**copy_, "headline": s.get("headline") or copy_.get("headline"), "subheadline": copy_.get("subheadline")}
    if s.get("callouts"):
        copy_slot["benefits"] = s["callouts"]
    try:
        with session_scope() as db:
            out = generate_creative(db, product_id=product_id, brand_id=brand_id, creative_type=SLOT_TO_TYPE.get(slot, "lifestyle"),
                                    width=mk["image_size"][0], height=mk["image_size"][1], style=p.get("style", "minimal"),
                                    extra_prompt=s.get("concept") or "", provider=p.get("provider"), copy=copy_slot,
                                    project_id=p["project_id"], progress=ctx.progress, people=bool(s.get("people")))
    except (ValueError, NoProviderAvailable) as e:
        msg = f"{e}. Enable a free image provider or install the local model in Settings." if isinstance(e, NoProviderAvailable) else str(e)
        _set_slot_state(p["project_id"], slot, {"status": "failed", "job_id": ctx.job_id, "error": msg[:300]})
        raise PermanentJobError(msg) from e
    except Exception as e:  # cancelled or crashed: don't leave the slot "running" forever
        _set_slot_state(p["project_id"], slot, {"status": "failed", "job_id": ctx.job_id, "error": str(e)[:300] or type(e).__name__})
        raise
    _set_slot_state(p["project_id"], slot, {"status": "done", "job_id": ctx.job_id},
                    result={**out, "plan": {k: s.get(k) for k in ("headline", "strategy_source", "strategy_note")}})
    return {"slot": slot, **out}


@job_handler("image_edit", heavy=True)
def h_image_edit(ctx: JobContext) -> dict[str, Any]:
    from app.services.editing import run_edit

    p = ctx.payload
    try:
        with session_scope() as db:
            return run_edit(db, p, progress=ctx.progress)
    except NoProviderAvailable as e:
        raise PermanentJobError(str(e)) from e
    except ValueError as e:
        raise PermanentJobError(str(e)) from e


@job_handler("factory_item", heavy=True)
def h_factory_item(ctx: JobContext) -> dict[str, Any]:
    from app.services.creative import generate_creative

    p = ctx.payload
    if p["creative_type"] == "listing_copy":
        from app.jobs.handlers_extra import make_listing

        try:
            with session_scope() as db:
                batch = db.get(FactoryBatch, p["batch_id"])
                cfg = (batch.config if batch else {}) or {}
                proj = make_listing(db, p["product_id"], cfg.get("brand_id"), cfg.get("marketplace", "amazon"),
                                    {"language": cfg.get("language", "en"), "country": cfg.get("country", "US")}, provider=cfg.get("provider"))
                return {"project_id": proj.id, "asset_ids": []}
        except (NoProviderAvailable, ValueError) as e:
            raise PermanentJobError(str(e)) from e
    try:
        with session_scope() as db:
            batch = db.get(FactoryBatch, p["batch_id"])
            cfg = (batch.config if batch else {}) or {}
            variant_note = ""
            if p.get("variant_name"):
                variant_note = f"variant: {p['variant_name']} {p.get('variant_attributes') or ''}"
            out = generate_creative(
                db, product_id=p["product_id"], brand_id=cfg.get("brand_id"), creative_type=p["creative_type"],
                width=int(cfg.get("width", 2000)), height=int(cfg.get("height", 2000)), style=cfg.get("style", "minimal"),
                extra_prompt=" ".join(x for x in (cfg.get("prompt", ""), variant_note) if x),
                provider=cfg.get("provider"), template_id=p.get("template_id"), progress=ctx.progress)
            # Variant recolor (non-AI) if requested and the variant has a color hex.
            hexcolor = (p.get("variant_attributes") or {}).get("hex")
            if hexcolor and out["asset_ids"]:
                a = db.get(Asset, out["asset_ids"][0])
                if a:
                    rec = ops.recolor(load_image(a), hexcolor, strength=0.5)
                    na = create_asset_from_bytes(db, ops.to_png(rec), ext="png", source="edited",
                                                 filename=f"{a.title}-{p['variant_name']}.png",
                                                 title=f"{a.title} ({p['variant_name']})", product_id=a.product_id,
                                                 provider="shelfcraft", model="hue recolor (non-AI)",
                                                 meta={"operation": "recolor", "parent_asset_id": a.id})
                    out["asset_ids"].append(na.id)
            for aid in out["asset_ids"]:
                a = db.get(Asset, aid)
                if a:
                    a.tags = list({*(a.tags or []), "factory", f"batch:{p['batch_id'][:8]}"})
            return out
    except NoProviderAvailable as e:
        raise PermanentJobError(str(e)) from e
    except ValueError as e:
        raise PermanentJobError(str(e)) from e


@job_handler("video_render", heavy=True)
def h_video(ctx: JobContext) -> dict[str, Any]:
    from app.services.video import VideoError, render_video

    p = ctx.payload
    with session_scope() as db:
        proj = db.get(Project, p["project_id"])
        if proj is None:
            raise PermanentJobError("video project was deleted")
        data = proj.data or {}
        scenes = data.get("scenes") or []
        ids = {s.get("asset_id") for s in scenes} | ({data["music_asset_id"]} if data.get("music_asset_id") else set())
        assets = {a.id: a for a in db.scalars(select(Asset).where(Asset.id.in_([i for i in ids if i])))}
        for a in assets.values():
            db.expunge(a)
        music = assets.get(data.get("music_asset_id") or "")
        settings = {"aspect": data.get("aspect", "16:9"), "transition": data.get("transition", "fade"),
                    "transition_s": data.get("transition_s", 0.6), "text_style": data.get("text_style") or {}}
        name, product_id = proj.name, proj.product_id
    try:
        key, duration = render_video(scenes, aspect=settings["aspect"], transition=settings["transition"],
                                     transition_s=settings["transition_s"], music=music, assets=assets,
                                     text_style=settings["text_style"], progress=ctx.progress)
    except VideoError as e:
        raise PermanentJobError(str(e)) from e
    with session_scope() as db:
        a = register_file_asset(db, key, kind="video", mime="video/mp4", filename=f"{name}.mp4", source="export",
                                title=name, product_id=product_id, project_id=p["project_id"], provider="ffmpeg",
                                model="slideshow composer (non-generative)",
                                meta={"operation": "video_compose", "aspect": settings["aspect"]})
        a.duration_s = duration
        proj = db.get(Project, p["project_id"])
        if proj:
            proj.data = {**(proj.data or {}), "last_render_asset_id": a.id}
        _notify(db, f"Video ready — {name}", f"{duration:.1f}s MP4", link=f"/videos/{p['project_id']}")
        return {"asset_id": a.id, "duration_s": duration}


@job_handler("inspire_generate", heavy=True)
def h_inspire(ctx: JobContext) -> dict[str, Any]:
    from app.services.inspire import generate_from_reference

    try:
        with session_scope() as db:
            return generate_from_reference(db, ctx.payload, progress=ctx.progress)
    except NoProviderAvailable as e:
        raise PermanentJobError(str(e)) from e
    except ValueError as e:
        raise PermanentJobError(str(e)) from e


@job_handler("document_render")
def h_document_render(ctx: JobContext) -> dict[str, Any]:
    """Render an editor document to PNG (used by A+ export and bulk export)."""
    from app.services.documents import document_json

    with session_scope() as db:
        d = db.get(EditorDocument, ctx.payload["document_id"])
        if d is None:
            raise PermanentJobError("document not found")
        doc = document_json(d)
        png = render_png(doc)
        a = create_asset_from_bytes(db, png, ext="png", source="export", filename=f"{d.name}.png", title=d.name,
                                    project_id=d.project_id, meta={"document_id": d.id, "operation": "render"})
        return {"asset_id": a.id}


@job_handler("listing_more_images", heavy=True)
def h_listing_more_images(ctx: JobContext) -> dict[str, Any]:
    """"Add more visuals" to an existing listing session, steered by a prompt; appended to the image set."""
    from app.services.creative import generate_creative
    from app.services.marketplaces import MARKETPLACES

    p = ctx.payload
    with session_scope() as db:
        proj = db.get(Project, p["project_id"])
        if proj is None:
            raise PermanentJobError("listing project was deleted")
        mk = MARKETPLACES.get((proj.data or {}).get("marketplace", "amazon"), MARKETPLACES["amazon"])
        copy_ = (proj.data or {}).get("copy") or {}
        product_id, brand_id = proj.product_id, proj.brand_id
    try:
        with session_scope() as db:
            out = generate_creative(db, product_id=product_id, brand_id=brand_id, creative_type=p.get("creative_type", "lifestyle"),
                                    width=mk["image_size"][0], height=mk["image_size"][1], style=p.get("style", "minimal"),
                                    extra_prompt=p.get("prompt", ""), provider=p.get("provider"), copy=copy_,
                                    project_id=p["project_id"], progress=ctx.progress)
    except NoProviderAvailable as e:
        raise PermanentJobError(f"{e}. Enable a free image provider or install the local model in Settings.") from e
    except ValueError as e:
        raise PermanentJobError(str(e)) from e
    with session_scope() as db:
        proj = db.get(Project, p["project_id"])
        if proj:
            data = dict(proj.data or {})
            data["images"] = list(data.get("images") or []) + [{"slot": "extra", "prompt": p.get("prompt", ""), **out}]
            proj.data = data
    return out
