export type Step = {
  kind: string; creative_type?: string; style?: string; extra_prompt?: string; width?: number; height?: number;
  marketplace?: string; language?: string; country?: string; aspect?: string; duration?: number; voiceover?: boolean;
  tier?: string; modules?: string[]; count?: number;
};
export type PlaybookSettings = { style?: string; marketplace?: string; width?: number; height?: number };
export interface PlaybookT {
  id: string; name: string; description?: string | null; category: string; steps: Step[]; settings: PlaybookSettings;
  is_template: boolean; updated_at: string; estimate_minutes?: number;
}
export interface PlaybookOptions {
  creative_types: Record<string, string>; styles: string[]; marketplaces: Record<string, string>; languages: Record<string, string>;
  aspects: string[]; aplus_modules: Record<string, string>; default_aplus_modules: string[]; step_minutes: Record<string, number>;
}
export interface PlaybookRun { id: string; total: number; counts: Record<string, number>; created_at: string }

export const STEP_KINDS: [string, string][] = [
  ["creative", "Image / creative"], ["listing_copy", "Listing copy"], ["research", "Product research"],
  ["aplus", "A+ content"], ["video", "Video"], ["packaging", "Packaging ideas"],
];
export const CATEGORIES = ["custom", "listing", "lifestyle", "social", "launch"];

/** A fresh step of the given kind — switching kinds never keeps fields that belong to another kind. */
export function defaultStep(kind: string): Step {
  switch (kind) {
    case "creative": return { kind, creative_type: "lifestyle" };
    case "listing_copy": return { kind, language: "en" };
    case "video": return { kind, aspect: "16:9", duration: 15, voiceover: false };
    case "aplus": return { kind, tier: "premium" };
    case "packaging": return { kind, count: 8 };
    default: return { kind };
  }
}

const KIND_LABEL = Object.fromEntries(STEP_KINDS);
const humanize = (s: string) => s.replaceAll("_", " ");

/** Short chip label, e.g. "White-background main image", "Listing copy · walmart · DE", "Video 9:16 + voiceover". */
export function stepLabel(s: Step, opts?: Partial<Pick<PlaybookOptions, "creative_types" | "marketplaces">> | null): string {
  if (s.kind === "creative") return (s.creative_type && opts?.creative_types?.[s.creative_type]) || humanize(s.creative_type ?? "image");
  if (s.kind === "listing_copy") {
    const bits = [s.marketplace && (opts?.marketplaces?.[s.marketplace] ?? s.marketplace), s.language && s.language !== "en" ? s.language.toUpperCase() : null].filter(Boolean);
    return ["Listing copy", ...bits].join(" · ");
  }
  if (s.kind === "video") return `Video ${s.aspect ?? "16:9"}${s.voiceover ? " + voiceover" : ""}`;
  if (s.kind === "aplus") return `A+ ${s.tier ?? "premium"}`;
  return KIND_LABEL[s.kind] ?? humanize(s.kind);
}

/** Rough minutes on CPU; mirrors backend STEP_MINUTES when options aren't loaded yet. */
const FALLBACK_MIN: Record<string, number> = { creative: 1, listing_copy: 2.5, research: 3, video: 1.5, aplus: 0.5, packaging: 2.5 };
export function estimateMinutes(steps: Step[], products = 1, perStep?: Record<string, number>): number {
  const per = steps.reduce((t, s) => t + (perStep?.[s.kind] ?? FALLBACK_MIN[s.kind] ?? 1) + (s.voiceover ? 1 : 0), 0);
  return Math.round(per * Math.max(products, 1) * 10) / 10;
}

export function formatMinutes(m: number): string {
  if (m < 1) return "under a minute";
  if (m < 60) return `~${Math.round(m)} min`;
  const h = Math.floor(m / 60), r = Math.round(m % 60);
  return `~${h} h${r ? ` ${r} min` : ""}`;
}

export function runSummary(r: PlaybookRun): { done: number; failed: number; active: number; state: "running" | "done" | "failed" | "cancelled" } {
  const c = r.counts;
  const done = c.succeeded ?? 0, failed = c.failed ?? 0, active = (c.queued ?? 0) + (c.running ?? 0);
  const state = active ? "running" : failed ? "failed" : (c.cancelled ?? 0) && !done ? "cancelled" : "done";
  return { done, failed, active, state };
}
