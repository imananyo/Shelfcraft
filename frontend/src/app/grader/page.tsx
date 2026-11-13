"use client";
import { CircleAlert, CircleCheck, Gauge, ImagePlus, Sparkles, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { AssetPicker, ImageThumb } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Field, Input, ListInput, Select, Switch, Textarea } from "@/components/ui/form";
import { Badge, Card, Notice, PageHeader, ProviderBadge, Tabs, TabPanel } from "@/components/ui/misc";
import { post } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Asset } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Check { label: string; passed: boolean; points: number; max: number; detail: string; fix: string; severity: string; section?: string }
interface Result {
  score: number; grade: string; sections: { key: string; score: number; checks: Check[] }[]; top_fixes: Check[]; note: string;
  ai_review?: { strengths?: string[]; weaknesses?: string[]; unanswered_questions?: string[]; rewrite_suggestions?: { field: string; suggestion: string }[]; provider?: string; model?: string; error?: string };
}
const SECTION: Record<string, string> = { title: "Title", bullets: "Bullet points", description: "Description", search_terms: "Search terms", images: "Images", aplus: "A+ content" };
const tone = (s: number) => (s >= 85 ? "text-success" : s >= 65 ? "text-[color-mix(in_oklch,var(--warning)_75%,black)] dark:text-warning" : "text-danger");

