"use client";
import { Check, Cpu, Download, ImagePlus, PenLine, Sparkles, WandSparkles } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { BeforeAfter, MaskPainter, type MaskPainterHandle } from "@/components/mask-painter";
import { AssetPicker, JobCard } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Slider } from "@/components/ui/form";
import { Badge, Card, EmptyState, Notice, PageHeader, ProviderBadge } from "@/components/ui/misc";
import { download, post } from "@/lib/api";
import { useApi, useCapabilities } from "@/lib/hooks";
import type { Asset, Job } from "@/lib/types";
import { cn } from "@/lib/utils";

const OPS = [
  { key: "remove_object", label: "Remove object", ai: true, mask: true, desc: "Paint over something to erase it (LaMa, local)." },
  { key: "generative_fill", label: "Replace object", ai: true, mask: true, desc: "Paint an area and describe what should appear (experimental)." },
  { key: "remove_background", label: "Remove background", ai: true, mask: false, desc: "Transparent cut-out (rembg U²-Net, local)." },
  { key: "replace_background", label: "Replace background", ai: true, mask: false, desc: "New color, your image, or an AI scene." },
  { key: "extend", label: "Extend image", ai: true, mask: false, desc: "Grow the canvas; LaMa fills the new area." },
  { key: "enhance", label: "Enhance", ai: false, mask: false, desc: "Auto-contrast, color and sharpening." },
  { key: "upscale", label: "Upscale 2×", ai: false, mask: false, desc: "High-quality Lanczos resize." },
  { key: "recolor", label: "Recolor", ai: false, mask: false, desc: "Shift hue toward a color (optional mask)." },
] as const;

