"use client";
import { Cpu, Images, Info, Shuffle, Sparkles } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { QuickAddProduct } from "@/components/quick-add-product";
import { AssetResult, BrandSelect, JobCard, ProductSelect } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Switch, Textarea } from "@/components/ui/form";
import { Card, EmptyState, Notice, PageHeader, Skeleton } from "@/components/ui/misc";
import { post } from "@/lib/api";
import { useActiveBrand, useApi, useCapabilities, useProviders } from "@/lib/hooks";
import type { Asset, Job, Product } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Options { creative_types: Record<string, string>; modes: Record<string, string>; styles: string[] }
interface Session { id: string; jobs: Job[]; assets: Asset[] }

const SIZES = [
  { key: "1:1", label: "Square 1:1", w: 1024, h: 1024 }, { key: "amazon", label: "Listing 2000²", w: 2000, h: 2000 },
  { key: "4:5", label: "Portrait 4:5", w: 1080, h: 1350 }, { key: "9:16", label: "Story 9:16", w: 1080, h: 1920 },
  { key: "16:9", label: "Landscape 16:9", w: 1920, h: 1080 }, { key: "sb", label: "Sponsored Brand", w: 1200, h: 628 },
];
const MODE_NOTE: Record<string, string> = {
  cutout_white: "Uses your real photo with the background removed locally (rembg). Product pixels are untouched.",
  composite: "Generates a background with AI, then places your untouched product photo on it.",
  template: "Builds a layered design with real text in your brand fonts — fully editable afterwards.",
};

