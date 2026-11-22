"""SQLAlchemy ORM models.

Conventions
- String UUID primary keys (portable to Postgres, safe to expose in URLs).
- `created_at` / `updated_at` on everything; `deleted_at` soft-delete on user content.
- Flexible list-like attributes (colors, bullets, tags...) are JSON columns; anything that
  needs querying or referential integrity is its own table.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


# ---------------------------------------------------------------- users & settings
class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    display_name: Mapped[str] = mapped_column(String(120), default="You")
    email: Mapped[str | None] = mapped_column(String(255))
    settings: Mapped[UserSettings | None] = relationship(back_populates="user", uselist=False)


class UserSettings(Base, TimestampMixin):
    __tablename__ = "user_settings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    theme: Mapped[str] = mapped_column(String(16), default="system")
    active_brand_id: Mapped[str | None] = mapped_column(ForeignKey("brands.id", ondelete="SET NULL"))
    default_text_provider: Mapped[str] = mapped_column(String(40), default="ollama")
    default_image_provider: Mapped[str] = mapped_column(String(40), default="local_composite")
    fallback_order: Mapped[list[Any]] = mapped_column(default=list)  # provider names
    generation_defaults: Mapped[dict[str, Any]] = mapped_column(default=dict)
    privacy_ack_hosted: Mapped[bool] = mapped_column(Boolean, default=False)
    onboarding: Mapped[dict[str, Any]] = mapped_column(default=dict)
    user: Mapped[User] = relationship(back_populates="settings")


# ---------------------------------------------------------------- brands
class Brand(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "brands"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    website: Mapped[str | None] = mapped_column(String(500))
    # Plain column (no DB FK) to avoid a brands↔assets FK cycle; assets are soft-deleted so it can't dangle.
    logo_asset_id: Mapped[str | None] = mapped_column(String(32))
    colors: Mapped[list[Any]] = mapped_column(default=list)  # ["#0f766e", ...] max 6
    primary_font: Mapped[str | None] = mapped_column(String(80))
    secondary_font: Mapped[str | None] = mapped_column(String(80))
    language: Mapped[str] = mapped_column(String(16), default="en")
    tagline: Mapped[str | None] = mapped_column(String(200))
    tone_of_voice: Mapped[str | None] = mapped_column(String(300))
    target_audience: Mapped[str | None] = mapped_column(Text)
    positioning: Mapped[str | None] = mapped_column(Text)
    values: Mapped[list[Any]] = mapped_column(default=list)
    aesthetic: Mapped[list[Any]] = mapped_column(default=list)
    visual_identity: Mapped[str | None] = mapped_column(Text)
    marketing_guidelines: Mapped[str | None] = mapped_column(Text)
    extra_details: Mapped[str | None] = mapped_column(Text)
    # Structured rules for claims and visuals (see app/services/brand_rules.py); AI-drafted, user-edited.
    rules: Mapped[dict[str, Any]] = mapped_column(default=dict)

    guidelines: Mapped[list[BrandGuideline]] = relationship(back_populates="brand", cascade="all, delete-orphan")
    products: Mapped[list[Product]] = relationship(back_populates="brand")


class BrandGuideline(Base, TimestampMixin):
    """Uploaded guideline document with extracted text (used as LLM context)."""

    __tablename__ = "brand_guidelines"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    extracted_text: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[Brand] = relationship(back_populates="guidelines")


# ---------------------------------------------------------------- products
class Product(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    brand_id: Mapped[str | None] = mapped_column(ForeignKey("brands.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(80), index=True)
    asin: Mapped[str | None] = mapped_column(String(20))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    category: Mapped[str | None] = mapped_column(String(120), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    features: Mapped[list[Any]] = mapped_column(default=list)
    benefits: Mapped[list[Any]] = mapped_column(default=list)
    specifications: Mapped[dict[str, Any]] = mapped_column(default=dict)
    price: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    tags: Mapped[list[Any]] = mapped_column(default=list)

    brand: Mapped[Brand | None] = relationship(back_populates="products")
    variants: Mapped[list[ProductVariant]] = relationship(back_populates="product", cascade="all, delete-orphan")
    images: Mapped[list[ProductImage]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="ProductImage.position"
    )


class ProductVariant(Base, TimestampMixin):
    __tablename__ = "product_variants"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    sku: Mapped[str | None] = mapped_column(String(80))
    attributes: Mapped[dict[str, Any]] = mapped_column(default=dict)  # {"color": "Red", "size": "L"}
    price: Mapped[float | None] = mapped_column(Float)
    product: Mapped[Product] = relationship(back_populates="variants")


class ProductImage(Base, TimestampMixin):
    __tablename__ = "product_images"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(30), default="reference")  # main | reference | cutout
    position: Mapped[int] = mapped_column(Integer, default=0)
    product: Mapped[Product] = relationship(back_populates="images")
    asset: Mapped[Asset] = relationship()


class ProductReview(Base, TimestampMixin):
    """A customer review collected for a product (from pages the user saved, CSV exports or pasted text).

    `content_hash` de-duplicates the same review arriving from several sources/pages."""

    __tablename__ = "product_reviews"
    __table_args__ = (Index("ux_product_reviews_hash", "product_id", "content_hash", unique=True),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(20), default="paste")  # amazon | walmart | page | csv | paste
    external_id: Mapped[str | None] = mapped_column(String(80))
    rating: Mapped[float | None] = mapped_column(Float)
    title: Mapped[str | None] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(120))
    review_date: Mapped[str | None] = mapped_column(String(10))  # ISO YYYY-MM-DD when it could be parsed
    verified: Mapped[bool | None] = mapped_column(Boolean)
    variant: Mapped[str | None] = mapped_column(String(200))
    helpful_votes: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))


class CompetitorListing(Base, TimestampMixin):
    """A top-performing / competing listing in the product's category, read from pages the user saved in their own
    browser (Best Sellers lists, search results, competitor product pages). One row per marketplace item; later pages
    about the same item enrich it."""

    __tablename__ = "competitor_listings"
    __table_args__ = (Index("ux_competitor_item", "product_id", "market", "market_id", unique=True),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    market: Mapped[str] = mapped_column(String(20))  # amazon | walmart | other
    market_id: Mapped[str] = mapped_column(String(64))  # ASIN / Walmart item id / URL hash
    url: Mapped[str | None] = mapped_column(String(1000))
    title: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(200))
    price: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(8))
    rating: Mapped[float | None] = mapped_column(Float)
    review_count: Mapped[int | None] = mapped_column(Integer)
    rank: Mapped[int | None] = mapped_column(Integer)  # position on a Best Sellers list
    position: Mapped[int | None] = mapped_column(Integer)  # position in search results
    bsr_rank: Mapped[int | None] = mapped_column(Integer)
    bsr: Mapped[str | None] = mapped_column(String(300))
    category: Mapped[str | None] = mapped_column(String(200))
    monthly_bought: Mapped[int | None] = mapped_column(Integer)  # "1K+ bought in past month" → 1000
    sponsored: Mapped[bool | None] = mapped_column(Boolean)
    badges: Mapped[list[Any]] = mapped_column(default=list)
    bullets: Mapped[list[Any]] = mapped_column(default=list)
    description: Mapped[str | None] = mapped_column(Text)
    specifications: Mapped[dict[str, Any]] = mapped_column(default=dict)
    image_count: Mapped[int | None] = mapped_column(Integer)
    has_video: Mapped[bool | None] = mapped_column(Boolean)
    has_aplus: Mapped[bool | None] = mapped_column(Boolean)
    image_url: Mapped[str | None] = mapped_column(String(1000))
    reviews: Mapped[list[Any]] = mapped_column(default=list)
    sources: Mapped[list[Any]] = mapped_column(default=list)  # bestsellers | search | product_page
    included: Mapped[bool] = mapped_column(Boolean, default=True)


class ProductResearch(Base, TimestampMixin):
    """AI product-intelligence result. `inputs` records exactly what the model was given."""

    __tablename__ = "product_research"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), default="full")
    inputs: Mapped[dict[str, Any]] = mapped_column(default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(default=dict)
    provider: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(120))


# ---------------------------------------------------------------- projects & sessions
class Project(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(30), default="design")  # design|listing|aplus|video|inspire
    brand_id: Mapped[str | None] = mapped_column(ForeignKey("brands.id", ondelete="SET NULL"), index=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)  # kind-specific state (e.g. listing copy, A+ modules)
    thumbnail_asset_id: Mapped[str | None] = mapped_column(String(32))  # no DB FK: avoids projects↔assets cycle


class CreativeSession(Base, TimestampMixin):
    """One user-initiated generation workflow (shown in Recent Work)."""

    __tablename__ = "creative_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)


# ---------------------------------------------------------------- assets
class Folder(Base, TimestampMixin):
    __tablename__ = "folders"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("folders.id", ondelete="CASCADE"))


class Asset(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(20), index=True)  # image | video | audio | document | export
    source: Mapped[str] = mapped_column(String(20), index=True)  # upload | generated | edited | export | system
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    thumb_key: Mapped[str | None] = mapped_column(String(500))
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_s: Mapped[float | None] = mapped_column(Float)
    title: Mapped[str | None] = mapped_column(String(255))
    tags: Mapped[list[Any]] = mapped_column(default=list)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    folder_id: Mapped[str | None] = mapped_column(ForeignKey("folders.id", ondelete="SET NULL"), index=True)
    brand_id: Mapped[str | None] = mapped_column(ForeignKey("brands.id", ondelete="SET NULL"), index=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    # Provenance: who/what produced it. Always set for generated content.
    provider: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(160))
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict)  # prompt, params, parent asset, op...


# ---------------------------------------------------------------- templates & editor
class Template(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "templates"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(40), index=True)  # main|lifestyle|infographic|aplus|social|ad
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    document: Mapped[dict[str, Any]] = mapped_column(default=dict)  # editor JSON with {{placeholders}}
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    thumbnail_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))


class EditorDocument(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "editor_documents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    background: Mapped[str] = mapped_column(String(40), default="#ffffff")
    version: Mapped[int] = mapped_column(Integer, default=1)  # optimistic concurrency
    thumbnail_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
    layers: Mapped[list[EditorLayer]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="EditorLayer.z_index"
    )


class EditorLayer(Base, TimestampMixin):
    __tablename__ = "editor_layers"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # client-generated id
    document_id: Mapped[str] = mapped_column(
        ForeignKey("editor_documents.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    type: Mapped[str] = mapped_column(String(20))  # image | text | rect | ellipse | line | group
    name: Mapped[str] = mapped_column(String(120))
    z_index: Mapped[int] = mapped_column(Integer, default=0)
    parent_id: Mapped[str | None] = mapped_column(String(32))  # group membership
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    visible: Mapped[bool] = mapped_column(Boolean, default=True)
    props: Mapped[dict[str, Any]] = mapped_column(default=dict)  # x, y, width, rotation, fill, text, assetId...
    document: Mapped[EditorDocument] = relationship(back_populates="layers")


class EditorRevision(Base):
    """Snapshot history for document recovery (bounded per document)."""

    __tablename__ = "editor_revisions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("editor_documents.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- AI providers & usage
class ProviderConfig(Base, TimestampMixin):
    __tablename__ = "provider_configs"
    name: Mapped[str] = mapped_column(String(40), primary_key=True)  # gemini, groq, ollama...
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Optional key entered in the UI. Stored server-side only; env vars take precedence.
    api_key: Mapped[str | None] = mapped_column(String(500))
    extra: Mapped[dict[str, Any]] = mapped_column(default=dict)  # account_id, base_url...
    text_model: Mapped[str | None] = mapped_column(String(160))
    image_model: Mapped[str | None] = mapped_column(String(160))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    circuit_open_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rate_limited_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GenerationRequest(Base, TimestampMixin):
    __tablename__ = "generation_requests"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(30), index=True)  # text | image | edit | vision
    purpose: Mapped[str] = mapped_column(String(60))  # listing_copy, research, main_image...
    provider: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    prompt: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    providers_tried: Mapped[list[Any]] = mapped_column(default=list)
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)


class UsageRecord(Base):
    __tablename__ = "usage_records"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    model: Mapped[str | None] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(20))
    success: Mapped[bool] = mapped_column(Boolean)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# ---------------------------------------------------------------- jobs
class Job(Base, TimestampMixin):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    type: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    # queued | running | succeeded | failed | cancelled
    heavy: Mapped[bool] = mapped_column(Boolean, default=False)  # CPU-bound (image/video)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str | None] = mapped_column(String(300))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    batch_id: Mapped[str | None] = mapped_column(String(32), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), unique=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("creative_sessions.id", ondelete="SET NULL"))
    job_attempts: Mapped[list[JobAttempt]] = relationship(back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_jobs_claim", "status", "heavy", "priority", "created_at"),)


class JobAttempt(Base):
    __tablename__ = "job_attempts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running")
    error: Mapped[str | None] = mapped_column(Text)
    job: Mapped[Job] = relationship(back_populates="job_attempts")


class FactoryBatch(Base, TimestampMixin):
    __tablename__ = "factory_batches"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    total: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------------- exports & audit
class ExportRecord(Base):
    __tablename__ = "export_records"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(30))  # png|jpeg|webp|mp4|zip|json|csv
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
    source_type: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[str | None] = mapped_column(String(32))
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(32))
    detail: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Playbook(Base, TimestampMixin, SoftDeleteMixin):
    """A reusable recipe of generation steps (e.g. 'Amazon main images' = white main + hero + 3 infographics)."""

    __tablename__ = "playbooks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), default="custom")
    steps: Mapped[list[Any]] = mapped_column(default=list)  # [{"kind": "creative", "creative_type": "...", ...}]
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)  # style, prompt, size, marketplace...
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)  # built-in library entry


class ApiKey(Base, TimestampMixin):
    """Public API key. Only a SHA-256 hash is stored; the full key is shown once at creation."""

    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    prefix: Mapped[str] = mapped_column(String(20), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list[Any]] = mapped_column(default=list)  # ["read", "write"]
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Member(Base, TimestampMixin):
    """Workspace member for team mode. Passwords hashed with scrypt; invites use one-time tokens."""

    __tablename__ = "members"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    role: Mapped[str] = mapped_column(String(20), default="editor")  # owner | admin | editor | viewer
    password_hash: Mapped[str | None] = mapped_column(String(300))
    invite_token_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    invite_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="invited")  # invited | active | disabled
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoginSession(Base):
    __tablename__ = "login_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    level: Mapped[str] = mapped_column(String(16), default="info")
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(300))
    read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