function SpotEdit() {
  const sp = useSearchParams();
  const router = useRouter();
  const caps = useCapabilities();
  const [assetId, setAssetId] = React.useState(sp.get("asset") ?? "");
  const [picker, setPicker] = React.useState(false);
  const [op, setOp] = React.useState<(typeof OPS)[number]["key"]>("remove_object");
  const [prompt, setPrompt] = React.useState("");
  const [bgMode, setBgMode] = React.useState<"color" | "prompt" | "asset">("color");
  const [color, setColor] = React.useState("#ffffff");
  const [bgAsset, setBgAsset] = React.useState<Asset | null>(null);
  const [bgPicker, setBgPicker] = React.useState(false);
  const [ext, setExt] = React.useState({ w: 0, h: 0 });
  const [strength, setStrength] = React.useState(0.85);
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<{ asset_id: string; provider: string; model: string; ai: boolean; note?: string } | null>(null);
  const painter = React.useRef<MaskPainterHandle>(null);
  const asset = useApi<Asset>(["asset", assetId], assetId ? `/assets/${assetId}` : null);
  const spec = OPS.find((o) => o.key === op)!;
  const usesMask = spec.mask || op === "recolor";

  React.useEffect(() => { if (asset.data?.width) setExt({ w: Math.round(asset.data.width * 1.5), h: asset.data.height ?? 0 }); }, [asset.data]);

  const run = async () => {
    if (!assetId) return;
    const mask = painter.current?.toDataURL() ?? null;
    if (spec.mask && !mask) return toast.error("Paint over the area to edit first.");
    if (op === "generative_fill" && !prompt.trim()) return toast.error("Describe what should appear in the painted area.");
    if (op === "replace_background" && bgMode === "asset" && !bgAsset) return toast.error("Choose a background image.");
    setResult(null);
    try {
      const j = await post<Job>("/edits", {
        asset_id: assetId, operation: op, mask: usesMask ? mask : null, prompt: prompt || null,
        background_mode: op === "replace_background" ? bgMode : null, color: op === "replace_background" || op === "recolor" ? color : null,
        background_asset_id: bgAsset?.id ?? null, width: op === "extend" ? ext.w : null, height: op === "extend" ? ext.h : null,
        strength: op === "recolor" || op === "generative_fill" ? strength : null,
      });
      setJobId(j.id);
    } catch (e) { toast.error((e as Error).message); }
  };

  return (
    <>
      <PageHeader title="Spot edit" description="Fix one detail without regenerating everything. Each tool says whether it uses AI — simple filters are never labeled as AI."
        actions={<Button variant="outline" onClick={() => setPicker(true)}><ImagePlus />{assetId ? "Change image" : "Choose image"}</Button>} />
      {!assetId ? (
        <EmptyState icon={<WandSparkles />} title="Choose an image to edit" body="Pick from your library or upload a new image." action={<Button onClick={() => setPicker(true)}><ImagePlus />Choose image</Button>} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
          <Card className="flex flex-col gap-4 p-5 lg:sticky lg:top-0 lg:self-start">
            <div className="grid grid-cols-2 gap-1.5">
              {OPS.map((o) => (
                <button key={o.key} onClick={() => { setOp(o.key); setResult(null); }}
                  className={cn("flex flex-col items-start rounded-[10px] border px-2.5 py-2 text-left text-[12.5px] font-medium", op === o.key ? "border-primary bg-primary-soft" : "border-border hover:bg-sunken")}>
                  {o.label}<Badge tone={o.ai ? "ai" : "neutral"} className="mt-1">{o.ai ? <><Sparkles />AI</> : "Non-AI"}</Badge>
                </button>
              ))}
            </div>
            <p className="text-[12.5px] text-muted">{spec.desc}</p>
            {op === "generative_fill" && (<>
              <Field label="What should appear?"><Input value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="a small potted succulent" /></Field>
              <Field label={`Strength ${strength.toFixed(2)}`}><Slider min={0.4} max={1} step={0.05} value={strength} onChange={setStrength} /></Field>
              {caps.data && !caps.data.image_ai && <Notice tone="warning">Needs an image model — enable Local diffusion in <Link className="underline" href="/settings">Settings</Link>.</Notice>}
            </>)}
            {op === "replace_background" && (<>
              <Field label="New background"><Select value={bgMode} onChange={(e) => setBgMode(e.target.value as typeof bgMode)}><option value="color">Solid color</option><option value="asset">One of my images</option><option value="prompt">AI-generated scene</option></Select></Field>
              {bgMode === "color" && <Field label="Color"><input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="h-9 w-full rounded-[10px] border border-border-strong" /></Field>}
              {bgMode === "asset" && <Button variant="outline" onClick={() => setBgPicker(true)}>{bgAsset ? bgAsset.title : "Choose background image"}</Button>}
              {bgMode === "prompt" && <Field label="Describe the scene"><Input value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="marble kitchen counter, morning light" /></Field>}
            </>)}
            {op === "extend" && (
              <div className="grid grid-cols-2 gap-2">
                <Field label="New width"><Input type="number" value={ext.w} onChange={(e) => setExt({ ...ext, w: Number(e.target.value) })} /></Field>
                <Field label="New height"><Input type="number" value={ext.h} onChange={(e) => setExt({ ...ext, h: Number(e.target.value) })} /></Field>
                <p className="col-span-2 text-xs text-muted">Current: {asset.data?.width}×{asset.data?.height}. Best on plain or repetitive backgrounds.</p>
              </div>
            )}
            {op === "recolor" && (<>
              <Field label="Target color"><input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="h-9 w-full rounded-[10px] border border-border-strong" /></Field>
              <Field label={`Strength ${strength.toFixed(2)}`}><Slider min={0.2} max={1} step={0.05} value={strength} onChange={setStrength} /></Field>
              <p className="text-xs text-muted">Optional: paint the area to recolor; otherwise the whole image shifts.</p>
            </>)}
            {op === "remove_object" && !caps.data?.object_removal_ai && <Notice icon={<Cpu />} className="text-xs">First use downloads the LaMa model (~200 MB) — one time only.</Notice>}
            <Button variant={spec.ai ? "ai" : "primary"} size="lg" onClick={run} disabled={!!jobId}>{spec.ai && <Sparkles />}Apply {spec.label.toLowerCase()}</Button>
            {jobId && <JobCard jobId={jobId} compact onDone={(j) => { setJobId(null); setResult(j.result as typeof result); }} />}
          </Card>
          <div className="flex flex-col gap-4">
            {result && asset.data ? (<>
              <BeforeAfter before={asset.data.url} after={`/api/assets/${result.asset_id}/file`} />
              <Card className="flex flex-wrap items-center gap-3 p-4">
                <ProviderBadge provider={result.provider} model={result.model} ai={result.ai} />
                {result.note && <span className="text-xs text-muted">{result.note}</span>}
                <div className="ml-auto flex gap-2">
                  <Button variant="outline" onClick={() => download(`/assets/${result.asset_id}/file?download=true`)}><Download />Download</Button>
                  <Button variant="outline" onClick={() => setResult(null)}>Discard</Button>
                  <Button onClick={() => { router.replace(`/edit?asset=${result.asset_id}`); setAssetId(result.asset_id); setResult(null); toast.success("Saved to library — keep editing"); }}><Check />Keep & continue</Button>
                </div>
              </Card>
            </>) : asset.data ? (
              <MaskPainter key={asset.data.id} ref={painter} src={asset.data.url} enabled={usesMask} />
            ) : null}
            {asset.data && (
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                <span>{asset.data.title} · {asset.data.width}×{asset.data.height}</span>
                {typeof asset.data.meta?.document_id === "string" && <Link href={`/editor/${asset.data.meta.document_id}`} className="inline-flex items-center gap-1 text-primary hover:underline"><PenLine className="size-3" />Open layered design</Link>}
              </div>
            )}
          </div>
        </div>
      )}
      <AssetPicker open={picker} onOpenChange={setPicker} onPick={(a) => { setAssetId(a.id); setResult(null); router.replace(`/edit?asset=${a.id}`); }} />
      <AssetPicker open={bgPicker} onOpenChange={setBgPicker} onPick={setBgAsset} title="Choose a background image" />
    </>
  );
}

export default function Page() {
  return <React.Suspense><SpotEdit /></React.Suspense>;
}
