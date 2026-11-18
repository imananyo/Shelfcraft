"use client";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Check, Clock, Copy, CopyPlus, Download, Play, Plus, Save, Search, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { BrandSelect, ImageThumb } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Switch, Textarea } from "@/components/ui/form";
import { Badge, Card, ErrorState, Notice, PageHeader, Progress, Skeleton } from "@/components/ui/misc";
import { Confirm } from "@/components/ui/overlay";
import { del, post, put } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import {
  CATEGORIES, STEP_KINDS, defaultStep, estimateMinutes, formatMinutes, runSummary, stepLabel,
  type PlaybookOptions, type PlaybookRun, type PlaybookSettings, type PlaybookT, type Step,
} from "@/lib/playbooks";
import type { Product } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";

const num = (v: string) => (v === "" ? undefined : Number(v));
const snapshot = (p: PlaybookT) => JSON.stringify([p.name, p.description ?? "", p.category, p.steps, p.settings]);

function StepFields({ s, set, o, defaults }: { s: Step; set: (p: Partial<Step>) => void; o?: PlaybookOptions; defaults: PlaybookSettings }) {
  const inherit = (v?: string) => `Default${v ? ` (${v})` : ""}`;
  if (s.kind === "creative") return (<>
    <Field label="Type" className="w-52"><Select aria-label="Image type" value={s.creative_type ?? ""} onChange={(e) => set({ creative_type: e.target.value })}>
      {!o && <option value={s.creative_type}>{s.creative_type}</option>}
      {o && Object.entries(o.creative_types).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
    <Field label="Style" className="w-40"><Select aria-label="Style" value={s.style ?? ""} onChange={(e) => set({ style: e.target.value || undefined })}>
      <option value="">{inherit(defaults.style ?? "minimal")}</option>{o?.styles.map((x) => <option key={x}>{x}</option>)}</Select></Field>
    <Field label="Direction" className="min-w-40 flex-1"><Input aria-label="Direction" value={s.extra_prompt ?? ""} maxLength={500} onChange={(e) => set({ extra_prompt: e.target.value })} placeholder="optional, e.g. morning light on a kitchen counter" /></Field>
  </>);
  if (s.kind === "listing_copy") return (<>
    <Field label="Marketplace" className="w-44"><Select aria-label="Marketplace" value={s.marketplace ?? ""} onChange={(e) => set({ marketplace: e.target.value || undefined })}>
      <option value="">{inherit(o?.marketplaces[defaults.marketplace ?? "amazon"] ?? defaults.marketplace ?? "Amazon")}</option>
      {o && Object.entries(o.marketplaces).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
    <Field label="Language" className="w-40"><Select aria-label="Language" value={s.language ?? "en"} onChange={(e) => set({ language: e.target.value })}>
      {o ? Object.entries(o.languages).map(([k, l]) => <option key={k} value={k}>{l}</option>) : <option value="en">English</option>}</Select></Field>
    <Field label="Country" className="w-24"><Input aria-label="Country" value={s.country ?? ""} maxLength={2} placeholder="US" onChange={(e) => set({ country: e.target.value.toUpperCase() || undefined })} /></Field>
  </>);
  if (s.kind === "video") return (<>
    <Field label="Aspect" className="w-28"><Select aria-label="Aspect ratio" value={s.aspect ?? "16:9"} onChange={(e) => set({ aspect: e.target.value })}>{(o?.aspects ?? ["16:9", "9:16", "1:1", "4:5"]).map((m) => <option key={m}>{m}</option>)}</Select></Field>
    <Field label="Length (s)" className="w-24"><Input aria-label="Video length in seconds" type="number" min={5} max={60} value={s.duration ?? 15} onChange={(e) => set({ duration: num(e.target.value) })} /></Field>
    <label className="mb-2 flex items-center gap-2 text-[12.5px]"><Switch checked={!!s.voiceover} onChange={(v) => set({ voiceover: v })} label="Voiceover" />Voiceover</label>
  </>);
  if (s.kind === "aplus") {
    const mods = s.modules ?? o?.default_aplus_modules ?? [];
    const toggle = (m: string) => { const n = mods.includes(m) ? mods.filter((x) => x !== m) : [...mods, m]; if (n.length) set({ modules: n }); };
    return (<>
      <Field label="Tier" className="w-32"><Select aria-label="A+ tier" value={s.tier ?? "premium"} onChange={(e) => set({ tier: e.target.value })}>{["premium", "basic", "mobile"].map((m) => <option key={m}>{m}</option>)}</Select></Field>
      <div className="min-w-60 flex-1">
        <div className="mb-1.5 text-[12px] font-medium">Modules <span className="font-normal text-muted">(in this order)</span></div>
        <div className="flex flex-wrap gap-1">
          {o && Object.entries(o.aplus_modules).map(([k, l]) => {
            const on = mods.includes(k);
            return <button key={k} type="button" onClick={() => toggle(k)} aria-pressed={on} disabled={on && mods.length === 1 || !on && mods.length >= 7}
              className={cn("rounded-full border px-2.5 py-0.5 text-[12px] disabled:opacity-50", on ? "border-primary bg-primary-soft text-primary" : "border-border text-muted hover:bg-sunken")}>
              {on && <span className="mr-1 font-mono">{mods.indexOf(k) + 1}</span>}{l}</button>;
          })}
        </div>
      </div>
    </>);
  }
  if (s.kind === "packaging") return <Field label="Ideas" className="w-24"><Input aria-label="Number of ideas" type="number" min={1} max={20} value={s.count ?? 8} onChange={(e) => set({ count: num(e.target.value) })} /></Field>;
  return <p className="mb-2 text-[12.5px] text-muted">Researches the product (audience, keywords, angles). Later copy steps use it automatically.</p>;
}

export default function PlaybookPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const q = useApi<PlaybookT>(["playbook", id], `/playbooks/${id}`);
  const opts = useApi<PlaybookOptions>(["playbook-options"], "/playbooks/options");
  const products = useApi<{ items: Product[] }>(["products", "pb"], "/products?limit=500&sort=name");
  const runs = useApi<PlaybookRun[]>(["playbook-runs", id], `/playbooks/${id}/runs`,
    { refetchInterval: (d) => (d?.some((r) => runSummary(r).active > 0) ? 5000 : false) });
  const [pb, setPb] = React.useState<PlaybookT | null>(null);
  const [saved, setSaved] = React.useState("");
  const [sel, setSel] = React.useState<string[]>([]);
  const [find, setFind] = React.useState("");
  const [brandId, setBrandId] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [running, setRunning] = React.useState(false);
  const [confirm, setConfirm] = React.useState(false);

  if (q.data && !pb) { setPb(q.data); setSaved(snapshot(q.data)); } // first load (state adjusted during render, no effect)
  const dirty = !!pb && snapshot(pb) !== saved;
  React.useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const save = React.useCallback(async () => {
    if (!pb || pb.is_template) return false;
    setSaving(true);
    try {
      const out = await put<PlaybookT>(`/playbooks/${id}`, { name: pb.name, description: pb.description, category: pb.category, steps: pb.steps, settings: pb.settings });
      setPb(out); setSaved(snapshot(out));
      qc.setQueryData(["playbook", id], out);
      qc.invalidateQueries({ queryKey: ["playbooks"] });
      return true;
    } catch (e) { toast.error((e as Error).message); return false; } finally { setSaving(false); }
  }, [pb, id, qc]);
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); if (dirty) save().then((ok) => ok && toast.success("Playbook saved")); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dirty, save]);

  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!pb) return <Skeleton className="h-96" />;
  const o = opts.data;
  const ro = pb.is_template;
  const setStep = (i: number, s: Partial<Step>) => setPb({ ...pb, steps: pb.steps.map((x, j) => (j === i ? { ...x, ...s } : x)) });
  const setKind = (i: number, kind: string) => setPb({ ...pb, steps: pb.steps.map((x, j) => (j === i ? defaultStep(kind) : x)) });
  const setSettings = (s: Partial<PlaybookSettings>) => setPb({ ...pb, settings: { ...pb.settings, ...s } });
  const move = (i: number, d: number) => { const n = [...pb.steps]; const [x] = n.splice(i, 1); n.splice(i + d, 0, x); setPb({ ...pb, steps: n }); };
  const duplicateStep = (i: number) => { const n = [...pb.steps]; n.splice(i + 1, 0, { ...pb.steps[i] }); setPb({ ...pb, steps: n }); };
  const copyPlaybook = async (msg: string) => {
    try { const p = await post<PlaybookT>(`/playbooks/${id}/import`); qc.invalidateQueries({ queryKey: ["playbooks"] }); toast.success(msg); router.push(`/playbooks/${p.id}`); }
    catch (e) { toast.error((e as Error).message); }
  };
  const run = async () => {
    setRunning(true);
    try {
      if (dirty && !(await save())) return;
      const r = await post<{ batch_id: string; total: number }>(`/playbooks/${id}/run`, { product_ids: sel, brand_id: brandId || null });
      toast.success(`Queued ${r.total} job${r.total === 1 ? "" : "s"}`);
      qc.invalidateQueries({ queryKey: ["playbook-runs", id] });
      router.push(`/factory?run=${r.batch_id}`);
    } catch (e) { toast.error((e as Error).message); } finally { setRunning(false); }
  };

  const items = products.data?.items ?? [];
  const f = find.trim().toLowerCase();
  const visible = f ? items.filter((p) => [p.name, p.sku, p.category, p.brand_name].some((v) => v?.toLowerCase().includes(f))) : items;
  const jobs = pb.steps.length * sel.length;
  const overLimit = sel.length > 50;
  const est = estimateMinutes(pb.steps, sel.length || 1, o?.step_minutes);

  return (
    <>
      <PageHeader eyebrow={<Link href="/playbooks" className="hover:text-foreground">Playbooks</Link>}
        title={<span className="flex items-center gap-2">{pb.name || "Untitled playbook"}{dirty && <Badge tone="warning">Unsaved changes</Badge>}</span>}
        actions={ro ? <Button onClick={() => copyPlaybook("Imported — customize and run it")}><Download />Import to edit</Button> : <>
          <Button variant="outline" onClick={() => save().then((ok) => ok && toast.success("Playbook saved"))} loading={saving} disabled={!dirty}><Save />{dirty ? "Save" : "Saved"}</Button>
          <Button variant="ghost" size="icon" aria-label="Duplicate playbook" title="Duplicate" onClick={() => copyPlaybook("Duplicated")}><Copy /></Button>
          <Button variant="ghost" size="icon" aria-label="Delete playbook" title="Delete" onClick={() => setConfirm(true)}><Trash2 /></Button>
        </>} />
      {ro && <Notice tone="warning" className="mb-4">This is a built-in template. Import it to make your own copy you can edit and run.</Notice>}
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <fieldset disabled={ro} className="flex min-w-0 flex-col gap-4">
          <Card className="grid gap-3 p-5 sm:grid-cols-[1fr_180px]">
            <Field label="Name"><Input aria-label="Playbook name" value={pb.name} maxLength={200} onChange={(e) => setPb({ ...pb, name: e.target.value })} /></Field>
            <Field label="Category"><Select aria-label="Category" value={pb.category} onChange={(e) => setPb({ ...pb, category: e.target.value })}>{CATEGORIES.map((c) => <option key={c}>{c}</option>)}</Select></Field>
            <Field label="Description" className="sm:col-span-2"><Textarea aria-label="Description" rows={2} maxLength={2000} value={pb.description ?? ""} onChange={(e) => setPb({ ...pb, description: e.target.value })} /></Field>
          </Card>
          <Card className="p-5">
            <h3 className="text-[14px] font-semibold">Defaults</h3>
            <p className="mb-3 text-[12.5px] text-muted">Used by every step that doesn&apos;t set its own value.</p>
            <div className="flex flex-wrap gap-3">
              <Field label="Image style" className="w-40"><Select aria-label="Default image style" value={pb.settings.style ?? ""} onChange={(e) => setSettings({ style: e.target.value || undefined })}>
                <option value="">minimal</option>{o?.styles.filter((x) => x !== "minimal").map((x) => <option key={x}>{x}</option>)}</Select></Field>
              <Field label="Marketplace" className="w-44"><Select aria-label="Default marketplace" value={pb.settings.marketplace ?? ""} onChange={(e) => setSettings({ marketplace: e.target.value || undefined })}>
                <option value="">Amazon</option>{o && Object.entries(o.marketplaces).filter(([k]) => k !== "amazon").map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
              <Field label="Image size (px)" className="w-48" hint="Marketplaces usually want 2000 × 2000">
                <div className="flex items-center gap-1.5">
                  <Input type="number" min={256} max={4096} placeholder="2000" aria-label="Image width" value={pb.settings.width ?? ""} onChange={(e) => setSettings({ width: num(e.target.value) })} />
                  <span className="text-muted">×</span>
                  <Input type="number" min={256} max={4096} placeholder="2000" aria-label="Image height" value={pb.settings.height ?? ""} onChange={(e) => setSettings({ height: num(e.target.value) })} />
                </div>
              </Field>
            </div>
          </Card>
          <Card className="p-5">
            <div className="mb-3 flex items-center justify-between gap-2">
              <h3 className="text-[14px] font-semibold">Steps ({pb.steps.length})</h3>
              <span className="flex items-center gap-1 text-[12px] text-muted"><Clock className="size-3.5" />{formatMinutes(estimateMinutes(pb.steps, 1, o?.step_minutes))} per product</span>
            </div>
            <div className="flex flex-col gap-2">
              {pb.steps.map((s, i) => (
                <div key={i} className="rounded-[12px] border border-border p-3">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="flex size-6 items-center justify-center rounded-full bg-sunken font-mono text-xs text-muted">{i + 1}</span>
                    <span className="truncate text-[13px] font-medium">{stepLabel(s, o)}</span>
                    {!ro && <div className="ml-auto flex gap-1">
                      <Button size="icon-sm" variant="ghost" aria-label="Move up" disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp /></Button>
                      <Button size="icon-sm" variant="ghost" aria-label="Move down" disabled={i === pb.steps.length - 1} onClick={() => move(i, 1)}><ArrowDown /></Button>
                      <Button size="icon-sm" variant="ghost" aria-label="Duplicate step" disabled={pb.steps.length >= 20} onClick={() => duplicateStep(i)}><CopyPlus /></Button>
                      <Button size="icon-sm" variant="ghost" aria-label="Remove step" disabled={pb.steps.length === 1} onClick={() => setPb({ ...pb, steps: pb.steps.filter((_, j) => j !== i) })}><X /></Button>
                    </div>}
                  </div>
                  <div className="flex flex-wrap items-end gap-2">
                    <Field label="Step" className="w-44"><Select aria-label={`Step ${i + 1} kind`} value={s.kind} onChange={(e) => setKind(i, e.target.value)}>{STEP_KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
                    <StepFields s={s} set={(p) => setStep(i, p)} o={o} defaults={pb.settings} />
                  </div>
                </div>
              ))}
            </div>
            {!ro && <div className="mt-3 flex flex-wrap gap-1.5">
              <span className="mr-1 self-center text-[12px] text-muted">Add:</span>
              {STEP_KINDS.map(([k, l]) => <Button key={k} size="sm" variant="outline" disabled={pb.steps.length >= 20} onClick={() => setPb({ ...pb, steps: [...pb.steps, defaultStep(k)] })}><Plus />{l}</Button>)}
            </div>}
            {pb.steps.length >= 20 && <p className="mt-2 text-[12px] text-muted">A playbook can have at most 20 steps.</p>}
          </Card>
        </fieldset>
        <div className="flex flex-col gap-4 lg:sticky lg:top-0 lg:self-start">
          {!ro && <Card className="flex flex-col gap-3 p-5">
            <div className="flex items-center justify-between"><h3 className="text-[14px] font-semibold">Run on products</h3>
              {items.length > 0 && <span className="text-[12px] text-muted">{sel.length} selected</span>}</div>
            {products.isLoading ? <Skeleton className="h-40" /> : !items.length ? (
              <Notice className="text-xs">No products yet. <Link href="/products" className="text-primary underline">Add a product</Link> to run this playbook.</Notice>
            ) : (<>
              {items.length > 6 && <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted" />
                <Input className="pl-8" placeholder="Find by name, SKU, category" value={find} onChange={(e) => setFind(e.target.value)} aria-label="Find products" />
              </div>}
              <div className="flex gap-3 text-[12px]">
                <button className="text-primary hover:underline" onClick={() => setSel((s) => [...new Set([...s, ...visible.map((p) => p.id)])])}>Select {f ? "shown" : "all"}</button>
                {sel.length > 0 && <button className="text-muted hover:underline" onClick={() => setSel([])}>Clear</button>}
              </div>
              <div className="flex max-h-72 flex-col gap-1 overflow-y-auto">
                {visible.map((p) => {
                  const on = sel.includes(p.id);
                  return (
                    <button key={p.id} onClick={() => setSel((s) => (on ? s.filter((x) => x !== p.id) : [...s, p.id]))} aria-pressed={on}
                      className={cn("flex items-center gap-2 rounded-[9px] border px-2 py-1.5 text-left text-[13px]", on ? "border-primary bg-primary-soft" : "border-border hover:bg-sunken")}>
                      <span className={cn("flex size-4 shrink-0 items-center justify-center rounded border", on ? "border-primary bg-primary text-white" : "border-border-strong")}>{on && <Check className="size-3" />}</span>
                      <ImageThumb src={p.cover_url} alt="" className="size-7" />
                      <span className="min-w-0 flex-1"><span className="block truncate">{p.name}</span>{p.image_count === 0 && <span className="block text-[11px] text-warning">no photo — image steps will fail</span>}</span>
                    </button>
                  );
                })}
                {!visible.length && <p className="py-4 text-center text-[12px] text-muted">No products match.</p>}
              </div>
            </>)}
            <Field label="Brand" hint="Leave empty to use each product's own brand"><BrandSelect value={brandId} onChange={setBrandId} /></Field>
            <div className="flex items-center gap-2 text-[13px]">
              <Badge>{jobs} job{jobs === 1 ? "" : "s"}</Badge>
              {sel.length > 0 && <span className="flex items-center gap-1 text-[12px] text-muted"><Clock className="size-3.5" />{formatMinutes(est)}</span>}
            </div>
            {overLimit && <Notice tone="warning" className="text-xs">At most 50 products per run — split this into smaller runs.</Notice>}
            <Button size="lg" variant="ai" disabled={!sel.length || overLimit || !pb.steps.length} loading={running} onClick={run}><Play />{dirty ? "Save & run" : "Run playbook"}</Button>
            <Notice className="text-xs">Steps run in the background, one heavy job at a time, in the order above. Times are rough CPU estimates.</Notice>
          </Card>}
          {!ro && <Card className="p-5">
            <div className="mb-2 flex items-center justify-between"><h3 className="text-[14px] font-semibold">Recent runs</h3>
              <Link href="/scale" className="text-[12px] text-primary hover:underline">All runs</Link></div>
            {runs.isLoading ? <Skeleton className="h-16" /> : !runs.data?.length ? <p className="text-[12.5px] text-muted">Not run yet.</p> : (
              <div className="flex flex-col gap-2">
                {runs.data.map((r) => {
                  const s = runSummary(r);
                  return (
                    <Link key={r.id} href={`/factory?run=${r.id}`} className="rounded-[10px] border border-border p-2.5 hover:bg-sunken">
                      <div className="flex items-center justify-between text-[12.5px]">
                        <span>{timeAgo(r.created_at)}</span>
                        <Badge tone={s.state === "done" ? "success" : s.state === "failed" ? "danger" : s.state === "running" ? "ai" : "neutral"}>
                          {s.state === "running" ? `${s.active} left` : s.state === "failed" ? `${s.failed} failed` : s.state}</Badge>
                      </div>
                      <Progress className="mt-2" value={r.total ? ((s.done + s.failed) / r.total) * 100 : 0} tone="ai" />
                      <div className="mt-1 text-[11px] text-muted">{s.done} of {r.total} done</div>
                    </Link>
                  );
                })}
              </div>
            )}
          </Card>}
        </div>
      </div>
      <Confirm open={confirm} onOpenChange={setConfirm} title="Delete this playbook?" body="Past runs and everything they generated are kept."
        onConfirm={async () => {
          try { await del(`/playbooks/${id}`); qc.invalidateQueries({ queryKey: ["playbooks"] }); setSaved(snapshot(pb)); router.push("/playbooks"); }
          catch (e) { toast.error((e as Error).message); }
        }} />
    </>
  );
}
