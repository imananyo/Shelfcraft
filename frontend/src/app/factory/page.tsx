"use client";
import { Check, Download, Factory, Play, RefreshCw, Square, TriangleAlert } from "lucide-react";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { JobStatusBadge } from "@/components/shell/app-shell";
import { BrandSelect, ImageThumb } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Switch } from "@/components/ui/form";
import { Badge, Card, EmptyState, Notice, PageHeader, Progress, Skeleton } from "@/components/ui/misc";
import { download, post } from "@/lib/api";
import { useActiveBrand, useApi } from "@/lib/hooks";
import type { Job, Product } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";

interface Batch { id: string; name: string; total: number; counts: Record<string, number>; progress?: number; created_at: string; jobs?: Job[] }
const TYPES = [["listing_copy", "Listing copy (text)"], ["white_bg_main", "Main (white)"], ["lifestyle", "Lifestyle"], ["hero", "Hero"], ["feature", "Feature callouts"], ["comparison", "Comparison"],
  ["dimensions", "Dimensions"], ["steps", "How-to steps"], ["social", "Social 4:5"], ["ad_sb", "Sponsored Brand"], ["lifestyle_headline", "Lifestyle + headline"]];

function FactoryInner() {
  const sp = useSearchParams();
  const { brand } = useActiveBrand();
  const products = useApi<{ items: Product[] }>(["products", "factory"], "/products?limit=500&sort=name");
  const templates = useApi<{ id: string; name: string }[]>(["templates"], "/templates");
  const batches = useApi<Batch[]>(["factory-batches"], "/factory/batches", { refetchInterval: 4000 });
  const [selected, setSelected] = React.useState<string[]>([]);
  const [types, setTypes] = React.useState<string[]>(["white_bg_main", "feature"]);
  const [variants, setVariants] = React.useState(sp.get("variants") === "1");
  const [brandId, setBrandId] = React.useState("");
  const [templateId, setTemplateId] = React.useState("");
  const [style, setStyle] = React.useState("minimal");
  const [prompt, setPrompt] = React.useState("");
  const [name, setName] = React.useState("Factory run");
  const [preview, setPreview] = React.useState<{ count: number; estimated_minutes: number; warnings: string[]; limit: number } | null>(null);
  const [active, setActive] = React.useState<string | null>(sp.get("run"));
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { if (brand && !brandId) setBrandId(brand.id); }, [brand, brandId]);
  const body = { name, product_ids: selected, include_variants: variants, creative_types: types, brand_id: brandId || null, template_id: templateId || null, style, prompt };

  React.useEffect(() => {
    if (!selected.length || !types.length) { setPreview(null); return; }
    const t = setTimeout(() => post<typeof preview>("/factory/preview", body).then(setPreview).catch(() => setPreview(null)), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected.join(), types.join(), variants, templateId]);

  const start = async () => {
    setBusy(true);
    try { const b = await post<Batch>("/factory/batches", body); setActive(b.id); batches.refetch(); toast.success(`Queued ${b.total} creatives`); }
    catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title="Factory" description="Generate many creatives at once. Jobs run in the background with bounded concurrency (one heavy job at a time on this CPU) and can be retried or cancelled." />
      <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
        <div className="flex flex-col gap-6">
          <Card className="p-5">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-[14px] font-semibold">1 · Products <span className="font-normal text-muted">({selected.length} selected)</span></h3>
              <div className="flex gap-2 text-[12.5px]"><button className="font-medium text-primary hover:underline" onClick={() => setSelected(products.data?.items.map((p) => p.id) ?? [])}>Select all</button><button className="text-muted hover:underline" onClick={() => setSelected([])}>Clear</button></div>
            </div>
            {products.isLoading ? <Skeleton className="h-40" /> : !products.data?.items.length ? <EmptyState icon={<Factory />} title="No products" body="Add products first." className="py-8" /> : (
              <div className="grid max-h-80 grid-cols-1 gap-2 overflow-y-auto sm:grid-cols-2 scrollbar-thin">
                {products.data.items.map((p) => {
                  const on = selected.includes(p.id);
                  return (
                    <button key={p.id} onClick={() => setSelected((s) => (on ? s.filter((x) => x !== p.id) : [...s, p.id]))}
                      className={cn("flex items-center gap-3 rounded-[10px] border p-2 text-left", on ? "border-primary bg-primary-soft" : "border-border hover:bg-sunken")}>
                      <span className={cn("flex size-5 shrink-0 items-center justify-center rounded-[6px] border", on ? "border-primary bg-primary text-white" : "border-border-strong")}>{on && <Check className="size-3.5" />}</span>
                      <ImageThumb src={p.cover_url} alt={p.name} className="size-10 shrink-0" />
                      <span className="min-w-0 flex-1"><span className="block truncate text-[13px] font-medium">{p.name}</span><span className="text-[11px] text-muted">{p.variant_count} variants{!p.image_count && " · no photo"}</span></span>
                    </button>
                  );
                })}
              </div>
            )}
            <label className="mt-3 flex items-center gap-2 text-[13px]"><Switch checked={variants} onChange={setVariants} label="Include variants" />Generate per variant (variants with a color get a non-AI hue-shifted copy)</label>
          </Card>
          <Card className="p-5">
            <h3 className="mb-3 text-[14px] font-semibold">2 · Creative types</h3>
            <div className="flex flex-wrap gap-2">
              {TYPES.map(([k, l]) => <button key={k} onClick={() => setTypes((t) => (t.includes(k) ? t.filter((x) => x !== k) : [...t, k]))}
                className={cn("rounded-full border px-3 py-1.5 text-[12.5px] font-medium", types.includes(k) ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-sunken")}>{l}</button>)}
            </div>
          </Card>
          <Card className="grid gap-4 p-5 sm:grid-cols-2">
            <h3 className="text-[14px] font-semibold sm:col-span-2">3 · Settings</h3>
            <Field label="Run name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <Field label="Brand"><BrandSelect value={brandId} onChange={setBrandId} /></Field>
            <Field label="Template override" hint="For infographic types; default uses each type's template"><Select value={templateId} onChange={(e) => setTemplateId(e.target.value)}><option value="">Default per type</option>{templates.data?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select></Field>
            <Field label="Style"><Select value={style} onChange={(e) => setStyle(e.target.value)}>{["minimal", "natural", "luxury", "vibrant", "editorial", "tech"].map((s) => <option key={s}>{s}</option>)}</Select></Field>
            <Field label="Extra prompt for AI backgrounds" className="sm:col-span-2"><Input value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="e.g. warm autumn tones" /></Field>
          </Card>
        </div>
        <div className="flex flex-col gap-4 xl:sticky xl:top-0 xl:self-start">
          <Card className="flex flex-col gap-3 p-5">
            <h3 className="text-[14px] font-semibold">Output preview</h3>
            {preview ? (<>
              <div className="flex items-baseline gap-2"><span className="font-display text-3xl font-semibold tabular-nums">{preview.count}</span><span className="text-[13px] text-muted">creatives · ≈{preview.estimated_minutes} min on this CPU</span></div>
              <div className="text-xs text-muted">Limit {preview.limit} per batch to protect your machine and free-tier quotas.</div>
              {preview.warnings.map((w) => <Notice key={w} tone="warning" icon={<TriangleAlert />} className="text-xs">{w}</Notice>)}
            </>) : <p className="text-[13px] text-muted">Select products and creative types.</p>}
            <Button size="lg" onClick={start} loading={busy} disabled={!preview || preview.count === 0 || preview.count > preview.limit}><Play />Queue {preview?.count ?? 0} jobs</Button>
          </Card>
          <Card className="p-4">
            <h3 className="mb-2 text-[14px] font-semibold">Runs</h3>
            {!batches.data?.length ? <p className="py-4 text-center text-[13px] text-muted">No runs yet.</p> : batches.data.map((b) => {
              const done = (b.counts.succeeded ?? 0) + (b.counts.failed ?? 0) + (b.counts.cancelled ?? 0);
              return (
                <button key={b.id} onClick={() => setActive(b.id)} className={cn("mb-1 w-full rounded-[10px] p-2.5 text-left hover:bg-sunken", active === b.id && "bg-sunken")}>
                  <div className="flex items-center justify-between text-[13px]"><span className="truncate font-medium">{b.name}</span><span className="text-xs text-muted">{done}/{b.total}</span></div>
                  <Progress value={b.total ? done / b.total : 0} className="mt-1.5" />
                  <div className="mt-1 flex gap-1.5 text-[11px] text-muted">{timeAgo(b.created_at)}{b.counts.failed ? <Badge tone="danger">{b.counts.failed} failed</Badge> : null}{b.counts.running ? <Badge tone="ai">running</Badge> : null}</div>
                </button>
              );
            })}
          </Card>
        </div>
      </div>
      {active && <BatchDetail id={active} />}
    </>
  );
}

function BatchDetail({ id }: { id: string }) {
  const q = useApi<Batch>(["factory-batch", id], `/factory/batches/${id}`, { refetchInterval: 2000 });
  const b = q.data;
  if (!b) return <Skeleton className="mt-6 h-40" />;
  return (
    <Card className="mt-6 p-5">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h3 className="text-[15px] font-semibold">{b.name}</h3>
        <span className="text-[13px] text-muted">{Object.entries(b.counts).map(([k, v]) => `${v} ${k}`).join(" · ")}</span>
        <div className="ml-auto flex gap-2">
          <Button size="sm" variant="outline" disabled={!b.counts.queued} onClick={async () => { const r = await post<{ cancelled: number }>(`/factory/batches/${id}/cancel`); toast.success(`Cancelled ${r.cancelled} pending`); q.refetch(); }}><Square />Cancel pending</Button>
          <Button size="sm" variant="outline" disabled={!b.counts.failed && !b.counts.cancelled} onClick={async () => { const r = await post<{ retried: number }>(`/factory/batches/${id}/retry-failed`); toast.success(`Retrying ${r.retried}`); q.refetch(); }}><RefreshCw />Retry failed</Button>
          <Button size="sm" disabled={!b.counts.succeeded} onClick={() => download(`/factory/batches/${id}/download`).catch((e) => toast.error(e.message))}><Download />Download ZIP</Button>
        </div>
      </div>
      <Progress value={b.progress ?? 0} className="mb-4" />
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead className="text-left text-xs text-muted"><tr><th className="py-2 font-medium">Product</th><th className="font-medium">Type</th><th className="font-medium">Status</th><th className="font-medium">Detail</th></tr></thead>
          <tbody>
            {b.jobs?.map((j) => (
              <tr key={j.id} className="border-t border-border">
                <td className="py-2 pr-3">{String(j.payload_summary.product_name ?? "Product")}{j.payload_summary.variant_name ? <span className="text-muted"> · {String(j.payload_summary.variant_name)}</span> : null}</td>
                <td className="pr-3">{String(j.payload_summary.creative_type ?? "")}</td>
                <td className="pr-3"><JobStatusBadge status={j.status} /></td>
                <td className="max-w-md truncate text-xs text-muted">{j.status === "running" ? <Progress value={j.progress} tone="ai" className="w-40" /> : j.status === "failed" ? j.error : j.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export default function Page() {
  return <React.Suspense><FactoryInner /></React.Suspense>;
}