function Studio() {
  const sp = useSearchParams();
  const opts = useApi<Options>(["creative-options"], "/creative/options");
  const caps = useCapabilities();
  const providers = useProviders();
  const { brand } = useActiveBrand();
  const [productId, setProductId] = React.useState(sp.get("product") ?? "");
  const [brandId, setBrandId] = React.useState("");
  const [type, setType] = React.useState(sp.get("type") ?? "lifestyle");
  const [size, setSize] = React.useState("1:1");
  const [style, setStyle] = React.useState("minimal");
  const [extra, setExtra] = React.useState("");
  const [override, setOverride] = React.useState(false);
  const [prompt, setPrompt] = React.useState("");
  const [provider, setProvider] = React.useState("");
  const [count, setCount] = React.useState(1);
  const [seed, setSeed] = React.useState("");
  const [harmonize, setHarmonize] = React.useState(false);
  const [sessionId, setSessionId] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { if (brand && !brandId) setBrandId(brand.id); }, [brand, brandId]);

  const product = useApi<Product>(["product", productId], productId ? `/products/${productId}` : null);
  const session = useApi<Session>(["session", sessionId], sessionId ? `/creative/sessions/${sessionId}` : null, { refetchInterval: 2000 });
  const history = useApi<{ items: Asset[] }>(["assets", "generated-history"], "/assets?source=generated&kind=image&limit=24");
  const mode = opts.data?.modes[type];
  const sz = SIZES.find((s) => s.key === size)!;
  const imageProviders = providers.data?.filter((p) => p.kinds.includes("image") && p.state === "available") ?? [];
  const noPhoto = productId && product.data && product.data.images.filter((i) => i.role !== "cutout").length === 0;
  const allDone = session.data && session.data.jobs.every((j) => ["succeeded", "failed", "cancelled"].includes(j.status));

  const generate = async () => {
    if (mode === "cutout_white" && !productId) return toast.error("Choose a product with a photo for a white-background image.");
    setBusy(true);
    try {
      const r = await post<{ session_id: string }>("/creative/generate", {
        creative_type: type, product_id: productId || null, brand_id: brandId || null, width: sz.w, height: sz.h, style,
        extra_prompt: override ? "" : extra, prompt: override && prompt.trim() ? prompt : null, provider: provider || null,
        count, seed: seed ? Number(seed) : null, harmonize,
      });
      setSessionId(r.session_id);
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title="Image studio" description="Main images, lifestyle scenes, infographics and ads. Every result shows exactly which model made it." />
      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <Card className="flex flex-col gap-4 p-5 lg:sticky lg:top-0 lg:max-h-[calc(100vh-120px)] lg:self-start lg:overflow-y-auto scrollbar-thin">
          <Field label="Product" aside={<QuickAddProduct onCreated={setProductId} />}><ProductSelect value={productId} onChange={setProductId} allowNone /></Field>
          {noPhoto && <Notice tone="warning">This product has no photo. AI will imagine the product — it won&apos;t match your real item. <Link className="underline" href={`/products/${productId}?tab=images`}>Add a photo</Link></Notice>}
          <Field label="Creative type">
            <Select value={type} onChange={(e) => setType(e.target.value)}>
              {opts.data && Object.entries(opts.data.creative_types).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          </Field>
          {mode && <p className="-mt-2 text-xs text-muted">{MODE_NOTE[mode]}</p>}
          <Field label="Size">
            <div className="grid grid-cols-3 gap-1.5">
              {SIZES.map((s) => (
                <button key={s.key} onClick={() => setSize(s.key)} className={cn("rounded-[9px] border px-2 py-1.5 text-[11.5px] font-medium", size === s.key ? "border-primary bg-primary-soft text-primary" : "border-border hover:bg-sunken")}>
                  {s.label}<div className="font-mono text-[10px] font-normal text-muted">{s.w}×{s.h}</div>
                </button>
              ))}
            </div>
          </Field>
          {mode === "template" && <p className="-mt-2 text-xs text-muted">Templates use their native size; resize the canvas in the editor if needed.</p>}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Style"><Select value={style} onChange={(e) => setStyle(e.target.value)}>{opts.data?.styles.map((s) => <option key={s} value={s} className="capitalize">{s}</option>)}</Select></Field>
            <Field label="Brand"><BrandSelect value={brandId} onChange={setBrandId} /></Field>
          </div>
          {mode !== "cutout_white" && (<>
            <Field label="Creative direction" aside={<label className="flex items-center gap-1.5">Full prompt<Switch checked={override} onChange={setOverride} label="Write the full prompt" /></label>}>
              {override ? <Textarea rows={4} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Full image prompt (background only when a product photo is used)" />
                : <Textarea rows={2} value={extra} onChange={(e) => setExtra(e.target.value)} placeholder="e.g. on a sunlit picnic table, autumn leaves" />}
            </Field>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Image AI" className="col-span-2"><Select value={provider} onChange={(e) => setProvider(e.target.value)}><option value="">Automatic</option>{imageProviders.map((p) => <option key={p.name} value={p.name}>{p.label}</option>)}</Select></Field>
              <Field label="Count"><Select value={count} onChange={(e) => setCount(Number(e.target.value))}>{[1, 2, 3, 4].map((n) => <option key={n}>{n}</option>)}</Select></Field>
            </div>
            <div className="flex items-end gap-2">
              <Field label="Seed" className="flex-1" hint="Same seed + prompt ≈ same image"><Input value={seed} onChange={(e) => setSeed(e.target.value.replace(/\D/g, ""))} placeholder="Random" /></Field>
              <Button variant="ghost" size="icon" className="mb-5" aria-label="Random seed" onClick={() => setSeed(String(Math.floor(Math.random() * 2 ** 31)))}><Shuffle /></Button>
            </div>
            {mode === "composite" && (
              <label className="flex items-start gap-3 rounded-[10px] border border-border p-3 text-[12.5px]">
                <Switch checked={harmonize} onChange={setHarmonize} label="Harmonize lighting" />
                <span><span className="font-medium">Harmonize lighting</span><span className="block text-muted">Blends product and scene with a light AI pass. May slightly change product details — off by default.</span></span>
              </label>
            )}
          </>)}
          {caps.data && !caps.data.image_ai && mode !== "cutout_white" && (
            <Notice tone="warning" icon={<Cpu />}>No image AI is enabled. You&apos;ll get a plain gradient backdrop (clearly labeled). Enable <b>Local diffusion</b> or Cloudflare in <Link href="/settings" className="underline">Settings</Link>.</Notice>
          )}
          <Button variant="ai" size="lg" onClick={generate} loading={busy}><Sparkles />Generate</Button>
        </Card>

        <div className="flex flex-col gap-6">
          {session.data && (
            <section>
              <h2 className="mb-3 text-[15px] font-semibold">This run</h2>
              {!allDone && <div className="mb-4 flex flex-col gap-2">{session.data.jobs.filter((j) => j.status !== "succeeded").map((j) => <JobCard key={j.id} jobId={j.id} compact onDone={() => { session.refetch(); history.refetch(); }} />)}</div>}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {session.data.assets.map((a) => <AssetResult key={a.id} asset={a} />)}
                {!allDone && Array.from({ length: Math.max(0, session.data.jobs.filter((j) => j.status !== "succeeded" && j.status !== "failed").length) }).map((_, i) => <Skeleton key={i} className="aspect-[4/5]" />)}
              </div>
            </section>
          )}
          <section>
            <h2 className="mb-3 flex items-center gap-2 text-[15px] font-semibold">Generation history <Link href="/library?source=generated" className="text-[13px] font-medium text-primary hover:underline">View all</Link></h2>
            {history.isLoading ? <Skeleton className="h-64" /> : !history.data?.items.length ? (
              <EmptyState icon={<Images />} title="Nothing generated yet" body="Pick a product and creative type, then hit Generate." />
            ) : <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">{history.data.items.map((a) => <AssetResult key={a.id} asset={a} />)}</div>}
          </section>
          <Notice icon={<Info />} className="text-xs">Text in infographics is rendered with real fonts as editable layers — image models are never asked to draw text, so spelling stays exact.</Notice>
        </div>
      </div>
    </>
  );
}

export default function Page() {
  return <React.Suspense><Studio /></React.Suspense>;
}
