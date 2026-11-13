"use client";
import { CircleAlert, Download, ExternalLink, ImageIcon, PenLine, RefreshCw, Search, Sparkles, X } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dropzone } from "@/components/ui/dropzone";
import { Input, Select } from "@/components/ui/form";
import { Badge, Card, Progress, ProviderBadge, Skeleton } from "@/components/ui/misc";
import { Dialog, Tip } from "@/components/ui/overlay";
import { download, post, upload } from "@/lib/api";
import { useApi, useBrands, useJob } from "@/lib/hooks";
import type { Asset, Job, Product } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";

export function ProductSelect({ value, onChange, allowNone, className }: { value: string; onChange: (id: string) => void; allowNone?: boolean; className?: string }) {
  const q = useApi<{ items: Product[] }>(["products", "picker"], "/products?limit=500&sort=name");
  return (
    <Select value={value} onChange={(e) => onChange(e.target.value)} className={className} aria-label="Product">
      <option value="">{allowNone ? "No product" : q.isLoading ? "Loading products…" : "Choose a product…"}</option>
      {q.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}{p.image_count ? "" : " (no photo)"}</option>)}
    </Select>
  );
}

export function BrandSelect({ value, onChange, className }: { value: string; onChange: (id: string) => void; className?: string }) {
  const q = useBrands();
  return (
    <Select value={value} onChange={(e) => onChange(e.target.value)} className={className} aria-label="Brand">
      <option value="">No brand</option>
      {q.data?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
    </Select>
  );
}

/** Pick an existing image from the library or upload a new one. */
export function AssetPicker({ open, onOpenChange, onPick, kind = "image", title = "Choose an image", productId }: {
  open: boolean; onOpenChange: (o: boolean) => void; onPick: (a: Asset) => void; kind?: string; title?: string; productId?: string;
}) {
  const [q, setQ] = React.useState("");
  const [uploading, setUploading] = React.useState(false);
  const params = new URLSearchParams({ kind, limit: "120" });
  if (q) params.set("q", q);
  const list = useApi<{ items: Asset[] }>(["assets", "picker", kind, q], open ? `/assets?${params}` : null);
  const onFiles = async (files: File[]) => {
    setUploading(true);
    try {
      const res = await upload<Asset[]>("/assets", files, "files", productId ? { product_id: productId } : undefined);
      onPick(res[0]);
      onOpenChange(false);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setUploading(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={title} wide>
      <div className="flex flex-col gap-4">
        <Dropzone compact onFiles={onFiles} multiple={false} accept={kind === "audio" ? "audio/*" : "image/*"}
          label={uploading ? "Uploading…" : kind === "audio" ? "Upload an audio file (MP3, WAV, M4A, OGG)" : "Upload from your computer"} disabled={uploading} />
        <div className="relative">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search library…" className="pl-9" />
        </div>
        {list.isLoading ? <div className="grid grid-cols-4 gap-2">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="aspect-square" />)}</div>
          : !list.data?.items.length ? <div className="py-8 text-center text-[13px] text-muted">Nothing in the library yet — upload above.</div>
          : (
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
              {list.data.items.map((a) => (
                <button key={a.id} onClick={() => { onPick(a); onOpenChange(false); }} className="group overflow-hidden rounded-[10px] border border-border text-left hover:border-primary">
                  {a.kind === "image" ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={a.thumb_url} alt={a.title} className="checkerboard aspect-square w-full object-contain" loading="lazy" />
                  ) : <div className="flex aspect-square items-center justify-center bg-sunken text-xs text-muted">{a.kind}</div>}
                  <div className="truncate px-1.5 py-1 text-[11px]">{a.title}</div>
                </button>
              ))}
            </div>
          )}
      </div>
    </Dialog>
  );
}

