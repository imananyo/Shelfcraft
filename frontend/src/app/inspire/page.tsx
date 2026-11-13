"use client";
import { ImagePlus, Info, LayoutTemplate, Palette, ScanSearch, Sparkles, Type } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";
import { QuickAddProduct } from "@/components/quick-add-product";
import { AssetPicker, AssetResult, BrandSelect, JobCard, ProductSelect } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Field, Input, Switch } from "@/components/ui/form";
import { Badge, Card, EmptyState, Notice, PageHeader, ProviderBadge } from "@/components/ui/misc";
import { get, post } from "@/lib/api";
import { useActiveBrand } from "@/lib/hooks";
import type { Asset, Job } from "@/lib/types";

interface Analysis {
  palette: { hex: string; share: number }[];
  layout: { size: number[]; grid: string; subject_placement: string; text_side?: string | null; whitespace_ratio: number; symmetry: number;
    text_blocks: { x: number; y: number; w: number; h: number; role: string }[]; focal_point: { x: number; y: number; bbox: number[] } };
  vision?: { composition?: string; mood?: string; typography?: string; design_principles?: string[]; provider?: string; model?: string } | null;
}

export default function InspirePage() {
  const { brand } = useActiveBrand();
  const [ref, setRef] = React.useState<Asset | null>(null);
  const [picker, setPicker] = React.useState(false);
  const [analysis, setAnalysis] = React.useState<Analysis | null>(null);
  const [analyzing, setAnalyzing] = React.useState(false);
  const [vision, setVision] = React.useState(true);
  const [productId, setProductId] = React.useState("");
  const [brandId, setBrandId] = React.useState("");
  const [headline, setHeadline] = React.useState("");
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<Asset | null>(null);
  React.useEffect(() => { if (brand && !brandId) setBrandId(brand.id); }, [brand, brandId]);

  const analyze = async (a: Asset) => {
    setRef(a); setAnalysis(null); setResult(null); setAnalyzing(true);
    try { setAnalysis(await post<Analysis>("/inspire/analyze", { asset_id: a.id, use_vision: vision })); }
    catch (e) { toast.error((e as Error).message); } finally { setAnalyzing(false); }
  };
  const generate = async () => {
    if (!ref || !productId) return toast.error("Choose a product to feature.");
    try {
      const j = await post<Job>("/inspire/generate", { reference_asset_id: ref.id, product_id: productId, brand_id: brandId || null, copy: headline ? { headline } : null });
      setJobId(j.id); setResult(null);
    } catch (e) { toast.error((e as Error).message); }
  };

  return (
    <>
      <PageHeader title="Inspire" description="Learn from a reference creative's design principles — palette, composition, text hierarchy — and apply them to your own product and brand."
        actions={<Button variant="outline" onClick={() => setPicker(true)}><ImagePlus />{ref ? "Change reference" : "Upload reference"}</Button>} />
      <Notice icon={<Info />} className="mb-6">Shelfcraft reuses only <b>structure</b> (layout grid, hierarchy, mood, color relationships). It never copies the reference&apos;s pixels, text, logos or brand identity. Use references you have the right to study.</Notice>
      {!ref ? (
        <EmptyState icon={<ScanSearch />} title="Start with a reference" body="Upload an ad, listing image or social post whose design you like." action={<Button onClick={() => setPicker(true)}><ImagePlus />Upload reference</Button>} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
          <Card className="p-4">
            <div className="relative mx-auto w-fit">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={ref.url} alt="Reference" className="max-h-[56vh] rounded-[10px]" />
              {analysis && (
                <div className="pointer-events-none absolute inset-0">
                  {analysis.layout.text_blocks.map((b, i) => (
                    <div key={i} className="absolute border-2 border-ai/80 bg-ai/10" style={{ left: `${b.x * 100}%`, top: `${b.y * 100}%`, width: `${b.w * 100}%`, height: `${b.h * 100}%` }}>
                      <span className="absolute -top-4 left-0 rounded bg-ai px-1 text-[9px] text-white">{b.role}</span>
                    </div>
                  ))}
                  <div className="absolute size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-danger" style={{ left: `${analysis.layout.focal_point.x * 100}%`, top: `${analysis.layout.focal_point.y * 100}%` }} title="Focal point" />
                </div>
              )}
            </div>
            <label className="mt-3 flex items-center gap-2 text-[12.5px] text-muted"><Switch checked={vision} onChange={setVision} label="Use vision AI" />Also describe the design with a vision-capable AI (if one is available)</label>
            <Button className="mt-3" variant="outline" size="sm" loading={analyzing} onClick={() => analyze(ref)}>Re-analyze</Button>
          </Card>
          <div className="flex flex-col gap-4">
            {analyzing && <Card className="p-5 text-[13px] text-muted">Analyzing layout, palette and text hierarchy…</Card>}
            {analysis && (<>
              <Card className="p-5">
                <div className="mb-2 flex items-center gap-2 text-[14px] font-semibold"><Palette className="size-4 text-primary" />Palette</div>
                <div className="flex h-12 overflow-hidden rounded-[10px]">{analysis.palette.map((c) => <div key={c.hex} style={{ background: c.hex, flex: c.share }} title={`${c.hex} · ${Math.round(c.share * 100)}%`} />)}</div>
                <div className="mt-2 flex flex-wrap gap-1.5">{analysis.palette.map((c) => <Badge key={c.hex} className="font-mono">{c.hex} {Math.round(c.share * 100)}%</Badge>)}</div>
              </Card>
              <Card className="grid grid-cols-2 gap-3 p-5 text-[13px]">
                <div className="col-span-2 flex items-center gap-2 text-[14px] font-semibold"><LayoutTemplate className="size-4 text-primary" />Composition</div>
                <div><div className="text-xs text-muted">Grid</div><div className="font-medium capitalize">{analysis.layout.grid}</div></div>
                <div><div className="text-xs text-muted">Subject</div><div className="font-medium capitalize">{analysis.layout.subject_placement}</div></div>
                <div><div className="text-xs text-muted">Text side</div><div className="font-medium capitalize">{analysis.layout.text_side ?? "—"}</div></div>
                <div><div className="text-xs text-muted">Whitespace</div><div className="font-medium">{Math.round(analysis.layout.whitespace_ratio * 100)}%</div></div>
                <div className="col-span-2 flex items-center gap-2"><Type className="size-4 text-muted" />{analysis.layout.text_blocks.length} text regions detected (heuristic)</div>
              </Card>
              {analysis.vision && (
                <Card className="p-5 text-[13px]">
                  <div className="mb-2 flex items-center justify-between"><span className="text-[14px] font-semibold">Design notes</span><ProviderBadge provider={analysis.vision.provider} model={analysis.vision.model} ai /></div>
                  {analysis.vision.composition && <p><b>Composition:</b> {analysis.vision.composition}</p>}
                  {analysis.vision.mood && <p><b>Mood:</b> {analysis.vision.mood}</p>}
                  {analysis.vision.typography && <p><b>Typography:</b> {analysis.vision.typography}</p>}
                  {!!analysis.vision.design_principles?.length && <ul className="mt-1 list-disc pl-4">{analysis.vision.design_principles.map((d) => <li key={d}>{d}</li>)}</ul>}
                </Card>
              )}
              <Card className="flex flex-col gap-3 p-5">
                <div className="text-[14px] font-semibold">Create with your product</div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Product *" aside={<QuickAddProduct label="New" onCreated={setProductId} />}><ProductSelect value={productId} onChange={setProductId} /></Field>
                  <Field label="Brand"><BrandSelect value={brandId} onChange={setBrandId} /></Field>
                </div>
                <Field label="Headline" hint="Defaults to your product name"><Input value={headline} onChange={(e) => setHeadline(e.target.value)} /></Field>
                <Button variant="ai" onClick={generate} disabled={!!jobId}><Sparkles />Generate inspired creative</Button>
                {jobId && <JobCard jobId={jobId} onDone={async (j) => { setJobId(null); const ids = (j.result?.asset_ids as string[]) ?? []; if (ids[0]) setResult(await get<Asset>(`/assets/${ids[0]}`)); }} />}
              </Card>
              {result && <div className="max-w-sm"><AssetResult asset={result} /></div>}
            </>)}
          </div>
        </div>
      )}
      <AssetPicker open={picker} onOpenChange={setPicker} onPick={analyze} title="Choose a reference creative" />
      <p className="mt-8 text-xs text-muted">Results are editable layered designs — find them under <Link href="/projects" className="underline">Designs</Link>.</p>
    </>
  );
}
