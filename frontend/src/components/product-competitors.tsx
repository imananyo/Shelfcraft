"use client";
import { useQueryClient } from "@tanstack/react-query";
import { BarChart3, Crown, ExternalLink, FileUp, Search, Sparkles, Trash2, Trophy } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { JobCard } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import { Badge, Card, EmptyState, Notice, ProviderBadge, Skeleton } from "@/components/ui/misc";
import { Confirm } from "@/components/ui/overlay";
import { del, patch, post } from "@/lib/api";
import { useApi, useCapabilities } from "@/lib/hooks";
import type { Job, Product } from "@/lib/types";
import { timeAgo } from "@/lib/utils";

type Comp = { id: string; market: string; market_id: string; included: boolean; badges: string[]; sources: string[]; url?: string | null;
  title?: string | null; brand?: string | null; price?: number | null; currency?: string | null; rating?: number | null; review_count?: number | null;
  rank?: number | null; position?: number | null; bsr?: string | null; monthly_bought?: number | null; sponsored?: boolean | null;
  image_count?: number | null; has_video?: boolean | null; has_aplus?: boolean | null; image_url?: string | null; bullets: string[];
  review_samples: number; has_details: boolean };
type Q = { min: number; p25: number; median: number; p75: number; max: number; n: number } | null;
type Bench = { listings: number; organic: number; with_details: number; categories: string[]; price: Q; your_price?: number | null;
  your_price_percentile?: number | null; rating: Q; review_count: Q; monthly_bought: Q; title_chars: Q; title_words: Q; your_title_chars?: number | null;
  keywords: { term: string; titles: number; share: number; in_your_listing: boolean }[]; missing_keywords: string[];
  bullets: { count: Q; avg_chars: Q }; images: Q; video_share: number | null; aplus_share: number | null; sponsored_share: number | null;
  badges: Record<string, number>; bsr: { title: string; bsr: string }[] };
type Theme = { theme: string; reviews: number; share: number; avg_rating: number | null; competitors?: number; quotes: { text: string; rating?: number | null; competitor?: string }[] };
type Analysis = { provider?: string; model?: string; created_at: string; result: {
  benchmark: Bench; competitor_review_themes: { complaints: Theme[]; praise: Theme[]; requests: Theme[] };
  summary?: string; what_top_listings_do?: string[]; title_formula?: string; bullet_patterns?: string[]; image_patterns?: string[];
  price_positioning?: string; competitor_weaknesses?: { weakness: string; evidence?: string; opportunity?: string }[];
  differentiation_angles?: { angle: string; why?: string }[]; keywords_to_add?: string[]; listing_recommendations?: string[]; assumptions?: string[];
  coverage: { listings: number; with_details: number; competitor_reviews: number; reviews_analysed: number; ai_error?: string | null } } };
type ImportResult = { added: number; updated: number; total: number;
  sources: { name: string; page_type?: string; category?: string | null; found?: number; added?: number; updated?: number; skipped_own?: number; error?: string }[] };

const PAGE_LABEL: Record<string, string> = { amazon_bestsellers: "Best Sellers list", amazon_search: "Amazon search", amazon_product: "Amazon product page",
  walmart_search: "Walmart search", walmart_product: "Walmart product page" };

const money = (v?: number | null, cur?: string | null) => (v == null ? "–" : `${cur && cur !== "USD" ? `${cur} ` : "$"}${v.toFixed(2)}`);
const n0 = (v?: number | null) => (v == null ? "–" : v >= 1000 ? `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}K` : String(v));

export function ProductCompetitors({ product }: { product: Product }) {
  const qc = useQueryClient();
  const list = useApi<{ items: Comp[]; total: number }>(["competitors", product.id], `/products/${product.id}/competitors`);
  const bench = useApi<Bench>(["competitor-bench", product.id], `/products/${product.id}/competitors/benchmark`);
  const analysis = useApi<Analysis | null>(["competitor-analysis", product.id], `/products/${product.id}/competitors/analysis`);
  const refresh = () => ["competitors", "competitor-bench", "competitor-analysis"].forEach((k) => qc.invalidateQueries({ queryKey: [k, product.id] }));
  const total = list.data?.total ?? 0;
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
        <Collect product={product} onAdded={refresh} />
        <div className="flex flex-col gap-4">
          {list.isLoading ? <Skeleton className="h-40" /> : !total ? (
            <EmptyState icon={<Trophy />} title="No top listings collected yet"
              body="Save your category’s Best Sellers page or a search results page for your main keyword. Shelfcraft reads every listing on it and benchmarks yours against them." />
          ) : bench.data && <BenchCard b={bench.data} />}
          {!!total && <AnalysisPanel product={product} total={total}
            reviews={(list.data?.items ?? []).filter((c) => c.included).reduce((s, c) => s + c.review_samples, 0)} analysis={analysis.data ?? null} loading={analysis.isLoading} onDone={refresh} />}
        </div>
      </div>
      {!!total && <CompTable product={product} items={list.data?.items ?? []} onChange={refresh} />}
    </div>
  );
}