/** Inline job status: queued → running (progress) → done/failed with retry. */
export function JobCard({ jobId, onDone, title, compact }: { jobId: string; onDone?: (j: Job) => void; title?: string; compact?: boolean }) {
  const [failedOnce, setFailedOnce] = React.useState(false);
  const q = useJob(jobId, { onDone, onFail: () => setFailedOnce(true) });
  const j = q.data;
  if (!j) return <Skeleton className="h-16" />;
  const retry = async () => { await post(`/jobs/${j.id}/retry`); setFailedOnce(false); q.refetch(); };
  const cancel = async () => { await post(`/jobs/${j.id}/cancel`); q.refetch(); };
  return (
    <div className={cn("rounded-[12px] border px-4 py-3", j.status === "failed" ? "border-danger/30 bg-danger-soft" : "border-border bg-surface", compact && "py-2.5")}>
      <div className="flex items-center gap-3">
        {j.status === "failed" ? <CircleAlert className="size-4 text-danger" /> : <Sparkles className={cn("size-4 text-ai", (j.status === "running" || j.status === "queued") && "animate-pulse")} />}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-[13px] font-medium">{title ?? j.label}
            <Badge tone={j.status === "succeeded" ? "success" : j.status === "failed" ? "danger" : j.status === "running" ? "ai" : "neutral"}>{j.status}</Badge>
          </div>
          <div className="truncate text-xs text-muted">
            {j.status === "failed" ? j.error : j.status === "queued" ? (j.message ?? "Waiting for a free worker…") : j.message ?? ""}
            {j.attempts > 1 && j.status !== "succeeded" ? ` · attempt ${j.attempts}/${j.max_attempts}` : ""}
          </div>
        </div>
        {(j.status === "queued" || j.status === "running") && <Button size="sm" variant="ghost" onClick={cancel}>Cancel</Button>}
        {(j.status === "failed" || j.status === "cancelled") && <Button size="sm" variant="outline" onClick={retry}><RefreshCw />Retry</Button>}
      </div>
      {(j.status === "running" || j.status === "queued") && <Progress value={j.status === "queued" ? 0.02 : j.progress} tone="ai" className="mt-2.5" />}
      {failedOnce && j.status === "failed" && j.error?.includes("No ") && (
        <div className="mt-2 text-xs">Tip: enable a free provider or start Ollama in <Link href="/settings" className="font-medium text-primary underline">Settings</Link>.</div>
      )}
    </div>
  );
}

/** Generated asset card with attribution, download and edit actions. */
export function AssetResult({ asset, onSelect, selected, actions = true }: { asset: Asset; onSelect?: () => void; selected?: boolean; actions?: boolean }) {
  const docId = asset.meta?.document_id as string | undefined;
  return (
    <Card className={cn("group overflow-hidden", selected && "ring-3 ring-[var(--ring)]")}>
      <button className="block w-full" onClick={onSelect} aria-label={`Preview ${asset.title}`}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={asset.thumb_url} alt={asset.title} className="checkerboard aspect-square w-full object-contain" loading="lazy" />
      </button>
      <div className="flex flex-col gap-2 p-3">
        <div className="truncate text-[13px] font-medium" title={asset.title}>{asset.title}</div>
        <ProviderBadge provider={asset.provider} model={asset.model} ai={asset.is_ai_generated} />
        {typeof asset.meta?.note === "string" && <p className="line-clamp-2 text-[11.5px] text-muted" title={asset.meta.note}>{asset.meta.note}</p>}
        {actions && (
          <div className="flex flex-wrap gap-1.5">
            <Tip content="Download PNG"><Button size="icon-sm" variant="outline" aria-label="Download" onClick={() => download(`/assets/${asset.id}/file?download=true`, {}, asset.filename)}><Download /></Button></Tip>
            {docId && <Link href={`/editor/${docId}`}><Button size="sm" variant="outline"><PenLine />Edit layers</Button></Link>}
            <Link href={`/edit?asset=${asset.id}`}><Button size="sm" variant="ghost">Spot edit</Button></Link>
            <a href={asset.url} target="_blank" rel="noreferrer"><Button size="icon-sm" variant="ghost" aria-label="Open full size"><ExternalLink /></Button></a>
          </div>
        )}
      </div>
    </Card>
  );
}

export function ImageThumb({ src, alt, className, onRemove }: { src?: string | null; alt: string; className?: string; onRemove?: () => void }) {
  return (
    <div className={cn("group relative overflow-hidden rounded-[10px] border border-border bg-sunken", className)}>
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt={alt} className="size-full object-cover" loading="lazy" />
      ) : <div className="flex size-full items-center justify-center text-muted"><ImageIcon className="size-5" /></div>}
      {onRemove && (
        <button onClick={onRemove} aria-label={`Remove ${alt}`} className="absolute right-1 top-1 hidden size-6 items-center justify-center rounded-full bg-black/60 text-white group-hover:flex">
          <X className="size-3.5" />
        </button>
      )}
    </div>
  );
}

export function Updated({ at }: { at?: string }) {
  return <span className="text-xs text-muted">Updated {timeAgo(at)}</span>;
}