function GraderInner() {
  const sp = useSearchParams();
  const listings = useApi<{ id: string; name: string; marketplace: string; has_copy: boolean }[]>(["listings"], "/listings");
  const [mode, setMode] = React.useState(sp.get("listing") ? "mine" : "paste");
  const [listingId, setListingId] = React.useState(sp.get("listing") ?? "");
  const [f, setF] = React.useState({ marketplace: "amazon", brand: "", title: "", description: "", search_terms: "", keywords: "" });
  const [bullets, setBullets] = React.useState<string[]>(["", "", "", "", ""]);
  const [images, setImages] = React.useState<Asset[]>([]);
  const [aplus, setAplus] = React.useState(false);
  const [ai, setAi] = React.useState(false);
  const [picker, setPicker] = React.useState(false);
  const [res, setRes] = React.useState<Result | null>(null);
  const [busy, setBusy] = React.useState(false);
  const run = async () => {
    setBusy(true);
    try {
      const body = mode === "mine" ? { listing_id: listingId, ai_review: ai } : {
        ...f, keywords: f.keywords.split(",").map((s) => s.trim()).filter(Boolean), bullets: bullets.filter((b) => b.trim()),
        asset_ids: images.map((a) => a.id), has_aplus: aplus, ai_review: ai, brand: f.brand || null,
      };
      setRes(await post<Result>("/grader", body));
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <>
      <PageHeader title="Listing grader" description="A transparent score for any listing — yours or one you paste in — with concrete fixes. Rule-based and free; optional AI review." />
      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        <Card className="p-5">
          <Tabs value={mode} onValueChange={setMode} tabs={[{ value: "paste", label: "Paste a listing" }, { value: "mine", label: "One of my listings" }]}>
            <TabPanel value="mine" className="flex flex-col gap-3">
              <Field label="Listing"><Select value={listingId} onChange={(e) => setListingId(e.target.value)}><option value="">Choose…</option>
                {listings.data?.filter((l) => l.has_copy).map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</Select></Field>
              <p className="text-xs text-muted">Uses the listing&apos;s copy, its generated image set and whether the product has A+ content.</p>
            </TabPanel>
            <TabPanel value="paste" className="flex flex-col gap-3">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Marketplace"><Select value={f.marketplace} onChange={(e) => setF({ ...f, marketplace: e.target.value })}>
                  {[["amazon", "Amazon"], ["amazon_mobile", "Amazon Mobile"], ["shopify", "Shopify"], ["walmart", "Walmart"], ["tiktok", "TikTok Shop"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
                <Field label="Brand"><Input value={f.brand} onChange={(e) => setF({ ...f, brand: e.target.value })} /></Field>
              </div>
              <Field label="Title" aside={`${f.title.length} chars`}><Textarea rows={2} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
              <Field label="Bullet points"><ListInput multiline value={bullets} onChange={setBullets} max={10} /></Field>
              <Field label="Description"><Textarea rows={4} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Search terms"><Input value={f.search_terms} onChange={(e) => setF({ ...f, search_terms: e.target.value })} /></Field>
                <Field label="Target keywords" hint="comma separated"><Input value={f.keywords} onChange={(e) => setF({ ...f, keywords: e.target.value })} /></Field>
              </div>
              <Field label={`Images (${images.length})`} hint="First image = main image">
                <div className="flex flex-wrap gap-2">
                  {images.map((a, i) => <div key={a.id + i} className="relative"><ImageThumb src={a.thumb_url} alt="" className="size-16" />
                    <button aria-label="Remove" className="absolute -right-1 -top-1 rounded-full bg-surface p-0.5 shadow" onClick={() => setImages((s) => s.filter((_, j) => j !== i))}><X className="size-3" /></button></div>)}
                  <button onClick={() => setPicker(true)} className="flex size-16 items-center justify-center rounded-[10px] border border-dashed border-border-strong text-muted hover:border-primary"><ImagePlus className="size-5" /></button>
                </div>
              </Field>
              <label className="flex items-center gap-2 text-[13px]"><Switch checked={aplus} onChange={setAplus} label="Has A+ content" />Listing has A+ content</label>
            </TabPanel>
          </Tabs>
          <div className="mt-4 flex items-center justify-between border-t border-border pt-4">
            <label className="flex items-center gap-2 text-[13px]"><Switch checked={ai} onChange={setAi} label="AI review" />Add AI review (free/local model)</label>
            <Button size="lg" onClick={run} loading={busy} disabled={mode === "mine" && !listingId}><Gauge />Grade listing</Button>
          </div>
        </Card>
        <div className="flex flex-col gap-4">
          {!res ? <Card className="flex flex-col items-center justify-center gap-2 p-10 text-center text-[13px] text-muted"><Gauge className="size-8" />Your score appears here.</Card> : (<>
            <Card className="flex items-center gap-6 p-6">
              <div className={cn("flex size-24 shrink-0 flex-col items-center justify-center rounded-full border-4", res.score >= 85 ? "border-success" : res.score >= 65 ? "border-warning" : "border-danger")}>
                <span className="font-display text-3xl font-semibold tabular-nums">{res.score}</span><span className="text-[11px] text-muted">/ 100</span>
              </div>
              <div><div className="font-display text-2xl font-semibold">Grade {res.grade}</div><p className="text-[12.5px] text-muted">{res.note}</p></div>
            </Card>
            <Card className="grid grid-cols-2 gap-3 p-5 sm:grid-cols-3">
              {res.sections.map((s) => <div key={s.key}><div className="text-xs text-muted">{SECTION[s.key]}</div><div className={cn("font-display text-xl font-semibold tabular-nums", tone(s.score))}>{s.score}</div></div>)}
            </Card>
            {res.top_fixes.length > 0 && (
              <Card className="p-5">
                <h3 className="mb-2 text-[14px] font-semibold">Top fixes</h3>
                <ol className="flex flex-col gap-2">
                  {res.top_fixes.map((c, i) => (
                    <li key={i} className="flex gap-2 text-[13px]"><CircleAlert className={cn("mt-0.5 size-4 shrink-0", c.severity === "error" ? "text-danger" : "text-warning")} />
                      <span><Badge className="mr-1.5">{SECTION[c.section ?? ""]}</Badge>{c.fix}{c.detail && <span className="text-muted"> ({c.detail})</span>}</span></li>
                  ))}
                </ol>
              </Card>
            )}
            <Card className="p-5">
              <h3 className="mb-2 text-[14px] font-semibold">All checks</h3>
              {res.sections.map((s) => (
                <div key={s.key} className="mb-3">
                  <div className="mb-1 text-xs font-medium uppercase tracking-wider text-muted">{SECTION[s.key]}</div>
                  {s.checks.map((c, i) => (
                    <div key={i} className="flex items-center gap-2 py-0.5 text-[12.5px]">
                      {c.passed ? <CircleCheck className="size-3.5 text-success" /> : <CircleAlert className="size-3.5 text-warning" />}
                      <span className="flex-1">{c.label}</span><span className="text-muted">{c.detail}</span><span className="w-10 text-right tabular-nums text-muted">{c.points}/{c.max}</span>
                    </div>
                  ))}
                </div>
              ))}
            </Card>
            {res.ai_review && (
              <Card className="p-5 text-[13px]">
                <div className="mb-2 flex items-center justify-between"><h3 className="flex items-center gap-1.5 text-[14px] font-semibold"><Sparkles className="size-4 text-ai" />AI review</h3>
                  {res.ai_review.provider && <ProviderBadge provider={res.ai_review.provider} model={res.ai_review.model} ai />}</div>
                {res.ai_review.error ? <Notice tone="warning">{res.ai_review.error}</Notice> : (<>
                  {!!res.ai_review.strengths?.length && <><div className="font-medium text-success">Strengths</div><ul className="mb-2 list-disc pl-4">{res.ai_review.strengths.map((x) => <li key={x}>{x}</li>)}</ul></>}
                  {!!res.ai_review.weaknesses?.length && <><div className="font-medium text-danger">Weaknesses</div><ul className="mb-2 list-disc pl-4">{res.ai_review.weaknesses.map((x) => <li key={x}>{x}</li>)}</ul></>}
                  {!!res.ai_review.unanswered_questions?.length && <><div className="font-medium">Questions shoppers may still have</div><ul className="list-disc pl-4">{res.ai_review.unanswered_questions.map((x) => <li key={x}>{x}</li>)}</ul></>}
                </>)}
              </Card>
            )}
          </>)}
        </div>
      </div>
      <AssetPicker open={picker} onOpenChange={setPicker} onPick={(a) => setImages((s) => [...s, a])} title="Add a listing image" />
    </>
  );
}

export default function Page() {
  return <React.Suspense><GraderInner /></React.Suspense>;
}