function Collect({ product, onAdded }: { product: Product; onAdded: () => void }) {
  const [busy, setBusy] = React.useState(false);
  const [kw, setKw] = React.useState(product.category || product.name);
  const [result, setResult] = React.useState<ImportResult | null>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const dom = /amazon\.[a-z.]+/i.exec(product.source_url ?? "")?.[0] ?? "amazon.com";
  const q = encodeURIComponent(kw.trim());

  const onFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    setBusy(true);
    const all = await Promise.all(Array.from(files).map(async (f) => ({ name: f.name, content: await f.text() })));
    const merged: ImportResult = { added: 0, updated: 0, total: 0, sources: [] };
    try {
      for (let i = 0; i < all.length; i += 5) {
        const chunk = all.slice(i, i + 5).filter((f) => f.content.trim() && f.content.length <= 8_000_000);
        if (!chunk.length) continue;
        try {
          const r = await post<ImportResult>(`/products/${product.id}/competitors/import`, { sources: chunk });
          merged.added += r.added; merged.updated += r.updated; merged.total = r.total; merged.sources.push(...r.sources);
        } catch (e) { merged.sources.push(...chunk.map((c) => ({ name: c.name, error: (e as Error).message }))); }
      }
      setResult(merged);
      if (merged.added || merged.updated) toast.success(`${merged.added} new listing${merged.added === 1 ? "" : "s"}, ${merged.updated} updated`);
      else toast.warning("No listings were found in those files");
      onAdded();
    } finally { setBusy(false); }
  };

  const link = (label: string, url: string) => (
    <a href={url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-[12px] hover:bg-sunken">
      {label}<ExternalLink className="size-3" /></a>
  );
  return (
    <Card className="flex flex-col gap-4 p-5 lg:sticky lg:top-0 lg:self-start">
      <div>
        <h3 className="text-[15px] font-semibold">Collect top listings</h3>
        <p className="text-[12.5px] text-muted">Open these pages in your own browser, save them (<kbd>Ctrl+S</kbd> / <kbd>⌘S</kbd>), then upload the files here. Shelfcraft never visits Amazon or Walmart itself.</p>
      </div>
      <div className="flex flex-col gap-2 text-[12.5px]">
        <div className="font-medium">1. Best sellers in your category</div>
        <div className="flex flex-wrap gap-1.5">{link("Amazon Best Sellers", `https://www.${dom}/gp/bestsellers`)}</div>
        <p className="text-muted">Click down to your exact category, <b>scroll to the bottom</b> so all 50 load, then save. Page 2 adds ranks 51–100.</p>
      </div>
      <div className="flex flex-col gap-2 text-[12.5px]">
        <div className="font-medium">2. Search results for your main keyword</div>
        <Input value={kw} onChange={(e) => setKw(e.target.value)} placeholder="e.g. insulated water bottle" />
        <div className="flex flex-wrap gap-1.5">
          {link("Amazon search", `https://www.${dom}/s?k=${q}`)}{link("Walmart search", `https://www.walmart.com/search?q=${q}`)}
        </div>
        <p className="text-muted">Search pages show “bought in past month”, sponsored placements and badges.</p>
      </div>
      <div className="flex flex-col gap-2 text-[12.5px]">
        <div className="font-medium">3. The top 5–10 competitors’ product pages (optional, recommended)</div>
        <p className="text-muted">Adds their bullets, image count, video, A+ content, Best Sellers Rank and the reviews shown, so Shelfcraft can count what customers complain about across the category. Use the “open” links in the table below.</p>
      </div>
      <Button variant="outline" onClick={() => fileRef.current?.click()} loading={busy}><FileUp />Upload saved pages</Button>
      <input ref={fileRef} type="file" multiple accept=".html,.htm,text/html" className="hidden"
        onChange={(e) => { onFiles(e.target.files).finally(() => { e.target.value = ""; }); }} />
      {result && (
        <Notice tone={result.added || result.updated ? "success" : "warning"}>
          <div className="font-medium">{result.added} new · {result.updated} updated · {result.total} listings in total</div>
          <ul className="mt-1 space-y-0.5 text-[12px]">
            {result.sources.map((s, i) => (
              <li key={i}><span className="font-medium">{s.name}</span>: {s.error ? <span className="text-danger">{s.error}</span> :
                `${PAGE_LABEL[s.page_type ?? ""] ?? s.page_type}${s.category ? ` (${s.category})` : ""}: ${s.found} found, ${s.added} new, ${s.updated} updated${s.skipped_own ? `, your own listing skipped` : ""}`}</li>
            ))}
          </ul>
        </Notice>
      )}
    </Card>
  );
}

