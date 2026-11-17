"use client";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, ExternalLink, FileUp, Lightbulb, MessageSquareQuote, Search, Sparkles, Star, ThumbsDown, ThumbsUp, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { JobCard } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input, Select, Textarea } from "@/components/ui/form";
import { Badge, Card, EmptyState, Notice, ProviderBadge, Skeleton } from "@/components/ui/misc";
import { Confirm } from "@/components/ui/overlay";
import { del, post } from "@/lib/api";
import { useApi, useCapabilities } from "@/lib/hooks";
import type { Job, Product } from "@/lib/types";
import { timeAgo } from "@/lib/utils";

type Review = { id: string; source: string; rating?: number | null; title?: string | null; text: string; author?: string | null;
  review_date?: string | null; verified?: boolean | null; variant?: string | null; helpful_votes?: number | null };
type Phrase = { phrase: string; reviews: number; share: number };
type Stats = { count: number; rated: number; average: number | null; histogram: Record<string, number>; verified_share: number | null;
  sources: Record<string, number>; date_range: [string, string] | null; by_variant: { variant: string; reviews: number; average: number }[];
  by_month: { month: string; reviews: number; average: number }[]; phrases: { positive: Phrase[]; negative: Phrase[] } };
type Theme = { theme: string; reviews: number; share: number; avg_rating: number | null; labels: string[];
  quotes: { text: string; rating?: number | null }[] };
type Analysis = { id: string; provider?: string; model?: string; created_at: string; result: {
  stats: Stats; themes: { praise: Theme[]; complaints: Theme[]; requests: Theme[] }; use_cases: { use_case: string; reviews: number }[];
  summary?: string; top_pain_points?: { pain: string; theme?: string; how_to_address?: string }[];
  objections?: { objection: string; response: string }[]; buyer_motivations?: string[]; feature_requests?: string[];
  listing_recommendations?: string[]; image_recommendations?: string[]; assumptions?: string[];
  coverage: { total_reviews: number; sampled: number; analysed: number; skipped: number; sample_note?: string | null; ai_error?: string | null } } };
type ImportResult = { added: number; duplicates: number; total: number;
  sources: { name: string; found: number; added: number; duplicates: number; error?: string; warning?: string }[] };

const FILE_BATCH = 5;

function amazonDomain(p: Product) {
  const m = /amazon\.[a-z.]+/i.exec(p.source_url ?? "");
  return m ? m[0].toLowerCase() : "amazon.com";
}

export function ProductReviews({ product }: { product: Product }) {
  const qc = useQueryClient();
  const stats = useApi<Stats>(["review-stats", product.id], `/products/${product.id}/reviews/stats`);
  const analysis = useApi<Analysis | null>(["review-analysis", product.id], `/products/${product.id}/reviews/analysis`);
  const refresh = () => ["review-stats", "reviews", "review-analysis"].forEach((k) => qc.invalidateQueries({ queryKey: [k, product.id] }));
  const s = stats.data;
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
        <AddReviews product={product} onAdded={refresh} />
        <div className="flex flex-col gap-4">
          {stats.isLoading ? <Skeleton className="h-40" /> : s && s.count > 0 ? <StatsCard s={s} /> : (
            <EmptyState icon={<MessageSquareQuote />} title="No reviews collected yet"
              body="Add every review page you can: Shelfcraft keeps them per product, removes duplicates and analyses all of them together." />
          )}
          {!!s?.count && <AnalysisPanel product={product} count={s.count} analysis={analysis.data ?? null} loading={analysis.isLoading} onDone={refresh} />}
        </div>
      </div>
      {!!s?.count && <ReviewList product={product} onChange={refresh} />}
    </div>
  );
}

