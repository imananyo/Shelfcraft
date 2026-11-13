"use client";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Check, Play, Plus, Save, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { BrandSelect, ImageThumb } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Switch, Textarea } from "@/components/ui/form";
import { Badge, Card, ErrorState, Notice, PageHeader, Skeleton } from "@/components/ui/misc";
import { Confirm } from "@/components/ui/overlay";
import { del, post, put } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Product } from "@/lib/types";
import { cn } from "@/lib/utils";

type Step = { kind: string; creative_type?: string; style?: string; extra_prompt?: string; marketplace?: string; aspect?: string; duration?: number; voiceover?: boolean; tier?: string };
interface PB { id: string; name: string; description?: string; category: string; steps: Step[]; settings: Record<string, unknown>; is_template: boolean }

const KINDS: [string, string][] = [["creative", "Image / creative"], ["listing_copy", "Listing copy"], ["research", "Product research"], ["aplus", "A+ content"], ["video", "Video"], ["packaging", "Packaging ideas"]];
const STYLES = ["", "minimal", "natural", "luxury", "vibrant", "editorial", "tech"];

export default function PlaybookPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const q = useApi<PB>(["playbook", id], `/playbooks/${id}`);
  const opts = useApi<{ creative_types: Record<string, string> }>(["creative-options"], "/creative/options");
  const products = useApi<{ items: Product[] }>(["products", "pb"], "/products?limit=500&sort=name");
  const [pb, setPb] = React.useState<PB | null>(null);
  const [sel, setSel] = React.useState<string[]>([]);
  const [brandId, setBrandId] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [confirm, setConfirm] = React.useState(false);
  React.useEffect(() => { if (q.data) setPb(q.data); }, [q.data]);
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!pb) return <Skeleton className="h-96" />;
  const setStep = (i: number, s: Partial<Step>) => setPb({ ...pb, steps: pb.steps.map((x, j) => (j === i ? { ...x, ...s } : x)) });
  const move = (i: number, d: number) => { const n = [...pb.steps]; const [x] = n.splice(i, 1); n.splice(i + d, 0, x); setPb({ ...pb, steps: n }); };
  const save = async () => {
    setSaving(true);
    try { await put(`/playbooks/${id}`, { name: pb.name, description: pb.description, category: pb.category, steps: pb.steps, settings: pb.settings }); qc.invalidateQueries({ queryKey: ["playbooks"] }); toast.success("Playbook saved"); return true; }
    catch (e) { toast.error((e as Error).message); return false; } finally { setSaving(false); }
  };
  const run = async () => {
    if (!(await save())) return;
    try { const r = await post<{ batch_id: string; total: number }>(`/playbooks/${id}/run`, { product_ids: sel, brand_id: brandId || null }); toast.success(`Queued ${r.total} steps`); router.push(`/factory?run=${r.batch_id}`); }
    catch (e) { toast.error((e as Error).message); }
  };
  return (
    <>
      <PageHeader eyebrow={<Link href="/playbooks" className="hover:text-foreground">Playbooks</Link>} title={pb.name}
        actions={<><Button variant="outline" onClick={save} loading={saving}><Save />Save</Button><Button variant="ghost" size="icon" aria-label="Delete playbook" onClick={() => setConfirm(true)}><Trash2 /></Button></>} />
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="flex flex-col gap-4">
          <Card className="grid gap-3 p-5 sm:grid-cols-[1fr_180px]">
            <Field label="Name"><Input value={pb.name} onChange={(e) => setPb({ ...pb, name: e.target.value })} /></Field>
            <Field label="Category"><Select value={pb.category} onChange={(e) => setPb({ ...pb, category: e.target.value })}>{["custom", "listing", "lifestyle", "social", "launch"].map((c) => <option key={c}>{c}</option>)}</Select></Field>
            <Field label="Description" className="sm:col-span-2"><Textarea rows={2} value={pb.description ?? ""} onChange={(e) => setPb({ ...pb, description: e.target.value })} /></Field>
          </Card>
          <Card className="p-5">
            <div className="mb-3 flex items-center justify-between"><h3 className="text-[14px] font-semibold">Steps ({pb.steps.length})</h3>
              <Button size="sm" variant="outline" disabled={pb.steps.length >= 20} onClick={() => setPb({ ...pb, steps: [...pb.steps, { kind: "creative", creative_type: "lifestyle" }] })}><Plus />Add step</Button></div>
            <div className="flex flex-col gap-2">
              {pb.steps.map((s, i) => (
                <div key={i} className="flex flex-wrap items-end gap-2 rounded-[12px] border border-border p-3">
                  <span className="mb-2 w-6 font-mono text-xs text-muted">{i + 1}</span>
                  <Field label="Step" className="w-44"><Select value={s.kind} onChange={(e) => setStep(i, { kind: e.target.value })}>{KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
                  {s.kind === "creative" && (<>
                    <Field label="Type" className="w-52"><Select value={s.creative_type} onChange={(e) => setStep(i, { creative_type: e.target.value })}>{opts.data && Object.entries(opts.data.creative_types).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
                    <Field label="Style" className="w-32"><Select value={s.style ?? ""} onChange={(e) => setStep(i, { style: e.target.value || undefined })}>{STYLES.map((x) => <option key={x} value={x}>{x || "default"}</option>)}</Select></Field>
                    <Field label="Direction" className="min-w-40 flex-1"><Input value={s.extra_prompt ?? ""} onChange={(e) => setStep(i, { extra_prompt: e.target.value })} placeholder="optional" /></Field>
                  </>)}
                  {s.kind === "listing_copy" && <Field label="Marketplace" className="w-40"><Select value={s.marketplace ?? "amazon"} onChange={(e) => setStep(i, { marketplace: e.target.value })}>{["amazon", "amazon_mobile", "shopify", "walmart", "tiktok"].map((m) => <option key={m}>{m}</option>)}</Select></Field>}
                  {s.kind === "aplus" && <Field label="Tier" className="w-36"><Select value={s.tier ?? "premium"} onChange={(e) => setStep(i, { tier: e.target.value })}>{["premium", "basic", "mobile"].map((m) => <option key={m}>{m}</option>)}</Select></Field>}
                  {s.kind === "video" && (<>
                    <Field label="Aspect" className="w-28"><Select value={s.aspect ?? "16:9"} onChange={(e) => setStep(i, { aspect: e.target.value })}>{["16:9", "9:16", "1:1", "4:5"].map((m) => <option key={m}>{m}</option>)}</Select></Field>
                    <label className="mb-2 flex items-center gap-2 text-[12.5px]"><Switch checked={!!s.voiceover} onChange={(v) => setStep(i, { voiceover: v })} label="Voiceover" />Voiceover</label>
                  </>)}
                  <div className="mb-1 ml-auto flex gap-1">
                    <Button size="icon-sm" variant="ghost" aria-label="Move up" disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp /></Button>
                    <Button size="icon-sm" variant="ghost" aria-label="Move down" disabled={i === pb.steps.length - 1} onClick={() => move(i, 1)}><ArrowDown /></Button>
                    <Button size="icon-sm" variant="ghost" aria-label="Remove step" disabled={pb.steps.length === 1} onClick={() => setPb({ ...pb, steps: pb.steps.filter((_, j) => j !== i) })}><X /></Button>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
        <Card className="flex flex-col gap-3 p-5 lg:sticky lg:top-0 lg:self-start">
          <h3 className="text-[14px] font-semibold">Run on products</h3>
          <div className="flex max-h-72 flex-col gap-1 overflow-y-auto">
            {products.data?.items.map((p) => {
              const on = sel.includes(p.id);
              return (
                <button key={p.id} onClick={() => setSel((s) => (on ? s.filter((x) => x !== p.id) : [...s, p.id]))}
                  className={cn("flex items-center gap-2 rounded-[9px] border px-2 py-1.5 text-left text-[13px]", on ? "border-primary bg-primary-soft" : "border-border hover:bg-sunken")}>
                  <span className={cn("flex size-4 items-center justify-center rounded border", on ? "border-primary bg-primary text-white" : "border-border-strong")}>{on && <Check className="size-3" />}</span>
                  <ImageThumb src={p.cover_url} alt="" className="size-7" /><span className="truncate">{p.name}</span>
                </button>
              );
            })}
          </div>
          <Field label="Brand"><BrandSelect value={brandId} onChange={setBrandId} /></Field>
          <div className="text-[13px]"><Badge>{pb.steps.length * sel.length} jobs</Badge></div>
          <Button size="lg" variant="ai" disabled={!sel.length} onClick={run}><Play />Run playbook</Button>
          <Notice className="text-xs">Steps run in the background, one heavy job at a time. Follow progress in Scale → My runs.</Notice>
        </Card>
      </div>
      <Confirm open={confirm} onOpenChange={setConfirm} title="Delete this playbook?" onConfirm={async () => { await del(`/playbooks/${id}`); qc.invalidateQueries({ queryKey: ["playbooks"] }); router.push("/playbooks"); }} />
    </>
  );
}