function Stat({ label, q, fmt = (v: number) => String(v), extra }: { label: string; q: Q; fmt?: (v: number) => string; extra?: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-[10px] bg-sunken px-3 py-2.5">
      <span className="text-[11px] uppercase tracking-wide text-muted">{label}</span>
      <span className="text-[17px] font-semibold">{q ? fmt(q.median) : "–"}</span>
      {q && <span className="text-[11.5px] text-muted">{fmt(q.p25)} – {fmt(q.p75)} middle half · n={q.n}</span>}
      {extra}
    </div>
  );
}

function BenchCard({ b }: { b: Bench }) {
  const pct = (v: number | null) => (v == null ? "–" : `${Math.round(v * 100)}%`);
  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <BarChart3 className="size-4 text-primary" /><h3 className="text-[15px] font-semibold">Category benchmark</h3>
        <span className="text-[12px] text-muted">{b.listings} listings{b.categories.length ? ` · ${b.categories.join(" · ")}` : ""} · exact numbers, no AI</span>
      </div>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Stat label="Price (median)" q={b.price} fmt={(v) => `$${v.toFixed(2)}`}
          extra={b.your_price != null && <span className="text-[11.5px] font-medium">You: ${b.your_price.toFixed(2)}{b.your_price_percentile != null ? ` · cheaper than ${pct(1 - b.your_price_percentile)}` : ""}</span>} />
        <Stat label="Rating" q={b.rating} fmt={(v) => `${v}★`} />
        <Stat label="Reviews" q={b.review_count} fmt={(v) => n0(v)} />
        <Stat label="Title length" q={b.title_chars} fmt={(v) => `${Math.round(v)} ch`}
          extra={b.your_title_chars != null && <span className="text-[11.5px] font-medium">Your product name: {b.your_title_chars} ch</span>} />
        {b.monthly_bought && <Stat label="Bought / month" q={b.monthly_bought} fmt={(v) => `${n0(v)}+`} />}
        {b.images && <Stat label="Images" q={b.images} />}
        {b.bullets.count && <Stat label="Bullets" q={b.bullets.count} />}
        {(b.video_share != null || b.aplus_share != null) && (
          <div className="flex flex-col gap-0.5 rounded-[10px] bg-sunken px-3 py-2.5 text-[12.5px]">
            <span className="text-[11px] uppercase tracking-wide text-muted">Rich content</span>
            <span>Video on {pct(b.video_share)}</span><span>A+ on {pct(b.aplus_share)}</span>
            <span className="text-[11.5px] text-muted">of {b.with_details} detailed listings</span>
          </div>
        )}
      </div>
      {!!b.keywords.length && (
        <div className="flex flex-col gap-1.5">
          <div className="text-[12.5px] font-medium">Title keywords shared by top listings <span className="font-normal text-muted">(how many titles use them; highlighted = missing from your listing)</span></div>
          <div className="flex flex-wrap gap-1">
            {b.keywords.map((k) => <Badge key={k.term} tone={k.in_your_listing ? "neutral" : "warning"}>{k.term} · {k.titles}</Badge>)}
          </div>
        </div>
      )}
      {(Object.keys(b.badges).length > 0 || b.sponsored_share != null) && (
        <div className="flex flex-wrap gap-2 text-[12px] text-muted">
          {Object.entries(b.badges).map(([k, v]) => <span key={k}><Crown className="mr-1 inline size-3" />{k}: {v}</span>)}
          {b.sponsored_share != null && <span>Sponsored in search results: {pct(b.sponsored_share)}</span>}
        </div>
      )}
    </Card>
  );
}