function AddReviews({ product, onAdded }: { product: Product; onAdded: () => void }) {
  const [busy, setBusy] = React.useState(false);
  const [text, setText] = React.useState("");
  const [result, setResult] = React.useState<ImportResult | null>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const walmartId = product.specifications?.["Walmart item ID"];
  const dom = amazonDomain(product);
  const amazonBase = product.asin ? `https://www.${dom}/product-reviews/${product.asin}/?sortBy=recent` : null;

  const send = async (sources: { name: string; content: string }[]) => {
    setBusy(true);
    const merged: ImportResult = { added: 0, duplicates: 0, total: 0, sources: [] };
    try {
      for (let i = 0; i < sources.length; i += FILE_BATCH) {
        try {
          const r = await post<ImportResult>(`/products/${product.id}/reviews/import`, { sources: sources.slice(i, i + FILE_BATCH) });
          merged.added += r.added; merged.duplicates += r.duplicates; merged.total = r.total; merged.sources.push(...r.sources);
        } catch (e) {
          merged.sources.push(...sources.slice(i, i + FILE_BATCH).map((x) => ({ name: x.name, found: 0, added: 0, duplicates: 0, error: (e as Error).message })));
        }
      }
      setResult(merged);
      if (merged.added) toast.success(`${merged.added} new review${merged.added === 1 ? "" : "s"} added (${merged.total} in total)`);
      else toast.warning(merged.duplicates ? "Those reviews were already collected" : "No reviews were found");
      onAdded();
    } finally { setBusy(false); }
  };

  const onFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    const list = await Promise.all(Array.from(files).map(async (f) => ({ name: f.name, content: await f.text() })));
    const tooBig = list.filter((f) => f.content.length > 8_000_000);
    if (tooBig.length) toast.error(`${tooBig.map((f) => f.name).join(", ")} is larger than 8 MB; save as “Webpage, HTML only”.`);
    await send(list.filter((f) => f.content.length <= 8_000_000 && f.content.trim()));
  };

  const link = (label: string, url: string) => (
    <a href={url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-[12px] hover:bg-sunken">
      {label}<ExternalLink className="size-3" />
    </a>
  );

  return (
    <Card className="flex flex-col gap-4 p-5 lg:sticky lg:top-0 lg:self-start">
      <div>
        <h3 className="text-[15px] font-semibold">Collect reviews</h3>
        <p className="text-[12.5px] text-muted">Add as many as you can. Every source is merged into one set and duplicates are skipped automatically.</p>
      </div>
      {amazonBase && (
        <div className="flex flex-col gap-2 text-[12.5px]">
          <div className="font-medium">Amazon review pages</div>
          <div className="flex flex-wrap gap-1.5">
            {link("All, newest", `${amazonBase}&pageNumber=1`)}
            {link("Critical", `${amazonBase}&filterByStar=critical&pageNumber=1`)}
            {link("1★", `${amazonBase}&filterByStar=one_star&pageNumber=1`)}
            {link("2★", `${amazonBase}&filterByStar=two_star&pageNumber=1`)}
            {link("3★", `${amazonBase}&filterByStar=three_star&pageNumber=1`)}
            {link("Positive", `${amazonBase}&filterByStar=positive&pageNumber=1`)}
          </div>
          <p className="text-muted">Amazon shows about 10 reviews per page and asks you to be signed in. Open a filter, save each page with <kbd>Ctrl+S</kbd> / <kbd>⌘S</kbd>, click “Next page” and save again. Then select all the saved files below at once. The critical and 1–3★ filters find the most useful complaints quickly.</p>
        </div>
      )}
      {walmartId && (
        <div className="flex flex-col gap-2 text-[12.5px]">
          <div className="font-medium">Walmart review pages</div>
          <div className="flex flex-wrap gap-1.5">
            {[1, 2, 3].map((n) => <React.Fragment key={n}>{link(`Page ${n}`, `https://www.walmart.com/reviews/product/${walmartId}?page=${n}`)}</React.Fragment>)}
            {link("Lowest rated", `https://www.walmart.com/reviews/product/${walmartId}?sort=rating-asc&page=1`)}
          </div>
        </div>
      )}
      <div className="flex flex-col gap-1.5">
        <Button variant="outline" onClick={() => fileRef.current?.click()} loading={busy}><FileUp />Upload saved pages or CSV files</Button>
        <span className="text-[11.5px] text-muted">Saved review pages (.html) from Amazon, Walmart or your store, or CSV exports from Helium 10, Jungle Scout, Seller Central or a spreadsheet. You can pick many files at once.</span>
        <input ref={fileRef} type="file" multiple accept=".html,.htm,.csv,.tsv,.txt,text/html,text/csv,text/plain" className="hidden"
          onChange={(e) => { const f = e.target.files; onFiles(f).finally(() => { e.target.value = ""; }); }} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder={"Or paste reviews, one per paragraph:\n\n5★ Love it\nKeeps my coffee hot all morning.\n\n2★ Lid leaks after a week."} />
        <Button variant="secondary" disabled={!text.trim() || busy} onClick={() => send([{ name: "Pasted text", content: text }]).then(() => setText(""))}>Add pasted reviews</Button>
      </div>
      {result && (
        <Notice tone={result.added ? "success" : "warning"}>
          <div className="font-medium">{result.added} added · {result.duplicates} already collected · {result.total} in total</div>
          <ul className="mt-1 space-y-0.5 text-[12px]">
            {result.sources.map((x, i) => (
              <li key={i}><span className="font-medium">{x.name}</span>: {x.error ? <span className="text-danger">{x.error}</span> : `${x.found} found, ${x.added} new`}
                {x.warning && <span className="text-muted"> ({x.warning})</span>}</li>
            ))}
          </ul>
        </Notice>
      )}
    </Card>
  );
}

