export type ID = string;

export interface Brand {
  id: ID; name: string; website?: string | null; colors: string[]; primary_font?: string | null;
  secondary_font?: string | null; language: string; tagline?: string | null; tone_of_voice?: string | null;
  target_audience?: string | null; positioning?: string | null; values: string[]; aesthetic: string[];
  visual_identity?: string | null; marketing_guidelines?: string | null; extra_details?: string | null;
  logo_asset_id?: ID | null; logo_url?: string | null;
  guidelines: { id: ID; title: string; asset_id?: ID; chars: number; created_at: string }[];
  product_count: number; created_at: string; updated_at: string;
}

export interface ProductImage { id: ID; asset_id: ID; role: string; position: number; url: string; thumb_url: string; width?: number; height?: number }
export interface Variant { id?: ID; name: string; sku?: string | null; attributes: Record<string, string>; price?: number | null }

export interface Product {
  id: ID; name: string; brand_id?: ID | null; brand_name?: string | null; sku?: string | null; asin?: string | null;
  category?: string | null; price?: number | null; currency: string; tags: string[]; images: ProductImage[];
  image_count: number; cover_url?: string | null; variant_count: number; created_at: string; updated_at: string;
  source_url?: string | null; description?: string | null; features?: string[]; benefits?: string[];
  specifications?: Record<string, string>; variants?: Variant[];
}

export interface Asset {
  id: ID; kind: "image" | "video" | "audio" | "document" | "archive" | string; source: string; filename: string; title: string;
  mime_type: string; size_bytes: number; width?: number | null; height?: number | null; duration_s?: number | null;
  tags: string[]; favorite: boolean; folder_id?: ID | null; brand_id?: ID | null; product_id?: ID | null; project_id?: ID | null;
  provider?: string | null; model?: string | null; is_ai_generated: boolean; meta: Record<string, unknown>;
  url: string; thumb_url: string; created_at: string;
}

export interface Job {
  id: ID; type: string; label: string; status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number; message?: string | null; error?: string | null; result?: Record<string, unknown> | null;
  attempts: number; max_attempts: number; batch_id?: ID | null; project_id?: ID | null;
  created_at: string; started_at?: string | null; finished_at?: string | null; payload_summary: Record<string, unknown>;
}

export interface ProviderStatus {
  name: string; label: string; kinds: string[]; local: boolean; free_tier_verified: boolean; verified_on: string;
  source_url: string; limits_note: string; privacy_note: string; license_note: string; requires_key: boolean; vision: boolean;
  enabled: boolean; has_key: boolean; key_source?: string | null; extra: Record<string, string>; configured: boolean;
  state: "available" | "disabled" | "not_configured" | "rate_limited" | "unavailable" | "ineligible";
  text_model?: string | null; image_model?: string | null; default_text_model?: string | null; default_image_model?: string | null;
  last_success_at?: string | null; last_failure_at?: string | null; last_error?: string | null;
  rate_limited_until?: string | null; circuit_open_until?: string | null;
}

export interface Settings {
  theme: "light" | "dark" | "system"; active_brand_id?: ID | null; default_text_provider: string; default_image_provider: string;
  fallback_order: string[]; generation_defaults: Record<string, unknown>; privacy_ack_hosted: boolean;
  onboarding: Record<string, boolean>; display_name: string;
}

export interface DocLayer {
  id: string; type: "text" | "rect" | "ellipse" | "image" | "line" | "group"; name: string;
  x: number; y: number; width: number; height: number; rotation: number; opacity: number; locked: boolean; visible: boolean;
  parentId?: string;
  // text
  text?: string; fontFamily?: string; fontSize?: number; fontStyle?: string; fill?: string; align?: string;
  lineHeight?: number; letterSpacing?: number; verticalAlign?: string;
  // shapes
  stroke?: string; strokeWidth?: number; cornerRadius?: number;
  // image
  assetId?: string | null; placeholder?: string; fit?: "contain" | "cover" | "fill"; crop?: { x: number; y: number; width: number; height: number } | null;
  // line
  points?: number[]; dash?: number[];
  [key: string]: unknown;
}

export interface EditorDoc { width: number; height: number; background: string; layers: DocLayer[] }
export interface DocSummary { id: ID; name: string; width: number; height: number; version: number; project_id?: ID | null; thumb_url?: string | null; updated_at: string }

export interface ListingCopy {
  title?: string; bullets?: string[]; description?: string; keywords?: string[]; search_terms?: string;
  benefits?: string[]; feature_explanations?: { feature: string; explanation: string }[];
  image_strategy?: { slot: string; concept: string; headline?: string; callouts?: string[] }[];
  listing_structure?: string[]; creative_recommendations?: string[]; headline?: string; subheadline?: string; assumptions?: string[];
}