function AnalysisPanel({ product, total, reviews, analysis, loading, onDone }: { product: Product; total: number; reviews: number; analysis: Analysis | null; loading: boolean; onDone: () => void }) {
  const caps = useCapabilities();
  // Measured with qwen2.5:3b on a 4-core laptop CPU: ~2.5 min per 12 competitor reviews + ~6 min for grouping/comparison.
  const minutes = Math.round(Math.ceil(Math.min(reviews, 120) / 12) * 2.5 + 6);
  const [jobId, setJobId] = React.useState<string | null>(null);
  const run = async () => {
    try { const j = await post<Job>(`/products/${product.id}/competitors/analyze`, {}); setJobId(j.id); }
    catch (e) { toast.error((e as Error).message); }
  };
  const r = analysis?.result;
  return (
    <>
      <Card className="flex flex-wrap items-center gap-3 p-4">
        <Button variant="ai" onClick={run} disabled={!!jobId || caps.data?.text_ai === false}><Sparkles />Analyze the category</Button>
        <span className="text-[12px] text-muted">Compares your product with {total} listings{reviews ? ` and counts complaints in ${Math.min(reviews, 120)} competitor reviews` : ""}. About {minutes} min with the local AI on a laptop CPU (much faster with a free Gemini or Groq key); runs in the background.</span>
        {analysis && r && r.coverage.listings !== total && <Badge tone="warning">New listings since the last analysis</Badge>}
        {jobId && <div className="w-full"><JobCard jobId={jobId} onDone={() => { setJobId(null); onDone(); }} /></div>}
      </Card>
      {loading ? <Skeleton className="h-64" /> : r && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            {analysis!.provider && <ProviderBadge provider={analysis!.provider} model={analysis!.model} ai />}<span>· {timeAgo(analysis!.created_at)}</span>
            <span>· {r.coverage.listings} listings · {r.coverage.reviews_analysed} of {r.coverage.competitor_reviews} competitor reviews tagged</span>
          </div>
          {r.coverage.ai_error && <Notice tone="warning">AI analysis didn’t run ({r.coverage.ai_error}). The benchmark numbers are complete.</Notice>}
          {r.summary && <Card className="p-5"><p className="text-[14px] leading-relaxed">{r.summary}</p></Card>}
          {r.title_formula && <Notice tone="ai"><span className="font-medium">Title formula in this category:</span> {r.title_formula}</Notice>}
          <div className="grid gap-4 md:grid-cols-2">
            {!!r.competitor_review_themes.complaints.length && (
              <Section title="What customers complain about across competitors (counted)">
                {r.competitor_review_themes.complaints.slice(0, 8).map((t) => (
                  <details key={t.theme} className="mb-2">
                    <summary className="cursor-pointer list-none"><span className="font-medium first-letter:uppercase">{t.theme}</span>
                      <span className="text-muted"> · {t.reviews} reviews{t.competitors ? ` · ${t.competitors} listing${t.competitors === 1 ? "" : "s"}` : ""}</span></summary>
                    {t.quotes.map((q, i) => <div key={i} className="mt-1 border-l-2 border-border pl-2 text-[12.5px] italic text-muted">“{q.text}”{q.competitor && <span className="not-italic">: {q.competitor}</span>}</div>)}
                  </details>
                ))}
              </Section>
            )}
            {!!r.competitor_weaknesses?.length && (
              <Section title="Competitor weaknesses → your opportunity">
                {r.competitor_weaknesses.map((w, i) => <div key={i} className="mb-2"><div className="font-medium">{w.weakness}</div>
                  {w.evidence && <div className="text-[12px] text-muted">{w.evidence}</div>}{w.opportunity && <div>→ {w.opportunity}</div>}</div>)}
              </Section>
            )}
            {!!r.what_top_listings_do?.length && <Section title="What top listings do"><Bullets items={r.what_top_listings_do} /></Section>}
            {!!r.differentiation_angles?.length && (
              <Section title="Ways to stand out">{r.differentiation_angles.map((a, i) => <div key={i} className="mb-2"><div className="font-medium">{a.angle}</div>{a.why && <div className="text-muted">{a.why}</div>}</div>)}</Section>
            )}
            {!!r.listing_recommendations?.length && <Section title="Recommended changes to your listing"><Bullets items={r.listing_recommendations} /></Section>}
            {!!r.keywords_to_add?.length && <Section title="Keywords to add (used by top titles, missing from yours)"><div className="flex flex-wrap gap-1">{r.keywords_to_add.map((k) => <Badge key={k} tone="warning">{k}</Badge>)}</div></Section>}
            {!!r.bullet_patterns?.length && <Section title="Bullet patterns"><Bullets items={r.bullet_patterns} /></Section>}
            {!!r.image_patterns?.length && <Section title="Image, video & A+ patterns"><Bullets items={r.image_patterns} /></Section>}
            {r.price_positioning && <Section title="Price positioning">{r.price_positioning}</Section>}
          </div>
          {!!r.assumptions?.length && <Notice tone="warning"><div className="font-medium">Assumptions (verify these)</div><Bullets items={r.assumptions} /></Notice>}
        </div>
      )}
    </>
  );
}