function Stars({ value }: { value?: number | null }) {
  if (!value) return null;
  return <span className="inline-flex items-center gap-0.5 text-[12px] font-medium text-warning"><Star className="size-3 fill-current" />{value.toFixed(value % 1 ? 1 : 0)}</span>;
}

function StatsCard({ s }: { s: Stats }) {
  const max = Math.max(1, ...Object.values(s.histogram));
  return (
    <Card className="grid gap-5 p-5 md:grid-cols-[160px_1fr_1fr]">
      <div className="flex flex-col gap-1">
        <div className="text-[34px] font-semibold leading-none">{s.average ?? "–"}<span className="text-[15px] text-muted"> / 5</span></div>
        <div className="text-[13px] text-muted">{s.count} reviews collected</div>
        {s.verified_share !== null && <div className="text-[12px] text-muted">{Math.round(s.verified_share * 100)}% verified purchases</div>}
        {s.date_range && <div className="text-[12px] text-muted">{s.date_range[0]} → {s.date_range[1]}</div>}
        <div className="mt-1 flex flex-wrap gap-1">{Object.entries(s.sources).map(([k, v]) => <Badge key={k}>{k} · {v}</Badge>)}</div>
      </div>
      <div className="flex flex-col gap-1.5">
        {Object.entries(s.histogram).map(([star, n]) => (
          <div key={star} className="flex items-center gap-2 text-[12px]">
            <span className="w-6 text-right">{star}★</span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-sunken"><div className="h-full rounded-full bg-warning" style={{ width: `${(n / max) * 100}%` }} /></div>
            <span className="w-14 text-muted">{n} · {s.count ? Math.round((n / s.count) * 100) : 0}%</span>
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-2 text-[12px]">
        <div className="text-[11px] font-medium uppercase tracking-wide text-muted">Recurring phrases (exact counts, no AI)</div>
        <PhraseChips items={s.phrases.positive.slice(0, 6)} tone="success" />
        <PhraseChips items={s.phrases.negative.slice(0, 6)} tone="danger" />
        {!s.phrases.positive.length && !s.phrases.negative.length && <span className="text-muted">Need a few more reviews to find recurring phrases.</span>}
      </div>
    </Card>
  );
}

function PhraseChips({ items, tone }: { items: Phrase[]; tone: "success" | "danger" }) {
  if (!items.length) return null;
  return <div className="flex flex-wrap gap-1">{items.map((p) => <Badge key={p.phrase} tone={tone}>“{p.phrase}” · {p.reviews}</Badge>)}</div>;
}

function AnalysisPanel({ product, count, analysis, loading, onDone }: { product: Product; count: number; analysis: Analysis | null; loading: boolean; onDone: () => void }) {
  const caps = useCapabilities();
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [max, setMax] = React.useState("400");
  const n = Math.min(count, Number(max));
  // Measured with qwen2.5:3b on a 4-core laptop CPU: ~2.5 min per batch of 12 reviews + ~3 min for grouping/summary.
  // Hosted free providers (Gemini, Groq) are much faster.
  const minutes = Math.max(2, Math.round(Math.ceil(n / 12) * 2.5 + 3));
  const run = async () => {
    try { const j = await post<Job>(`/products/${product.id}/reviews/analyze`, { max_reviews: Number(max) }); setJobId(j.id); }
    catch (e) { toast.error((e as Error).message); }
  };
  const r = analysis?.result;
  const stale = analysis && r && r.coverage.total_reviews !== count;
  return (
    <>
      <Card className="flex flex-wrap items-center gap-3 p-4">
        <Button variant="ai" onClick={run} disabled={!!jobId || caps.data?.text_ai === false}><Sparkles />Analyze {n === count ? `all ${count}` : `${n} of ${count}`} reviews</Button>
        {count > 200 && (
          <Select value={max} onChange={(e) => setMax(e.target.value)} className="w-40" aria-label="Reviews to analyse">
            {["200", "400", "1000", "2000"].map((v) => <option key={v} value={v}>Up to {v}</option>)}
          </Select>
        )}
        <span className="text-[12px] text-muted">About {minutes} min with the local AI on a laptop CPU (much faster with a free Gemini or Groq key). Runs in the background, so you can keep working.</span>
        {stale && <Badge tone="warning">New reviews since the last analysis</Badge>}
        {caps.data?.text_ai === false && <Notice tone="warning" className="w-full">No text AI is reachable. The star statistics and phrases above still work without AI.</Notice>}
        {jobId && <div className="w-full"><JobCard jobId={jobId} onDone={() => { setJobId(null); onDone(); }} /></div>}
      </Card>
      {loading ? <Skeleton className="h-64" /> : r && <AnalysisView a={analysis!} />}
    </>
  );
}

function AnalysisView({ a }: { a: Analysis }) {
  const r = a.result;
  const c = r.coverage;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        {a.provider && <ProviderBadge provider={a.provider} model={a.model} ai />}<span>· {timeAgo(a.created_at)}</span>
        <span>· {c.analysed} of {c.total_reviews} reviews tagged{c.skipped ? ` (${c.skipped} skipped after a model error)` : ""}</span>
      </div>
      {c.sample_note && <Notice>{c.sample_note}</Notice>}
      {c.ai_error && <Notice tone="warning">AI analysis didn’t run ({c.ai_error}). The statistics are complete; start Ollama or add a free key, then analyse again.</Notice>}
      {r.summary && <Card className="p-5"><p className="text-[14px] leading-relaxed">{r.summary}</p></Card>}
      {c.analysed > 0 && (
        <div className="grid gap-4 xl:grid-cols-3">
          <ThemeColumn title="Complaints" icon={<ThumbsDown />} rows={r.themes.complaints} tone="bg-danger" n={c.analysed} />
          <ThemeColumn title="Praise" icon={<ThumbsUp />} rows={r.themes.praise} tone="bg-success" n={c.analysed} />
          <ThemeColumn title="Requests" icon={<Lightbulb />} rows={r.themes.requests} tone="bg-ai" n={c.analysed} />
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        {!!r.top_pain_points?.length && (
          <Section title="Top pain points and how to answer them">
            {r.top_pain_points.map((p, i) => <div key={i} className="mb-2"><div className="font-medium">{p.pain}</div>{p.how_to_address && <div className="text-muted">→ {p.how_to_address}</div>}</div>)}
          </Section>
        )}
        {!!r.objections?.length && (
          <Section title="Shopper objections">
            {r.objections.map((o, i) => <div key={i} className="mb-2"><div className="font-medium">{o.objection}</div><div className="text-muted">{o.response}</div></div>)}
          </Section>
        )}
        {!!r.listing_recommendations?.length && <Section title="Listing copy recommendations"><Bullets items={r.listing_recommendations} /></Section>}
        {!!r.image_recommendations?.length && <Section title="Image & infographic ideas"><Bullets items={r.image_recommendations} /></Section>}
        {!!r.buyer_motivations?.length && <Section title="Why people buy"><Bullets items={r.buyer_motivations} /></Section>}
        {!!r.use_cases?.length && (
          <Section title="Use cases mentioned (counted)">
            <div className="flex flex-wrap gap-1">{r.use_cases.map((u) => <Badge key={u.use_case}>{u.use_case} · {u.reviews}</Badge>)}</div>
          </Section>
        )}
        {!!r.stats.by_variant?.length && (
          <Section title="Rating by variant">
            {r.stats.by_variant.map((v) => <div key={v.variant} className="flex justify-between gap-2"><span className="truncate">{v.variant}</span><span className="text-muted">{v.average}★ · {v.reviews}</span></div>)}
          </Section>
        )}
        {r.stats.by_month?.length > 2 && (
          <Section title="Rating over time">
            {r.stats.by_month.slice(-12).map((m) => <div key={m.month} className="flex justify-between gap-2"><span>{m.month}</span><span className="text-muted">{m.average}★ · {m.reviews} reviews</span></div>)}
          </Section>
        )}
      </div>
      {!!r.assumptions?.length && <Notice tone="warning"><div className="font-medium">Assumptions (verify these)</div><Bullets items={r.assumptions} /></Notice>}
    </div>
  );
}

function ThemeColumn({ title, icon, rows, tone, n }: { title: string; icon: React.ReactNode; rows: Theme[]; tone: string; n: number }) {
  return (
    <Card className="flex flex-col gap-3 p-4 text-[13px]">
      <div className="flex items-center gap-2 font-semibold [&_svg]:size-4 [&_svg]:text-primary">{icon}{title}</div>
      {!rows.length && <span className="text-muted">None mentioned.</span>}
      {rows.map((t) => (
        <details key={t.theme} className="group">
          <summary className="flex cursor-pointer list-none flex-col gap-1">
            <div className="flex items-baseline justify-between gap-2"><span className="font-medium first-letter:uppercase">{t.theme}</span>
              <span className="shrink-0 text-[12px] text-muted">{t.reviews} · {Math.round(t.share * 100)}%{t.avg_rating ? ` · ${t.avg_rating}★` : ""}</span></div>
            <div className="h-1.5 overflow-hidden rounded-full bg-sunken"><div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.max(3, (t.reviews / n) * 100)}%` }} /></div>
          </summary>
          <div className="mt-2 flex flex-col gap-1.5 border-l-2 border-border pl-3">
            {t.quotes.map((q, i) => <div key={i} className="text-[12.5px] italic text-muted">“{q.text}”{q.rating ? <span className="not-italic"> · {q.rating}★</span> : null}</div>)}
          </div>
        </details>
      ))}
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

function ReviewList({ product, onChange }: { product: Product; onChange: () => void }) {
  const [rating, setRating] = React.useState<number | null>(null);
  const [q, setQ] = React.useState("");
  const [page, setPage] = React.useState(0);
  const [confirm, setConfirm] = React.useState(false);
  const per = 20;
  const params = new URLSearchParams({ offset: String(page * per), limit: String(per) });
  if (rating) params.set("rating", String(rating));
  if (q.trim()) params.set("q", q.trim());
  const list = useApi<{ items: Review[]; total: number }>(["reviews", product.id, rating, q, page], `/products/${product.id}/reviews?${params}`);
  const pages = Math.max(1, Math.ceil((list.data?.total ?? 0) / per));
  return (
    <Card className="flex flex-col gap-3 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="mr-auto text-[15px] font-semibold">Collected reviews</h3>
        <div className="flex gap-1">
          {[null, 5, 4, 3, 2, 1].map((s) => (
            <Button key={s ?? 0} size="sm" variant={rating === s ? "primary" : "outline"} onClick={() => { setRating(s); setPage(0); }}>{s ? `${s}★` : "All"}</Button>
          ))}
        </div>
        <div className="relative"><Search className="absolute left-2.5 top-2.5 size-3.5 text-muted" />
          <Input value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} placeholder="Search reviews" className="w-48 pl-8" /></div>
        <Button size="sm" variant="ghost" onClick={() => setConfirm(true)}><Trash2 />Clear all</Button>
      </div>
      {list.isLoading ? <Skeleton className="h-40" /> : (
        <div className="flex flex-col divide-y divide-border">
          {list.data?.items.map((r) => (
            <div key={r.id} className="flex gap-3 py-3 text-[13px]">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2"><Stars value={r.rating} />{r.title && <span className="font-medium">{r.title}</span>}
                  {r.verified && <Badge tone="success">Verified</Badge>}{r.variant && <Badge>{r.variant}</Badge>}</div>
                <p className="mt-1 whitespace-pre-line text-foreground/90">{r.text}</p>
                <div className="mt-1 text-[11.5px] text-muted">{[r.author, r.review_date, r.source, r.helpful_votes ? `${r.helpful_votes} found helpful` : null].filter(Boolean).join(" · ")}</div>
              </div>
              <Button size="icon-sm" variant="ghost" aria-label="Delete review" onClick={async () => { await del(`/products/${product.id}/reviews/${r.id}`); onChange(); }}><Trash2 /></Button>
            </div>
          ))}
          {!list.data?.items.length && <div className="py-6 text-center text-[13px] text-muted">No reviews match.</div>}
        </div>
      )}
      {pages > 1 && (
        <div className="flex items-center justify-end gap-2 text-[12px] text-muted">
          <Button size="icon-sm" variant="outline" disabled={page === 0} onClick={() => setPage(page - 1)} aria-label="Previous page"><ChevronLeft /></Button>
          Page {page + 1} of {pages}
          <Button size="icon-sm" variant="outline" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)} aria-label="Next page"><ChevronRight /></Button>
        </div>
      )}
      <Confirm open={confirm} onOpenChange={setConfirm} title="Delete all collected reviews?" body="Past analyses are kept. You can add the reviews again any time."
        onConfirm={async () => { await del(`/products/${product.id}/reviews`); setConfirm(false); onChange(); toast.success("Reviews cleared"); }} />
    </Card>
  );
}
