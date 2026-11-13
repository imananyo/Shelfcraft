"use client";
import { Copy, Factory, Languages, Palette, Play, ScanSearch, SquareStack } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";
import { JobStatusBadge } from "@/components/shell/app-shell";
import { ImageThumb } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/form";
import { Badge, Card, EmptyState, OptionCard, PageHeader, Progress } from "@/components/ui/misc";
import { Dialog } from "@/components/ui/overlay";
import { post } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { DocSummary, Product } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";

interface Run { id: string; name: string; total: number; counts: Record<string, number>; created_at: string; kind: string }

export default function ScalePage() {
  const runs = useApi<Run[]>(["scale-runs"], "/scale/runs", { refetchInterval: 4000 });
  const [tool, setTool] = React.useState<null | "translate" | "apply">(null);
  return (
    <>
      <PageHeader title="Scale" description="Turn one finished listing into many — variants, new markets, more products, or a look you love." />
      <h2 className="mb-3 text-[15px] font-semibold">Tools</h2>
      <div className="mb-8 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <OptionCard icon={<Palette />} title="Variant" description="Swap color, size or flavor across your images" href="/factory?variants=1" />
        <OptionCard icon={<Languages />} title="Translate" description="Adapt a listing — copy and image text — for a new market" onClick={() => setTool("translate")} />
        <OptionCard icon={<Copy />} title="Different product" description="Apply a finished design to other products" onClick={() => setTool("apply")} />
        <OptionCard icon={<ScanSearch />} title="Steal the look" description="Take inspiration from visuals you love" href="/inspire" />
      </div>
      <div className="mb-3 flex items-center justify-between"><h2 className="text-[15px] font-semibold">My runs <span className="font-normal text-muted">({runs.data?.length ?? 0})</span></h2>
        <Link href="/factory"><Button size="sm" variant="outline"><Factory />Start a bulk run</Button></Link></div>
      {!runs.data?.length ? <EmptyState icon={<SquareStack />} title="No runs yet" body="Bulk runs from Factory, Playbooks and bulk listing copy appear here." action={<Link href="/factory"><Button><Play />Start a run</Button></Link>} /> : (
        <Card className="divide-y divide-border">
          {runs.data.map((r) => {
            const done = (r.counts.succeeded ?? 0) + (r.counts.failed ?? 0) + (r.counts.cancelled ?? 0);
            return (
              <Link key={r.id} href={`/factory?run=${r.id}`} className="flex items-center gap-4 px-5 py-3 hover:bg-sunken/60">
                <div className="min-w-0 flex-1"><div className="truncate text-[13.5px] font-medium">{r.name}</div><div className="text-xs text-muted">{timeAgo(r.created_at)}</div></div>
                <Badge className="capitalize">{r.kind.replace("_", " ")}</Badge>
                <div className="w-40"><Progress value={r.total ? done / r.total : 0} /><div className="mt-1 text-right text-[11px] text-muted">{done}/{r.total}{r.counts.failed ? ` · ${r.counts.failed} failed` : ""}</div></div>
                {r.counts.running ? <JobStatusBadge status="running" /> : null}
              </Link>
            );
          })}
        </Card>
      )}
      <TranslateDialog open={tool === "translate"} onOpenChange={(o) => !o && setTool(null)} />
      <ApplyDialog open={tool === "apply"} onOpenChange={(o) => !o && setTool(null)} />
    </>
  );
}

function TranslateDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const listings = useApi<{ id: string; name: string; has_copy: boolean }[]>(["listings"], open ? "/listings" : null);
  const langs = useApi<Record<string, string>>(["languages"], "/languages");
  const [lid, setLid] = React.useState("");
  const [lang, setLang] = React.useState("de");
  const [country, setCountry] = React.useState("DE");
  const go = async () => {
    try { await post(`/listings/${lid}/translate`, { language: lang, country }); toast.success("Translating — you'll be notified when it's ready"); onOpenChange(false); }
    catch (e) { toast.error((e as Error).message); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Translate a listing" description="Creates a new listing in the target language, including the text inside its images."
      footer={<><Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button><Button disabled={!lid} onClick={go}><Languages />Translate</Button></>}>
      <div className="flex flex-col gap-3">
        <Field label="Listing"><Select value={lid} onChange={(e) => setLid(e.target.value)}><option value="">Choose…</option>{listings.data?.filter((l) => l.has_copy).map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</Select></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Language"><Select value={lang} onChange={(e) => setLang(e.target.value)}>{langs.data && Object.entries(langs.data).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
          <Field label="Country"><Select value={country} onChange={(e) => setCountry(e.target.value)}>{["US", "UK", "DE", "FR", "ES", "IT", "NL", "PL", "SE", "TR", "AE", "IN", "JP", "MX", "CA", "AU"].map((c) => <option key={c}>{c}</option>)}</Select></Field>
        </div>
        <p className="text-xs text-muted">Brand and product names stay unchanged. Review translations before publishing — small local models can make mistakes.</p>
      </div>
    </Dialog>
  );
}

function ApplyDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const docs = useApi<DocSummary[]>(["documents"], open ? "/documents" : null);
  const products = useApi<{ items: Product[] }>(["products", "apply"], open ? "/products?limit=500&sort=name" : null);
  const [d, setD] = React.useState<string[]>([]);
  const [p, setP] = React.useState<string[]>([]);
  const [busy, setBusy] = React.useState(false);
  const toggle = (arr: string[], set: (v: string[]) => void, id: string) => set(arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id]);
  const go = async () => {
    setBusy(true);
    try { const r = await post<{ results: unknown[] }>("/scale/apply", { document_ids: d, product_ids: p }); toast.success(`Created ${r.results.length} designs — find them in Designs`); onOpenChange(false); }
    catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Apply designs to other products" wide description="Product photos, names, features and benefits are swapped in; layout, colors and styling stay the same."
      footer={<><Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button><Button loading={busy} disabled={!d.length || !p.length} onClick={go}><Copy />Create {d.length * p.length} designs</Button></>}>
      <div className="grid gap-5 md:grid-cols-2">
        <div><div className="mb-2 text-[13px] font-medium">1 · Designs ({d.length})</div>
          <div className="grid max-h-80 grid-cols-3 gap-2 overflow-y-auto">
            {docs.data?.map((x) => (
              <button key={x.id} onClick={() => toggle(d, setD, x.id)} className={cn("overflow-hidden rounded-[10px] border text-left", d.includes(x.id) ? "border-primary ring-3 ring-[var(--ring)]" : "border-border")}>
                <ImageThumb src={x.thumb_url} alt={x.name} className="aspect-square rounded-none border-0 [&_img]:object-contain" /><div className="truncate px-1.5 py-1 text-[11px]">{x.name}</div>
              </button>
            ))}
          </div></div>
        <div><div className="mb-2 text-[13px] font-medium">2 · Products ({p.length})</div>
          <div className="flex max-h-80 flex-col gap-1 overflow-y-auto">
            {products.data?.items.map((x) => (
              <button key={x.id} onClick={() => toggle(p, setP, x.id)} className={cn("flex items-center gap-2 rounded-[9px] border px-2 py-1.5 text-left text-[13px]", p.includes(x.id) ? "border-primary bg-primary-soft" : "border-border hover:bg-sunken")}>
                <ImageThumb src={x.cover_url} alt="" className="size-8" /><span className="truncate">{x.name}</span>
              </button>
            ))}
          </div></div>
      </div>
    </Dialog>
  );
}