function CompTable({ product, items, onChange }: { product: Product; items: Comp[]; onChange: () => void }) {
  const [confirm, setConfirm] = React.useState(false);
  const [q, setQ] = React.useState("");
  const shown = items.filter((c) => !q.trim() || (c.title ?? "").toLowerCase().includes(q.trim().toLowerCase()));
  return (
    <Card className="flex flex-col gap-3 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="mr-auto text-[15px] font-semibold">Collected listings <span className="font-normal text-muted">· untick ones that aren’t real competitors (accessories, other product types)</span></h3>
        <div className="relative"><Search className="absolute left-2.5 top-2.5 size-3.5 text-muted" /><Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter" className="w-44 pl-8" /></div>
        <Button size="sm" variant="ghost" onClick={() => setConfirm(true)}><Trash2 />Clear all</Button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[820px] text-[12.5px]">
          <thead className="text-left text-[11px] uppercase tracking-wide text-muted">
            <tr><th className="w-8 py-2" /><th className="py-2">Rank</th><th>Listing</th><th>Price</th><th>Rating</th><th>Reviews</th><th>Bought/mo</th><th>Details</th><th /></tr>
          </thead>
          <tbody className="divide-y divide-border">
            {shown.map((c) => (
              <tr key={c.id} className={c.included ? "" : "opacity-45"}>
                <td className="py-2"><input type="checkbox" checked={c.included} aria-label="Include in analysis"
                  onChange={async (e) => { await patch(`/products/${product.id}/competitors/${c.id}`, { included: e.target.checked }); onChange(); }} /></td>
                <td className="whitespace-nowrap">{c.rank ? `#${c.rank}` : c.position ? `pos ${c.position}` : "–"}</td>
                <td className="max-w-[420px] py-2">
                  <div className="flex items-start gap-2">
                    {/* eslint-disable-next-line @next/next/no-img-element -- marketplace CDN thumbnails, not optimisable */}
                    {c.image_url && <img src={c.image_url} alt="" className="size-9 shrink-0 rounded object-contain" referrerPolicy="no-referrer" />}
                    <div className="min-w-0">
                      <div className="line-clamp-2">{c.title ?? c.market_id}</div>
                      <div className="mt-0.5 flex flex-wrap gap-1">
                        {c.sponsored && <Badge tone="warning">Sponsored</Badge>}{c.badges.map((b) => <Badge key={b} tone="success">{b}</Badge>)}
                        {c.bsr && <span className="text-[11px] text-muted">BSR {c.bsr}</span>}
                      </div>
                    </div>
                  </div>
                </td>
                <td>{money(c.price, c.currency)}</td><td>{c.rating ? `${c.rating}★` : "–"}</td><td>{n0(c.review_count)}</td>
                <td>{c.monthly_bought ? `${n0(c.monthly_bought)}+` : "–"}</td>
                <td className="whitespace-nowrap">{c.has_details
                  ? <span className="text-muted">{[c.image_count ? `${c.image_count} img` : null, c.has_video ? "video" : null, c.has_aplus ? "A+" : null, c.review_samples ? `${c.review_samples} reviews` : null].filter(Boolean).join(" · ") || "saved"}</span>
                  : c.url ? <a href={c.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-primary hover:underline">open<ExternalLink className="size-3" /></a> : "–"}</td>
                <td><Button size="icon-sm" variant="ghost" aria-label="Remove" onClick={async () => { await del(`/products/${product.id}/competitors/${c.id}`); onChange(); }}><Trash2 /></Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Confirm open={confirm} onOpenChange={setConfirm} title="Remove all collected listings?" body="Past analyses are kept."
        onConfirm={async () => { await del(`/products/${product.id}/competitors`); setConfirm(false); onChange(); }} />
    </Card>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <Card className="p-4 text-[13px] leading-relaxed"><div className="mb-2 font-semibold">{title}</div>{children}</Card>;
}
function Bullets({ items }: { items?: string[] }) {
  if (!items?.length) return <span className="text-muted">—</span>;
  return <ul className="list-disc space-y-1 pl-4">{items.map((i) => <li key={i}>{i}</li>)}</ul>;
}
